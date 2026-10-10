"""Committed support accounting; retained samples do not imply lifetime dedup."""
import json


def support_diagnostics(service):
    with service.lock:
        totals = [json.loads(row[0]) for row in service.db.execute('SELECT payload FROM support_totals')]
        buckets = [json.loads(row[0]) for row in service.db.execute('SELECT payload FROM support_buckets')]
        samples = [json.loads(row[0]) for row in service.db.execute('SELECT payload FROM support_samples')]
        legacy = service.db.execute("SELECT COUNT(*) FROM observations WHERE errors!='[]' OR event_type='diagnostic'").fetchone()[0]
    return dict(lifetime_reason_counts={row['environment'] + ':' + row['reason']: row['count'] for row in totals},
                retained_buckets=buckets, retained_samples=samples,
                legacy_diagnostic_observations=legacy,
                scope='committed lifetime reason counts; bounded retained cause/stage buckets and samples')
