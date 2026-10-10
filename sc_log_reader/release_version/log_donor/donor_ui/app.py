"""
SC_LogReader -- Log Donor API Server

FastAPI server that exposes REST endpoints for the standalone log donor
dashboard. Manages discovery of eligible logs, preview display, and
coordinating the upload job with progress tracking.

Author: Mallachi
"""

from __future__ import annotations

import logging
import secrets
import socket
import threading
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from log_donor.dedup import DedupStore
from log_donor.scanner import (
    LiveLogUnavailableError,
    discover_candidates,
    discover_candidates_with_caps,
)
from log_donor.types import Candidate, DiscoveryResult
from log_donor.ui_dialog import CONSENT_BODY, build_preview, format_summary_header
from log_donor.uploader import Uploader


logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR_RESOLVED = _STATIC_DIR.resolve()

_SESSION_HEADER = "X-Donor-Session"
_SESSION_META_PLACEHOLDER = "<!--DONOR_SESSION_META-->"

_IDLE_JOB: dict = {
    "phase": "idle",
    "started_at": None,
    "finished_at": None,
    "progress": {"done": 0, "total": 0},
    "result": None,
    "error": None,
}

_EMPTY_DISCOVERY = DiscoveryResult(
    candidates=[],
    already_uploaded_count=0,
    skipped_undersize_count=0,
    skipped_oversize_count=0,
    trimmed_count=0,
)


def _find_free_port(preferred: int, max_offset: int = 20) -> int:
    """Try preferred port first; if taken, increment up to max_offset times."""
    for offset in range(max_offset + 1):
        port = preferred + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return preferred  # fall back; uvicorn will surface the error


