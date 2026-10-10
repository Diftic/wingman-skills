"""Read-only source-log corpus audit of the real SC Log Reader pipeline.

Only audit reports/databases below --output are written. No Wingman or updater
activation occurs. Each file is snapshotted to a temporary stream at discovery
size; growing sources are identified and their later bytes are not included.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import traceback

from sc_log_reader.reader import Instructions, RecordAssembler, bundled_bytes
from sc_log_reader.service import Service, ToolInterface
try:
    from tools.support_diagnostics import support_diagnostics
except ModuleNotFoundError:
    from support_diagnostics import support_diagnostics


def write_json(path, value):
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
    # Windows readers can briefly deny replacement while inspecting progress.
    for attempt in range(40):
        try:
            os.replace(temporary,path)
            return
        except PermissionError:
            if attempt == 39:
                if path.parent.name == 'progress':
                    return  # Progress is advisory; never abort a log replay.
                raise
            time.sleep(0.05)


def record_digest(hasher, record):
    hasher.update(json.dumps([record.start,record.end,record.complete],separators=(',',':')).encode())
    hasher.update(hashlib.sha256(record.text.encode()).digest())


def stable_state(state):
    # Runtime age advances even when no persisted observation changes.
    # Keep every state/evidence field and all other health fields in the check.
    result = dict(state)
    result['reader_health'] = dict(result.get('reader_health', {}))
    result['reader_health'].pop('source_age_seconds', None)
    return result


def process_file(task):
    path=Path(task['path']);out=Path(task['output']);index=task['index']
    report={'index':index,'path':str(path),'relative_path':task['relative_path'],
            'environment':task['environment'],'discovered_bytes':task['size'],
            'status':'running','records':0,'recognized_records':0,'unrecognized_records':0,
            'raw_event_counts':{},'output_event_counts':{},'diagnostic_counts':{},
            'invariant_failures':[],'exceptions':[],'samples':[],'unknown_notification_labels':{},
            'notification_records':0,'unmatched_notification_records':0}
    progress=out/'progress'/f'{index:04}.json'
    begin=time.monotonic();last_progress=begin
    raw_counts=Counter();output_counts=Counter();diagnostics=Counter();unknown=Counter();statuses=Counter()
    service=None;probe=None
    def failure(kind,record=None,details=None):
        item={'check':kind}
        if record:item.update(byte_start=record.start,byte_end=record.end)
        if details:item['details']=details
        if len(report['invariant_failures'])<100:report['invariant_failures'].append(item)
    def sample(kind,record):
        if sum(s['reason']==kind for s in report['samples'])<3 and len(report['samples'])<50:
            report['samples'].append({'reason':kind,'byte_start':record.start,'byte_end':record.end,'text':record.text[:1600]})
    try:
        instructions=Instructions.load(bundled_bytes())
        if task.get('timings'):
            from timing_probe import TimingProbe
            probe=TimingProbe(out/'timings'/f'{index:04}')
            probe.set_file(index,task['relative_path'])
        file_build=re.search(r'Build\((\d+)\)',path.name)
        build=file_build[1] if file_build else None
        env=task['environment'];generation=f'audit-{index}'
        with tempfile.TemporaryFile(dir=out/'work',mode='w+b') as snapshot:
            read_hash=hashlib.sha256();remaining=task['size']
            with path.open('rb') as original:
                while remaining:
                    chunk=original.read(min(1024*1024,remaining))
                    if not chunk:break
                    snapshot.write(chunk);read_hash.update(chunk);remaining-=len(chunk)
            size=task['size']-remaining
            report.update(snapshot_bytes=size,sha256=read_hash.hexdigest(),short_read=bool(remaining))
            snapshot.seek(0)
            header=snapshot.read(min(size,32768)).decode('utf-8','replace')
            report['build_from_filename']=build
            report['build_header_lines']=[line[:300] for line in header.splitlines() if re.search(r'(?i)(build|version|branch)',line)][:12]
            snapshot.seek(0)
            runtime=out/'databases'/f'{index:04}'
            service=Service(runtime,instructions=instructions)
            original_parse=service.reader.parse
            last_event=[None]
            def observed_parse(*args,**kwargs):
                event=original_parse(*args,**kwargs);last_event[0]=event;return event
            service.reader.parse=observed_parse
            assembler=RecordAssembler(instructions)
            boundary=hashlib.sha256();observed_ranges=set();missing_timestamps=0

            def consume(record):
                nonlocal last_progress,missing_timestamps
                if probe:probe.set_record(record.start,record.end)
                report['records']+=1;record_digest(boundary,record);last_event[0]=None
                try:
                    rows=service.ingest(record,env,generation,build)
                    event=last_event[0]
                    if 'Added notification' in record.text:
                        report['notification_records']+=1
                        if event is None and 'UpdateNotificationItem' not in record.text:
                            report['unmatched_notification_records']+=1
                            m=re.search(r'Added notification\s+"([^"\n]*)',record.text)
                            label=m[1].split(':',1)[0] if m else '<unreadable>'
                            label=re.sub(r'\b\d[\d,.]*\b','<number>',label).strip()[:120]
                            unknown[label]+=1
                            sample('unmatched_notification',record)
                    if event is None:
                        report['unrecognized_records']+=1
                        return
                    report['recognized_records']+=1;raw_counts[event.event_type]+=1
                    # T7 journals only clean recognized domain evidence.
                    if not event.errors and event.event_type != 'diagnostic':
                        observed_ranges.add((record.start,record.end))
                    if event.source_timestamp is None:missing_timestamps+=1
                    for error in event.errors:
                        diagnostics[error]+=1;sample(error,record)
                    if event.errors and rows:failure('invalid_record_emitted_events',record)
                    for row in rows:
                        output_counts[row['event_type']]+=1;statuses[row['status']]+=1
                        amount=row.get('amount_auec')
                        if amount is not None:
                            if not isinstance(amount,(int,float)) or not math.isfinite(amount):failure('nonfinite_money',record)
                            if row['status']!='confirmed':failure('unconfirmed_money',record)
                            if row.get('item_name') or event.fields.get('unresolved_number'):failure('item_or_unresolved_number_booked_as_money',record)
                        if row['status']=='requested' and amount is not None:failure('request_booked_as_money',record)
                        if row['event_type'] in ('shop_buy','shop_sell') and row['status']=='confirmed':
                            if len(row['source_occurrences'])!=2:failure('trade_without_request_and_response',record)
                        if row['event_type']=='money_sent' and amount is not None and not row['data'].get('recipient'):failure('money_sent_without_recipient',record)
                except Exception as exc:
                    if len(report['exceptions'])<20:
                        report['exceptions'].append({'phase':'ingest','byte_start':record.start,'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
                finally:
                    if time.monotonic()-last_progress>5:
                        write_json(progress,{'path':task['relative_path'],'phase':'replay','records':report['records'],
                                             'byte_end':record.end,'snapshot_bytes':size,'elapsed_seconds':round(time.monotonic()-begin,1)})
                        last_progress=time.monotonic()

            while chunk:=snapshot.read(256*1024):
                try:records=assembler.feed(chunk)
                except Exception as exc:
                    report['exceptions'].append({'phase':'assembly','type':type(exc).__name__,'message':str(exc)})
                    raise
                for record in records:consume(record)
            for record in assembler.finish():consume(record)
            if probe:probe.enabled=False
            report['assembly_digest_256k']=boundary.hexdigest()
            report['missing_source_timestamps']=missing_timestamps
            before_state=service.state(env)
            json.dumps(before_state,allow_nan=False)
            before_counts=(service.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],service.db.execute('SELECT COUNT(*) FROM events').fetchone()[0])
            integrity=service.db.execute('PRAGMA integrity_check').fetchone()[0]
            report['database_integrity']=integrity
            if integrity!='ok':failure('database_integrity')
            ledger=ToolInterface(service).call('get_trade_ledger',{'environment':env,'time_range':'all'})
            expected=service.db.execute("SELECT COALESCE(SUM(amount),0) FROM events WHERE status='confirmed' AND event_type IN ('shop_buy','shop_sell','commodity_buy','commodity_sell')").fetchone()[0]
            if not math.isclose(ledger['net_cash_flow_auec'],expected,abs_tol=.0001):failure('tool_ledger_total_mismatch')
            report['ledger']=ledger
            report['final_state']=before_state
            service.close();service=Service(runtime,instructions=instructions)
            if stable_state(service.state(env))!=stable_state(before_state):failure('restart_state_mismatch')
            snapshot.seek(0);small=RecordAssembler(instructions);small_hash=hashlib.sha256();replayed=0;second_records=0
            def second(record):
                nonlocal replayed,second_records,last_progress
                second_records+=1;record_digest(small_hash,record)
                if (record.start,record.end) in observed_ranges:
                    replayed+=1
                    if service.ingest(record,env,generation,build):failure('duplicate_after_restart',record)
                if time.monotonic()-last_progress>5:
                    write_json(progress,{'path':task['relative_path'],'phase':'restart_and_chunk_check','records':second_records,'byte_end':record.end,'snapshot_bytes':size,'elapsed_seconds':round(time.monotonic()-begin,1)})
                    last_progress=time.monotonic()
            while chunk:=snapshot.read(4093):
                for record in small.feed(chunk):second(record)
            for record in small.finish():second(record)
            report.update(assembly_digest_4093=small_hash.hexdigest(),restart_replayed_observations=replayed,
                          second_pass_records=second_records,chunk_boundaries_identical=small_hash.hexdigest()==boundary.hexdigest())
            if not report['chunk_boundaries_identical']:failure('chunk_size_changes_record_assembly')
            if replayed!=before_counts[0]:failure('not_all_observations_replayed',details={'replayed':replayed,'stored':before_counts[0]})
            after_counts=(service.db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],service.db.execute('SELECT COUNT(*) FROM events').fetchone()[0])
            if before_counts!=after_counts or stable_state(service.state(env))!=stable_state(before_state):failure('restart_dedup_changed_database')
            report['stored_observations']=after_counts[0];report['stored_output_events']=after_counts[1]
            report['diagnostic_rows']=service.db.execute("SELECT COUNT(*) FROM observations WHERE errors!='[]' OR event_type='diagnostic'").fetchone()[0]
            report['support_diagnostics'] = support_diagnostics(service)
            report['restart_scope'] = 'exact clean recognized observations; diagnostic-only rows use bounded support storage and are excluded from unlimited replay dedup'
            report['suppressed_without_diagnostic']=service.db.execute("SELECT COUNT(*) FROM observations o WHERE errors='[]' AND NOT EXISTS(SELECT 1 FROM events e WHERE e.occurrence=o.occurrence)").fetchone()[0]
            report['database_integrity_after_restart']=service.db.execute('PRAGMA integrity_check').fetchone()[0]
            service.close();service=None
            post_hash=hashlib.sha256();remaining=size
            with path.open('rb') as original:
                while remaining:
                    chunk=original.read(min(1024*1024,remaining))
                    if not chunk:break
                    post_hash.update(chunk);remaining-=len(chunk)
            final_stat=path.stat()
            report['source_prefix_unchanged']=not remaining and post_hash.hexdigest()==report['sha256']
            report['source_bytes_after']=final_stat.st_size
            report['source_grew']=final_stat.st_size>task['size']
            report['source_changed_since_discovery']=final_stat.st_mtime_ns!=task['mtime_ns'] or final_stat.st_size!=task['size']
            if not report['source_prefix_unchanged']:failure('source_changed_during_test')
    except Exception as exc:
        report['exceptions'].append({'phase':'file','type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()})
    finally:
        if service:service.close()
        if probe:probe.close()
    report.update(raw_event_counts=dict(raw_counts),output_event_counts=dict(output_counts),
                  diagnostic_counts=dict(diagnostics),output_status_counts=dict(statuses),
                  unknown_notification_labels=dict(unknown.most_common(100)),elapsed_seconds=round(time.monotonic()-begin,3))
    report['status']='failed_checks' if report['exceptions'] or report['invariant_failures'] else ('completed_with_diagnostics' if diagnostics else 'completed')
    write_json(out/'files'/f'{index:04}.json',report)
    write_json(progress,{'path':task['relative_path'],'phase':'done','status':report['status'],'records':report['records'],'elapsed_seconds':report['elapsed_seconds']})
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--output',required=True);parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--timings',action='store_true')
    args=parser.parse_args();source=Path(args.root).resolve();out=Path(args.output).resolve()
    if out==source or source in out.parents:raise SystemExit('Reports must be outside the source logs')
    if out.exists():raise SystemExit('Use a new report directory')
    out.mkdir(parents=True)
    for directory in ('work','progress','files','databases'):(out/directory).mkdir()
    errors=[];tasks=[]
    for directory,dirs,files in os.walk(source,onerror=lambda exc:errors.append(str(exc)),followlinks=False):
        for name in sorted(files):
            if not name.lower().endswith('.log'):continue
            path=Path(directory)/name
            try:
                stat=path.stat();relative=path.relative_to(source)
                tasks.append({'path':str(path),'relative_path':str(relative),'environment':relative.parts[0] if len(relative.parts)>1 else 'ROOT','size':stat.st_size,'mtime_ns':stat.st_mtime_ns})
            except OSError as exc:errors.append(str(exc))
    tasks.sort(key=lambda x:x['relative_path'])
    for index,task in enumerate(tasks,1):task.update(index=index,output=str(out),timings=args.timings)
    code_root=Path(__file__).resolve().parents[1]/'src/sc_log_reader'
    hashes={str(p.relative_to(code_root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in code_root.rglob('*') if p.is_file() and (p.suffix in ('.py','.json'))}
    manifest={'started_utc':datetime.now(timezone.utc).isoformat(),'source_root':str(source),'files':tasks,'enumeration_errors':errors,'code_hashes':hashes,'instruction_sha256':hashlib.sha256(bundled_bytes()).hexdigest(),'method':'Every discovered file, no duplicate skipping; immutable prefix snapshot; 256KiB full service replay; 4093-byte assembly and restart/dedup pass; local reports only.'}
    write_json(out/'manifest.json',manifest)
    project=code_root.parents[1]
    suite=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-v'],cwd=project,text=True,capture_output=True)
    (out/'unittest.txt').write_text(suite.stdout+suite.stderr,encoding='utf-8')
    print(json.dumps({'phase':'start','files':len(tasks),'bytes':sum(t['size'] for t in tasks),'unit_suite_exit':suite.returncode,'enumeration_errors':errors}),flush=True)
    results=[];start=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(process_file,t):t for t in tasks}
        for future in as_completed(futures):
            task=futures[future]
            try:result=future.result()
            except Exception as exc:result={'index':task['index'],'relative_path':task['relative_path'],'status':'worker_failed','exceptions':[str(exc)]}
            results.append(result)
            print(json.dumps({'done':len(results),'total':len(tasks),'file':task['relative_path'],'status':result['status'],'records':result.get('records',0),'elapsed_seconds':round(time.monotonic()-start,1)}),flush=True)
            write_json(out/'progress.json',{'completed':len(results),'total':len(tasks),'elapsed_seconds':round(time.monotonic()-start,1),'statuses':dict(Counter(r['status'] for r in results))})
    results.sort(key=lambda r:r['index'])
    totals=Counter();raw=Counter();outputs=Counter();diagnostics=Counter();unknown=Counter();groups=defaultdict(list)
    for r in results:
        for key in ('snapshot_bytes','records','recognized_records','unrecognized_records','notification_records','unmatched_notification_records','stored_output_events','diagnostic_rows','restart_replayed_observations'):
            totals[key]+=r.get(key,0)
        raw.update(r.get('raw_event_counts',{}));outputs.update(r.get('output_event_counts',{}));diagnostics.update(r.get('diagnostic_counts',{}));unknown.update(r.get('unknown_notification_labels',{}))
        if r.get('sha256'):groups[r['sha256']].append(r['relative_path'])
    new_hashes={str(p.relative_to(code_root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in code_root.rglob('*') if p.is_file() and p.suffix in ('.py','.json')}
    events={r['event'] for r in Instructions.load(bundled_bytes()).data['rules']}
    summary={'finished_utc':datetime.now(timezone.utc).isoformat(),'files':len(tasks),'completed_files':len(results),'unit_suite_exit':suite.returncode,
             'statuses':dict(Counter(r['status'] for r in results)),'totals':dict(totals),'raw_event_counts':dict(raw),'output_event_counts':dict(outputs),
             'diagnostic_counts':dict(diagnostics),'unknown_notification_labels':dict(unknown.most_common(100)),
             'observed_event_types':sorted(set(raw)&events),'unobserved_event_types':sorted(events-set(raw)),
             'unique_content_files':len(groups),'duplicate_content_groups':[v for v in groups.values() if len(v)>1],
             'failed_files':[r['relative_path'] for r in results if r['status'] in ('worker_failed','failed_checks')],
             'enumeration_errors':errors,'code_unchanged':hashes==new_hashes,'elapsed_seconds':round(time.monotonic()-start,1),
             'limitations':['Replay has no hand-labeled ground truth; recognized counts are not accuracy.','Duplicate file contents were tested separately and are included in totals.','Unused rules are covered by synthetic tests only.','Original logs are read-only; no Wingman or update activation.']}
    write_json(out/'summary.json',summary)
    write_json(out/'results.json',results)
    print(json.dumps({'phase':'complete','summary':str(out/'summary.json'),'statuses':summary['statuses'],'totals':dict(totals)}),flush=True)
    return 0 if not summary['failed_files'] and suite.returncode==0 and not errors else 1

if __name__=='__main__':raise SystemExit(main())
