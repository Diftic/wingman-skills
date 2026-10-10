"""Sequential, chronological real-log story audit. Production code stays unchanged.

The continuous-history stress profile keeps state per environment across file
boundaries and lets explicit login/character/shard records control resets. This
deliberately supplements the production file-generation reset profile tested by
corpus_test.py. Exact full-file duplicates within an environment are audited as
aliases rather than counted as a second play session. Cross-environment copies
remain separate histories and are flagged in the index.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import traceback
from sc_log_reader.reader import Instructions, Reader, Record, RecordAssembler, bundled_bytes
from sc_log_reader.service import Service

STAMP=re.compile(rb'^<([^>]+)>',re.M)

def timestamp(raw):
    try:
        dt=datetime.fromisoformat(raw.decode().replace('Z','+00:00'))
        return dt.astimezone(timezone.utc).isoformat() if dt.tzinfo else None
    except (UnicodeError,ValueError):return None

def save(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')

def brief(state):
    return {k:state[k] for k in ('player_name','player_geid','shard','active_missions','injuries','location_name','location_status','aboard_ship','ship','own_ship')}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--timings',action='store_true')
    args=parser.parse_args();root=Path(args.root).resolve();out=Path(args.output).resolve()
    if out.exists() or out==root or root in out.parents:raise SystemExit('Need a new output outside log tree')
    out.mkdir(parents=True);(out/'work').mkdir();(out/'chapters').mkdir()
    items=[];scan_errors=[];start=time.monotonic()
    # Read only head and tail for indexing. The full sequential pass hashes all
    # snapshotted bytes and evaluates every record, including untimestamped ones.
    for directory,dirs,files in os.walk(root,onerror=lambda e:scan_errors.append(str(e)),followlinks=False):
        for name in files:
            if not name.lower().endswith('.log'):continue
            path=Path(directory)/name
            try:
                st=path.stat()
                with path.open('rb') as f:
                    head=f.read(128*1024);f.seek(max(0,st.st_size-256*1024));tail=f.read()
                headtimes=[timestamp(m[1]) for m in STAMP.finditer(head)];tailtimes=[timestamp(m[1]) for m in STAMP.finditer(tail)]
                first=next((t for t in headtimes if t),None);last=next((t for t in reversed(tailtimes) if t),None)
                rel=path.relative_to(root)
                items.append({'path':str(path),'relative_path':str(rel),'environment':rel.parts[0],
                              'size':st.st_size,'mtime_ns':st.st_mtime_ns,'first_timestamp':first,'last_timestamp_hint':last})
            except OSError as exc:scan_errors.append({'path':str(path),'error':str(exc)})
    items.sort(key=lambda x:(x['first_timestamp'] or '9999',x['environment'],x['relative_path']))
    for n,item in enumerate(items,1):item['order']=n
    save(out/'chronological-index.json',{'files':items,'scan_errors':scan_errors,'ordering':'First timestamp inside each file; physical record order within file. Untimed files last. Environments retain independent state.'})
    instructions=Instructions.load(bundled_bytes())
    probe=None
    if args.timings:
        from timing_probe import TimingProbe
        probe=TimingProbe(out/'timings')
    reader=Reader(instructions)
    service=Service(out/'history',instructions=instructions)
    offsets=defaultdict(int);seen_content=defaultdict(dict);last_time={};chapters=[];finding_counts=Counter();finding_samples=defaultdict(list)
    total_records=0;raw_counts=Counter();output_counts=Counter();diag=Counter();timeline_count=0
    source_hashes={};bytes_total=0;exceptions=[];last_progress=time.monotonic()
    cached=[None]
    # Each record is parsed by the actual Reader; recognized records then go
    # through actual persistent Service/State without parsing them a second time.
    service.reader.parse=lambda *args,**kwargs:cached[0]
    code_root=Path(__file__).resolve().parents[1]/'src/sc_log_reader'
    code_hashes={str(p.relative_to(code_root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in code_root.rglob('*') if p.suffix in ('.py','.json')}
    def finding(kind,item,record=None,details=None):
        finding_counts[kind]+=1
        if len(finding_samples[kind])<12:
            s={'order':item['order'],'file':item['relative_path']}
            if record:s.update(byte_start=record.start,byte_end=record.end)
            if details is not None:s['details']=details
            finding_samples[kind].append(s)
    try:
        with (out/'timeline.jsonl').open('w',encoding='utf-8') as timeline:
            for item in items:
                env=item['environment'];file_start=time.monotonic();before=brief(service.state(env));file_raw=Counter();file_out=Counter();file_findings=Counter();file_records=0
                chapter={**item,'state_before':before,'boundaries':[],'notable_events':[]}
                with tempfile.TemporaryFile(dir=out/'work',mode='w+b') as snapshot:
                    hasher=hashlib.sha256();remaining=item['size']
                    with Path(item['path']).open('rb') as original:
                        while remaining:
                            chunk=original.read(min(1024*1024,remaining))
                            if not chunk:break
                            snapshot.write(chunk);hasher.update(chunk);remaining-=len(chunk)
                    sha=hasher.hexdigest();bytes_total+=item['size']-remaining;chapter['sha256']=sha;source_hashes[item['relative_path']]=sha
                    if sha in seen_content[env]:
                        chapter.update(status='duplicate_alias',duplicate_of=seen_content[env][sha],state_after=before)
                        chapters.append(chapter);save(out/'chapters'/f"{item['order']:04}.json",chapter)
                        print(json.dumps({'done':len(chapters),'total':len(items),'file':item['relative_path'],'status':'duplicate_alias'}),flush=True)
                        continue
                    seen_content[env][sha]=item['relative_path']
                    if last_time.get(env) and item['first_timestamp'] and item['first_timestamp']<last_time[env]:
                        finding('overlapping_file_time_ranges',item,details={'previous_last':last_time[env],'next_first':item['first_timestamp']})
                    if not item['first_timestamp']:finding('file_without_index_timestamp',item)
                    snapshot.seek(0);assembler=RecordAssembler(instructions);base=offsets[env];seen_login=False
                    if probe:probe.set_file(item['order'],item['relative_path'])
                    def consume(record):
                        nonlocal total_records,file_records,timeline_count,last_progress,seen_login
                        if probe:probe.set_record(record.start,record.end)
                        total_records+=1;file_records+=1
                        if time.monotonic()-last_progress>5:
                            save(out/'progress.json',{'completed_files':len(chapters),'total_files':len(items),'current_file':item['relative_path'],'current_byte':record.end,'current_size':item['size'],'total_records':total_records,'elapsed_seconds':round(time.monotonic()-start,1),'findings':dict(finding_counts)})
                            last_progress=time.monotonic()
                        try:
                            event=reader.parse(record.text,complete=record.complete)
                            if event is None:return
                            raw_counts[event.event_type]+=1;file_raw[event.event_type]+=1
                            for error in event.errors:diag[error]+=1
                            # Pull before-state only for meaningful narrative records.
                            interest=event.event_type!='attachment_received'
                            prior=service.state(env) if interest else None
                            cached[0]=event
                            output=service.ingest(Record(record.text,base+record.start,base+record.end,record.complete),env,'continuous-'+env)
                            if event.source_timestamp:
                                moment=event.source_timestamp.isoformat()
                                if last_time.get(env) and moment<last_time[env]:finding('recognized_timestamp_moves_backwards',item,record,{'previous':last_time[env],'current':moment})
                                last_time[env]=max(moment,last_time.get(env,moment))
                            for row in output:output_counts[row['event_type']]+=1;file_out[row['event_type']]+=1
                            if not interest:return
                            after=service.state(env);kind=event.event_type;fields=event.fields;issues=[]
                            if event.errors:
                                if kind in ('channel_change','reward_earned','objective_complete','objective_new','contract_complete','money_sent'):
                                    issues.append('story_event_rejected_by_parser')
                            if kind in ('user_login','session_start'):
                                seen_login=True
                                chapter['boundaries'].append({'event':kind,'timestamp':event.source_timestamp.isoformat() if event.source_timestamp else None,'byte_start':record.start,'missions_before':len(prior['active_missions']),'missions_after':len(after['active_missions'])})
                                if prior['active_missions'] and not after['active_missions']:issues.append('login_boundary_cleared_active_missions')
                            if kind.startswith('objective_') and fields.get('mission_id') and fields['mission_id'] not in prior['active_missions'] and not event.errors:issues.append('objective_without_observed_active_mission')
                            if kind in ('contract_complete','contract_failed') and fields.get('mission_id') not in prior['active_missions'] and not event.errors:issues.append('mission_terminal_without_observed_acceptance')
                            if kind=='channel_change' and fields.get('action')=='joined':
                                name=fields.get('channel_raw','')
                                human_name=any(name.startswith(m+' ') for m in instructions.data['lookups']['ship_manufacturer_names'])
                                if human_name and not after['aboard_ship']:issues.append('named_ship_join_did_not_establish_ship_state')
                            if kind=='qt_arrived' and not prior['aboard_ship']:issues.append('qt_arrival_unattributed_after_ship_context_missing')
                            if kind=='location_change' and output and output[0]['status']=='unresolved':
                                issues.append('unmapped_location_keeps_previous_location' if after['location_name'] is not None or after['location_guid'] is not None or after['location_status']!='unknown' else 'unmapped_location_current_unknown')
                            if kind=='shop_transaction_result':
                                if output and output[0]['status'] in ('unresolved','ambiguous'):issues.append('shop_response_not_correlated')
                                for row in output:
                                    if row['status']=='confirmed' and row.get('amount_auec') is None:issues.append('confirmed_trade_has_unknown_currency')
                            if kind=='reward_earned' and not output:issues.append('reward_did_not_reach_event_history')
                            if kind=='inventory_location_update' and prior['location_status']=='at' and not prior['location_guid'] and fields.get('loc_from') not in (None,'0') and fields.get('loc_from')!=fields.get('loc_to'):issues.append('location_transition_cannot_resolve_departure_without_guid')
                            for problem in issues:
                                finding(problem,item,record,{'event_type':kind,'fields':fields,'errors':event.errors,'prior_location':prior['location_name'],'prior_ship':prior['ship']});file_findings[problem]+=1
                            entry={'order':item['order'],'file':item['relative_path'],'byte_start':record.start,'byte_end':record.end,'environment':env,'timestamp':event.source_timestamp.isoformat() if event.source_timestamp else None,
                                   'event_type':kind,'fields':fields,'errors':event.errors,'emitted':[{'event_type':r['event_type'],'status':r['status'],'amount_auec':r.get('amount_auec')} for r in output],'issues':issues,
                                   'state_changes':{k:{'from':prior[k],'to':after[k]} for k in ('player_name','player_geid','shard','location_name','location_status','aboard_ship','ship','active_missions','injuries') if prior[k]!=after[k]}}
                            timeline.write(json.dumps(entry,ensure_ascii=False)+'\n');timeline_count+=1
                            if (kind.startswith(('contract_','objective_')) or kind in ('location_change','channel_change','shop_transaction_result','reward_earned','injury','med_bed_heal')) and len(chapter['notable_events'])<250:chapter['notable_events'].append(entry)
                        except Exception as exc:
                            exceptions.append({'file':item['relative_path'],'byte_start':record.start,'error':str(exc),'traceback':traceback.format_exc()})
                    while chunk:=snapshot.read(256*1024):
                        for record in assembler.feed(chunk):consume(record)
                    for record in assembler.finish():consume(record)
                    offsets[env]+=item['size']+1
                    chapter['state_after']=brief(service.state(env));chapter['has_login_boundary']=seen_login
                    if before['player_name'] and not seen_login: finding('file_without_explicit_login_boundary',item,details={'inherited_state':before})
                    verify=hashlib.sha256();remaining=item['size']
                    with Path(item['path']).open('rb') as original:
                        while remaining:
                            chunk=original.read(min(1024*1024,remaining))
                            if not chunk:break
                            verify.update(chunk);remaining-=len(chunk)
                    chapter['source_prefix_unchanged']=remaining==0 and verify.hexdigest()==sha
                    if not chapter['source_prefix_unchanged']:finding('source_changed_during_replay',item)
                    chapter.update(status='replayed',records=file_records,raw_event_counts=dict(file_raw),output_event_counts=dict(file_out),findings=dict(file_findings),elapsed_seconds=round(time.monotonic()-file_start,2))
                    chapters.append(chapter);save(out/'chapters'/f"{item['order']:04}.json",chapter)
                    print(json.dumps({'done':len(chapters),'total':len(items),'file':item['relative_path'],'start':item['first_timestamp'],'records':file_records,'findings':sum(file_findings.values())}),flush=True)
        integrity=service.db.execute('PRAGMA integrity_check').fetchone()[0]
        final_states={env:brief(service.state(env)) for env in offsets}
    finally:
        service.close()
        if probe:probe.close()
    new_hashes={str(p.relative_to(code_root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in code_root.rglob('*') if p.suffix in ('.py','.json')}
    summary={'files_indexed':len(items),'files_replayed':sum(c['status']=='replayed' for c in chapters),'duplicate_aliases':sum(c['status']=='duplicate_alias' for c in chapters),'bytes_read':bytes_total,'records':total_records,
             'timeline_entries':timeline_count,'raw_event_counts':dict(raw_counts),'output_event_counts':dict(output_counts),'diagnostic_counts':dict(diag),'findings':dict(finding_counts),'finding_samples':dict(finding_samples),
             'exceptions':exceptions,'scan_errors':scan_errors,'database_integrity':integrity,'final_states':final_states,'code_unchanged':code_hashes==new_hashes,'elapsed_seconds':round(time.monotonic()-start,2),
             'profile':'Continuous-history stress replay. Shared service, separate environments, physical-order events. State survives file boundaries; real login/character/shard events decide resets. Production generation-reset behavior tested separately.',
             'classification_scope':'Every record is independently parsed by Reader. Only recognized/diagnostic Events enter Service through cached parse; Reader classification metadata is not propagated and unrecognized records are not Service-sampled. This run qualifies domain chronology, not production unknown sampling. Paced Tailer qualification exercises the production parse/classification/support path.'}
    save(out/'summary.json',summary);save(out/'source-hashes.json',source_hashes)
    for env in offsets:
        lines=[f'# {env}: chronological session story','',summary['profile'],'','Flags include confirmed parser gaps and evidence gaps that need interpretation; a missing observed acceptance is not automatically a game or reader bug.','']
        for c in chapters:
            if c['environment']!=env:continue
            lines.extend([f"## {c['order']:03}: {c['first_timestamp'] or 'unknown time'}",'',f"File: `{c['relative_path']}`",''])
            if c['status']=='duplicate_alias':lines.extend([f"Exact duplicate of `{c['duplicate_of']}`; already represented in this story.",'']);continue
            lines.append(f"{c['records']:,} records; {len(c['boundaries'])} login/character boundary records. Active missions: {len(c['state_before']['active_missions'])} before, {len(c['state_after']['active_missions'])} after.")
            lines.append('')
            for entry in c['notable_events']:
                f=entry['fields'];detail=f.get('mission_name') or f.get('objective') or f.get('channel_raw') or f.get('location') or f.get('item_name') or f.get('result') or f.get('body_part') or ''
                suffix='; '+', '.join(entry['issues']) if entry['issues'] else ''
                lines.append(f"- {entry['timestamp'] or 'unknown time'} — **{entry['event_type']}**: {str(detail).replace(chr(10),' ')[:180]}{suffix}")
            lines.extend(['',f"End: location `{c['state_after']['location_name']}`, ship `{c['state_after']['ship']}`, {len(c['state_after']['injuries'])} tracked injuries.",''])
        (out/(env+'-story.md')).write_text('\n'.join(lines),encoding='utf-8')
    save(out/'progress.json',{'completed_files':len(chapters),'total_files':len(items),'phase':'complete','records':total_records,'elapsed_seconds':summary['elapsed_seconds']})
    print(json.dumps({'phase':'complete','summary':str(out/'summary.json'),'findings':dict(finding_counts)}),flush=True)
    return 1 if exceptions or scan_errors or integrity!='ok' else 0

if __name__=='__main__':raise SystemExit(main())
