"""Tests for log_donor.uploader.

Mocks the network via httpx.MockTransport.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from log_donor.types import Candidate
from log_donor.uploader import Uploader


def _make_candidate(tmp_path: Path, name: str, content: bytes) -> Candidate:
    p = tmp_path / name
    p.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    return Candidate(
        path=p,
        install="Live",
        game_version="4.8.180.28520",
        size_bytes=len(content),
        sha256=sha,
        detected_handle="Mallachi",
        renamed=f"Mallachi_{name}",
    )


def test_begin_sends_manifest_with_token_header(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"hello world")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["token"] = request.headers.get("X-Donor-Token")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "upload_id": "u-1",
                "files": [
                    {
                        "sha256": cand.sha256,
                        "put_url": "https://r2.example/put",
                        "key": "2026-05-14/u-1/Live/Mallachi_x.log",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="secret",
        client_version="sc_log_reader v1.0",
        wingman_version="1.0",
        transport=transport,
    )
    begin = up._begin([cand])
    assert begin.upload_id == "u-1"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://w.example/upload/begin"
    assert captured["token"] == "secret"
    body = captured["body"]
    assert body["files"][0]["sha256"] == cand.sha256
    assert body["files"][0]["renamed"] == cand.renamed


def test_begin_raises_on_401(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="wrong",
        client_version="t",
        wingman_version="t",
        transport=transport,
    )
    with pytest.raises(PermissionError):
        up._begin([cand])


def test_put_file_succeeds_on_first_try(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"hello")
    put_calls: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT":
            put_calls.append(request.content)
            return httpx.Response(200)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=transport,
    )
    ok = up._put_file(cand, "https://r2.example/put")
    assert ok is True
    assert put_calls == [b"hello"]


def test_put_file_retries_on_5xx_then_succeeds(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"hello")
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] < 2:
            return httpx.Response(503)
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=transport,
    )
    ok = up._put_file(cand, "https://r2.example/put", sleep=lambda _: None)
    assert ok is True
    assert counter["n"] == 2


def test_put_file_gives_up_after_max_retries(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"hello")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=transport,
    )
    ok = up._put_file(cand, "https://r2.example/put", sleep=lambda _: None)
    assert ok is False


def test_upload_happy_path(tmp_path: Path) -> None:
    cand_a = _make_candidate(tmp_path, "a.log", b"aaa")
    cand_b = _make_candidate(tmp_path, "b.log", b"bbb")

    events: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/begin":
            events.append("begin")
            return httpx.Response(
                200,
                json={
                    "upload_id": "u-7",
                    "files": [
                        {
                            "sha256": cand_a.sha256,
                            "put_url": "https://r2.example/a",
                            "key": "2026-05-14/u-7/Live/Mallachi_a.log",
                        },
                        {
                            "sha256": cand_b.sha256,
                            "put_url": "https://r2.example/b",
                            "key": "2026-05-14/u-7/Live/Mallachi_b.log",
                        },
                    ],
                },
            )
        if request.url.path == "/upload/complete":
            events.append("complete")
            return httpx.Response(200, json={"upload_id": "u-7", "complete": True})
        if request.method == "PUT":
            events.append(f"put-{request.url}")
            return httpx.Response(200)
        return httpx.Response(404)

    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=httpx.MockTransport(handler),
    )
    progress: list[int] = []
    result = up.upload([cand_a, cand_b], progress_cb=progress.append)

    assert result.upload_id == "u-7"
    assert result.succeeded_count == 2
    assert result.failed_count == 0
    assert events[0] == "begin"
    assert events[-1] == "complete"
    assert progress == [1, 2]


def test_upload_marks_already_uploaded(tmp_path: Path) -> None:
    cand = _make_candidate(tmp_path, "x.log", b"x")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/begin":
            return httpx.Response(
                200,
                json={
                    "upload_id": "u-8",
                    "files": [
                        {
                            "sha256": cand.sha256,
                            "already_uploaded": True,
                            "key": "old-key",
                        }
                    ],
                },
            )
        if request.url.path == "/upload/complete":
            return httpx.Response(200, json={"upload_id": "u-8", "complete": True})
        return httpx.Response(404)

    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=httpx.MockTransport(handler),
    )
    result = up.upload([cand], progress_cb=lambda _: None)
    assert result.files[0].already_uploaded is True
    assert result.files[0].succeeded is True   # treated as success for state purposes
    assert result.total_bytes_uploaded == 0    # nothing was actually transferred


def test_upload_partial_failure(tmp_path: Path) -> None:
    cand_a = _make_candidate(tmp_path, "a.log", b"aaa")
    cand_b = _make_candidate(tmp_path, "b.log", b"bbb")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/begin":
            return httpx.Response(
                200,
                json={
                    "upload_id": "u-9",
                    "files": [
                        {
                            "sha256": cand_a.sha256,
                            "put_url": "https://r2.example/a",
                            "key": "k-a",
                        },
                        {
                            "sha256": cand_b.sha256,
                            "put_url": "https://r2.example/b",
                            "key": "k-b",
                        },
                    ],
                },
            )
        if request.url.path == "/upload/complete":
            return httpx.Response(200, json={"upload_id": "u-9", "complete": True})
        if request.method == "PUT" and "r2.example/a" in str(request.url):
            return httpx.Response(200)
        if request.method == "PUT" and "r2.example/b" in str(request.url):
            return httpx.Response(403)  # non-retryable
        return httpx.Response(404)

    up = Uploader(
        worker_url="https://w.example",
        worker_token="t",
        client_version="t",
        wingman_version="t",
        transport=httpx.MockTransport(handler),
    )
    result = up.upload([cand_a, cand_b], progress_cb=lambda _: None)
    assert result.succeeded_count == 1
    assert result.failed_count == 1
