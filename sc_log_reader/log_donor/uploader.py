"""Coordinates the handshake with the sc-log-donate Worker and R2 PUTs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

import httpx

from log_donor.types import Candidate, FileUploadResult, UploadResult


logger = logging.getLogger(__name__)


@dataclass
class _BeginFileResult:
    sha256: str
    put_url: str | None
    key: str
    already_uploaded: bool


@dataclass
class _BeginResponse:
    upload_id: str
    files: list[_BeginFileResult]


class Uploader:
    """Single-use uploader for one donation cycle.

    Use one instance per click of "Donate logs".
    """

    PUT_TIMEOUT_S = 120.0
    JSON_TIMEOUT_S = 30.0
    MAX_PUT_RETRIES = 3

    def __init__(
        self,
        worker_url: str,
        worker_token: str,
        client_version: str,
        wingman_version: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._worker_url = worker_url.rstrip("/")
        self._worker_token = worker_token
        self._client_version = client_version
        self._wingman_version = wingman_version
        self._client = httpx.Client(transport=transport, timeout=self.JSON_TIMEOUT_S)

    def __enter__(self) -> "Uploader":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _begin(self, candidates: list[Candidate]) -> _BeginResponse:
        """Send the upload manifest to the Worker and return the parsed response.

        Args:
            candidates: List of Candidate files to register for upload.

        Returns:
            _BeginResponse containing the upload_id and per-file results.

        Raises:
            PermissionError: If the Worker returns 401 (token rejected).
            httpx.HTTPStatusError: If the Worker returns any other 4xx/5xx.
            ValueError: If the Worker returns a non-JSON body on 2xx.
        """
        body = {
            "client_version": self._client_version,
            "wingman_version": self._wingman_version,
            "files": [
                {
                    "original_name": c.path.name,
                    "renamed": c.renamed,
                    "install": c.install,
                    "game_version": c.game_version,
                    "size_bytes": c.size_bytes,
                    "sha256": c.sha256,
                }
                for c in candidates
            ],
        }
        res = self._client.post(
            f"{self._worker_url}/upload/begin",
            json=body,
            headers={"X-Donor-Token": self._worker_token},
        )
        if res.status_code == 401:
            raise PermissionError("Worker rejected token")
        res.raise_for_status()
        try:
            payload = res.json()
        except ValueError as e:
            logger.error("worker returned non-JSON body: %s", e)
            raise ValueError("Worker returned invalid JSON") from e
        files = [
            _BeginFileResult(
                sha256=f["sha256"],
                put_url=f.get("put_url"),
                key=f["key"],
                already_uploaded=bool(f.get("already_uploaded")),
            )
            for f in payload["files"]
        ]
        return _BeginResponse(upload_id=payload["upload_id"], files=files)

    def _put_file(
        self,
        candidate: Candidate,
        put_url: str,
        sleep: Callable[[float], None] = time.sleep,
    ) -> bool:
        """PUT one file to R2. Returns True on success.

        Retries on 408/425/429/5xx and network errors up to MAX_PUT_RETRIES,
        with exponential backoff (2^attempt seconds).

        Args:
            candidate: The Candidate whose path will be PUT.
            put_url: The presigned R2 URL minted by the Worker.
            sleep: Sleep function (injected for test speed).

        Returns:
            True if the file was successfully PUT (any 2xx). False on
            non-retryable HTTP errors or after exhausting retries.
        """
        last_attempt = self.MAX_PUT_RETRIES - 1
        for attempt in range(self.MAX_PUT_RETRIES):
            try:
                # Stream the file to httpx rather than reading it fully into
                # memory; large Game.log files (backups can run tens of MB)
                # would otherwise be buffered whole on every retry attempt.
                with candidate.path.open("rb") as fh:
                    res = self._client.put(
                        put_url,
                        content=fh,
                        timeout=self.PUT_TIMEOUT_S,
                    )
                if 200 <= res.status_code < 300:
                    return True
                if res.status_code in (408, 425, 429) or res.status_code >= 500:
                    if attempt < last_attempt:
                        logger.info(
                            "PUT %s got %s, retrying (attempt %d)",
                            candidate.renamed, res.status_code, attempt + 1,
                        )
                        sleep(2 ** attempt)
                    continue
                # Non-retryable
                logger.warning(
                    "PUT %s failed with %s, not retrying",
                    candidate.renamed, res.status_code,
                )
                return False
            except httpx.HTTPError as e:
                if attempt < last_attempt:
                    logger.info(
                        "PUT %s network error: %s, retrying (attempt %d)",
                        candidate.renamed, e, attempt + 1,
                    )
                    sleep(2 ** attempt)
        logger.warning(
            "PUT %s gave up after %d attempts", candidate.renamed, self.MAX_PUT_RETRIES
        )
        return False

    def upload(
        self,
        candidates: list[Candidate],
        progress_cb: Callable[[int], None],
    ) -> UploadResult:
        """Run a full begin → PUTs → complete cycle for the given candidates."""
        result = UploadResult(upload_id=None)
        if not candidates:
            return result

        try:
            begin = self._begin(candidates)
        except PermissionError:
            result.error = "Worker rejected token"
            return result
        except httpx.HTTPError as e:
            result.error = f"Worker unreachable: {e}"
            return result
        except ValueError as e:
            result.error = f"Invalid Worker response: {e}"
            return result
        result.upload_id = begin.upload_id

        # Build sha256 -> Candidate lookup
        by_hash: dict[str, Candidate] = {c.sha256: c for c in candidates}

        done = 0
        for f in begin.files:
            cand = by_hash.get(f.sha256)
            if cand is None:
                logger.debug(
                    "Worker begin-response referenced unknown sha256 %s", f.sha256
                )
                continue
            if f.already_uploaded:
                result.files.append(
                    FileUploadResult(
                        sha256=f.sha256,
                        renamed=cand.renamed,
                        succeeded=True,
                        already_uploaded=True,
                    )
                )
                done += 1
                progress_cb(done)
                continue
            if f.put_url is None:
                result.files.append(
                    FileUploadResult(
                        sha256=f.sha256,
                        renamed=cand.renamed,
                        succeeded=False,
                        already_uploaded=False,
                        error="no put_url in Worker response",
                    )
                )
                done += 1
                progress_cb(done)
                continue
            ok = self._put_file(cand, f.put_url)
            if ok:
                result.total_bytes_uploaded += cand.size_bytes
            result.files.append(
                FileUploadResult(
                    sha256=f.sha256,
                    renamed=cand.renamed,
                    succeeded=ok,
                    already_uploaded=False,
                    error=None if ok else "PUT failed after retries",
                )
            )
            done += 1
            progress_cb(done)

        # Candidates the Worker's begin-response silently dropped never get a
        # PUT attempt above. Record them as failed so progress still reaches
        # len(candidates) instead of stalling short of the total.
        returned_hashes = {f.sha256 for f in begin.files}
        for cand in candidates:
            if cand.sha256 in returned_hashes:
                continue
            logger.warning(
                "candidate %s missing from Worker begin-response", cand.renamed
            )
            result.files.append(
                FileUploadResult(
                    sha256=cand.sha256,
                    renamed=cand.renamed,
                    succeeded=False,
                    already_uploaded=False,
                    error="missing from Worker begin-response",
                )
            )
            done += 1
            progress_cb(done)

        # Always attempt /upload/complete if anything was attempted, so the
        # Worker can finalize what it can.
        try:
            self._complete(begin.upload_id)
        except httpx.HTTPError as e:
            logger.warning(
                "/upload/complete failed for %s: %s (server-side reconciler will sweep)",
                begin.upload_id, e,
            )
            # Not fatal - local state is still correct for what succeeded.

        return result

    def _complete(self, upload_id: str) -> None:
        res = self._client.post(
            f"{self._worker_url}/upload/complete",
            json={"upload_id": upload_id},
            headers={"X-Donor-Token": self._worker_token},
        )
        res.raise_for_status()