class DonorServer:
    """FastAPI server for the log donor dashboard."""

    def __init__(
        self,
        sc_root_provider: Callable[[], Path | None],
        store: DedupStore,
        worker_url_provider: Callable[[], str],
        worker_token_provider: Callable[[], str],
        client_version: str,
        wingman_version: str,
        port: int = 7864,
    ) -> None:
        self._sc_root_provider = sc_root_provider
        self._store = store
        self._worker_url_provider = worker_url_provider
        self._worker_token_provider = worker_token_provider
        self._client_version = client_version
        self._wingman_version = wingman_version
        self._port = port

        self._thread: threading.Thread | None = None
        self._server: uvicorn.Server | None = None

        self._lock = threading.Lock()
        self._job_state: dict = deepcopy(_IDLE_JOB)

        # Per-run session token. Required on state-changing requests
        # (X-Donor-Session header) so a page loaded from this server is the
        # only thing that can trigger an upload or reset.
        self._session_token = secrets.token_urlsafe(32)

        self._app = self._create_app()

    # ------------------------------------------------------------------
    # Request guards
    # ------------------------------------------------------------------

    def _allowed_hosts(self) -> set[str]:
        return {f"127.0.0.1:{self._port}", f"localhost:{self._port}"}

    def _check_session(self, request: Request) -> JSONResponse | None:
        """Return a 403 JSONResponse if the request lacks a valid session token, else None."""
        token = request.headers.get(_SESSION_HEADER, "")
        if not token or not secrets.compare_digest(token, self._session_token):
            return JSONResponse({"error": "invalid or missing session token"}, status_code=403)
        return None

    # ------------------------------------------------------------------
    # App construction
    # ------------------------------------------------------------------

    def _create_app(self) -> FastAPI:
        """Build the FastAPI application with all routes."""
        app = FastAPI(title="SC Log Donor", docs_url=None, redoc_url=None)

        # -- Host header check, applied to every request --
        # Defeats drive-by CSRF and DNS rebinding against the local server:
        # only requests that claim to target this exact host:port are served.

        @app.middleware("http")
        async def verify_host(request: Request, call_next):
            host = request.headers.get("host", "")
            if host not in self._allowed_hosts():
                return JSONResponse({"error": "forbidden host"}, status_code=403)
            return await call_next(request)

        # -- Health check --

        @app.get("/healthz")
        def healthz() -> HTMLResponse:
            return HTMLResponse("ok", status_code=200)

        # -- Preview --

        @app.get("/api/preview")
        def get_preview() -> JSONResponse:
            sc_root = self._sc_root_provider()
            if sc_root is None or not sc_root.exists():
                return JSONResponse(
                    {
                        "header": "Star Citizen root directory is not configured.",
                        "error": None,
                        "candidates": [],
                        "total_bytes": 0,
                        "per_install_counts": {},
                        "per_install_bytes": {},
                        "already_uploaded_count": 0,
                        "skipped_undersize_count": 0,
                        "skipped_oversize_count": 0,
                        "trimmed_count": 0,
                        "sc_root_configured": False,
                        "consent_text": CONSENT_BODY,
                    }
                )
            error: str | None = None
            try:
                result = discover_candidates_with_caps(sc_root, self._store)
            except LiveLogUnavailableError as exc:
                result = _EMPTY_DISCOVERY
                error = str(exc)
            except Exception as exc:
                logger.warning("preview scan failed: %s", exc)
                result = _EMPTY_DISCOVERY
                error = f"Scan failed: {exc}"

            summary = build_preview(result)
            header = error if error else format_summary_header(summary)

            return JSONResponse(
                {
                    "header": header,
                    "error": error,
                    "candidates": [
                        {
                            "sha256": c.sha256,
                            "renamed": c.renamed,
                            "install": c.install,
                            "size_bytes": c.size_bytes,
                            "handle": c.detected_handle or "unknown",
                        }
                        for c in summary.candidates
                    ],
                    "total_bytes": summary.total_bytes,
                    "per_install_counts": summary.per_install_counts,
                    "per_install_bytes": summary.per_install_bytes,
                    "already_uploaded_count": summary.already_uploaded_count,
                    "skipped_undersize_count": summary.skipped_undersize_count,
                    "skipped_oversize_count": summary.skipped_oversize_count,
                    "trimmed_count": summary.trimmed_count,
                    "sc_root_configured": True,
                    "consent_text": CONSENT_BODY,
                }
            )

        # -- Upload trigger --

        @app.post("/api/upload")
        async def post_upload(request: Request) -> JSONResponse:
            denied = self._check_session(request)
            if denied is not None:
                return denied

            try:
                body = await request.json()
            except Exception:
                body = {}
            sha256_list = body.get("sha256") if isinstance(body, dict) else None
            allowed_hashes = (
                {str(h) for h in sha256_list} if isinstance(sha256_list, list) else set()
            )

            with self._lock:
                if self._job_state["phase"] == "running":
                    return JSONResponse(
                        {"error": "upload already running"},
                        status_code=409,
                    )
                self._job_state = deepcopy(_IDLE_JOB)
                self._job_state["phase"] = "running"
                self._job_state["started_at"] = datetime.now(UTC).isoformat()

            t = threading.Thread(
                target=self._run_upload_job,
                args=(allowed_hashes,),
                name="donor-upload",
                daemon=True,
            )
            t.start()
            return JSONResponse({"phase": "running"}, status_code=202)

        # -- Status --

        @app.get("/api/status")
        def get_status() -> JSONResponse:
            with self._lock:
                snapshot = deepcopy(self._job_state)
            return JSONResponse(snapshot)

        # -- Reset (called by "Donate more logs" button) --

        @app.post("/api/reset")
        def reset_job(request: Request) -> JSONResponse:
            """Return the job state to idle so the next preview re-runs the scan.

            Refuses to reset while a job is actively running so we do not lose
            progress mid-upload. After reset the client typically reloads and
            hits /api/preview again, picking up any newly-rotated logbackups
            that were not yet donated.
            """
            denied = self._check_session(request)
            if denied is not None:
                return denied

            with self._lock:
                if self._job_state["phase"] == "running":
                    return JSONResponse(
                        {"error": "upload in progress"}, status_code=409
                    )
                self._job_state = deepcopy(_IDLE_JOB)
            return JSONResponse({"phase": "idle"})

        # -- Static / frontend --

        # No return type annotation on these routes: the Wingman runtime ships
        # a fastapi build that fails to introspect FileResponse | HTMLResponse
        # union annotations even with response_model=None. Returning Response
        # subclasses directly works fine; FastAPI just shouldn't see a union
        # in the type-hint slot.
        @app.get("/")
        def index():
            index_file = _STATIC_DIR / "index.html"
            if not index_file.is_file():
                return HTMLResponse(
                    "<html><body><p>Donor UI frontend not yet built (T10b pending)</p></body></html>",
                    status_code=200,
                )
            html = index_file.read_text(encoding="utf-8")
            html = html.replace(
                _SESSION_META_PLACEHOLDER,
                f'<meta name="donor-session" content="{self._session_token}">',
            )
            return HTMLResponse(html)

        # Explicit static file handler. We avoid fastapi.staticfiles because the
        # Wingman runtime ships a fastapi build without that submodule.
        @app.get("/static/{filename}")
        def static_file(filename: str):
            resolved = (_STATIC_DIR / filename).resolve()
            if resolved.parent != _STATIC_DIR_RESOLVED:
                return HTMLResponse("not found", status_code=404)
            if not resolved.is_file():
                return HTMLResponse("not found", status_code=404)
            return FileResponse(str(resolved))

        return app

    # ------------------------------------------------------------------
    # Upload job
    # ------------------------------------------------------------------

    def _on_progress(self, done: int) -> None:
        """Thread-safe progress update."""
        with self._lock:
            self._job_state["progress"]["done"] = done

    def _run_upload_job(self, allowed_hashes: set[str]) -> None:
        """Execute the full upload cycle in a background thread.

        Args:
            allowed_hashes: sha256 set from the preview the user consented to.
                Discovery is re-run (files may have rotated since the preview
                was rendered), but only candidates whose hash is in this set
                are ever uploaded, so the upload can never exceed what the
                user actually saw and confirmed.
        """
        sc_root = self._sc_root_provider()
        result: dict = {
            "upload_id": None,
            "succeeded_count": 0,
            "failed_count": 0,
            "total_bytes_uploaded": 0,
            "files": [],
            "top_level_error": None,
        }
        try:
            if sc_root is None or not sc_root.exists():
                raise ValueError("SC root is not configured or does not exist")

            candidates = discover_candidates(sc_root, self._store)
            candidates = [c for c in candidates if c.sha256 in allowed_hashes]

            with self._lock:
                self._job_state["progress"]["total"] = len(candidates)

            worker_url = self._worker_url_provider()
            worker_token = self._worker_token_provider()

            with Uploader(
                worker_url=worker_url,
                worker_token=worker_token,
                client_version=self._client_version,
                wingman_version=self._wingman_version,
            ) as uploader:
                upload_result = uploader.upload(
                    candidates,
                    progress_cb=self._on_progress,
                )

            # Record successes in the dedup store, matched by sha256 only.
            # (renamed is a display string derived from a detected player
            # handle -- it is not unique across installs and must never be
            # used to identify which candidate a Worker result belongs to.)
            by_hash: dict[str, Candidate] = {c.sha256: c for c in candidates}
            rows: list[tuple[str, str, str]] = []
            upload_id = upload_result.upload_id or ""
            for f in upload_result.files:
                if not f.succeeded or f.already_uploaded:
                    continue
                cand = by_hash.get(f.sha256)
                if cand is not None:
                    rows.append((f.sha256, str(cand.path), upload_id))
            if rows:
                self._store.record_many_uploaded(rows)

            result["upload_id"] = upload_result.upload_id
            result["succeeded_count"] = upload_result.succeeded_count
            result["failed_count"] = upload_result.failed_count
            result["total_bytes_uploaded"] = upload_result.total_bytes_uploaded
            result["files"] = [
                {
                    "renamed": f.renamed,
                    "succeeded": f.succeeded,
                    "already_uploaded": f.already_uploaded,
                    "error": f.error,
                }
                for f in upload_result.files
            ]
            if upload_result.error:
                result["top_level_error"] = upload_result.error

        except Exception as exc:
            logger.warning("upload job failed: %s", exc)
            result["top_level_error"] = str(exc)
            with self._lock:
                self._job_state["error"] = str(exc)

        finally:
            with self._lock:
                self._job_state["phase"] = "done"
                self._job_state["finished_at"] = datetime.now(UTC).isoformat()
                self._job_state["result"] = result

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the server in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            return

        self._port = _find_free_port(self._port)

        config = uvicorn.Config(
            self._app,
            host="127.0.0.1",
            port=self._port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)

        self._thread = threading.Thread(
            target=self._server.run,
            name="sc-log-donor-ui",
            daemon=True,
        )
        self._thread.start()
        logger.info("Donor UI server started on port %d", self._port)

    def stop(self) -> None:
        """Stop the server."""
        if self._server:
            self._server.should_exit = True
            self._server = None
        if self._thread:
            try:
                self._thread.join(timeout=3.0)
            except OSError:
                pass
            self._thread = None
        logger.info("Donor UI server stopped")

    @property
    def port(self) -> int:
        """Port the server is bound to."""
        return self._port

    @property
    def url(self) -> str:
        """Base URL for local browser access."""
        return f"http://127.0.0.1:{self._port}"

    @property
    def is_running(self) -> bool:
        """Whether the server thread is alive."""
        return self._thread is not None and self._thread.is_alive()
