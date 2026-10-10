"""End-to-end test stitching scanner, uploader, and dedup with a mock Worker."""

from __future__ import annotations

from pathlib import Path

import httpx

from log_donor.dedup import DedupStore
from log_donor.scanner import discover_candidates
from log_donor.uploader import Uploader


def test_full_donation_cycle_records_dedup(
    fake_sc_install: Path, tmp_path: Path, sc_not_running
) -> None:
    store = DedupStore(db_path=tmp_path / "state.sqlite")
    cands = discover_candidates(fake_sc_install, store)
    # Live only: current Game.log plus both parseable backups.
    assert len(cands) == 3

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/begin":
            body = request.content.decode()
            import json
            payload = json.loads(body)
            files_resp = [
                {
                    "sha256": f["sha256"],
                    "put_url": f"https://r2.example/{f['sha256'][:6]}",
                    "key": f"2026-05-14/u/Live/{f['renamed']}",
                }
                for f in payload["files"]
            ]
            return httpx.Response(
                200,
                json={"upload_id": "u-int", "files": files_resp},
            )
        if request.url.path == "/upload/complete":
            return httpx.Response(200, json={"upload_id": "u-int", "complete": True})
        if request.method == "PUT":
            return httpx.Response(200)
        return httpx.Response(404)

    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="sc_log_reader v1.0",
        wingman_version="1.0",
        transport=httpx.MockTransport(handler),
    )
    result = up.upload(cands, progress_cb=lambda _: None)

    assert result.upload_id == "u-int"
    assert result.succeeded_count == 3
    assert result.failed_count == 0

    # Record successes in dedup store, simulating what the skill will do
    rows = [
        (f.sha256, str(next(c.path for c in cands if c.sha256 == f.sha256)), result.upload_id)
        for f in result.files
        if f.succeeded and not f.already_uploaded
    ]
    store.record_many_uploaded(rows)

    # Second scan should be empty
    second = discover_candidates(fake_sc_install, store)
    assert second == []
