"""The background batcher (S-1) — OBSERVE-ONLY by construction.

X-01 at the code level: this never sits in the customer's request path.
`record()` enqueues into a BOUNDED buffer and returns immediately; it never
blocks, never raises into caller code, and drops (counted) rather than grow
unboundedly. A background daemon thread flushes on an interval or when the
buffer fills, POSTing to <host>/api/v1/ingest with stdlib urllib (no new
dependency; a customer using only the SDK pulls nothing heavy). Network
failures are swallowed — the SDK NEVER retry-storms and NEVER surfaces an
error into the customer's process. atexit flushes the tail so a short
script still ships its last calls.

FR-26: each batch carries an Idempotency-Key (a hash of its contents), so
a duplicated flush is deduped server-side, never double-counted.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import threading
import urllib.error
import urllib.request
from collections import deque
from typing import Any

import structlog

log = structlog.get_logger("tokenops_cost_auditor.sdk")


class Batcher:
    def __init__(
        self,
        host: str,
        api_key: str,
        *,
        flush_interval: float = 5.0,
        batch_size: int = 500,
        max_queue: int = 10_000,
        timeout: float = 10.0,
    ) -> None:
        self._url = f"{host.rstrip('/')}/api/v1/ingest"
        self._key = api_key
        self._flush_interval = flush_interval
        self._batch_size = batch_size
        self._timeout = timeout
        self._queue: deque[dict[str, Any]] = deque(maxlen=max_queue)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._closed = False
        self.dropped = 0  # observability: records shed under backpressure
        self.shipped = 0
        self._thread = threading.Thread(
            target=self._run, name="tokenops-cost-auditor-sdk", daemon=True
        )
        self._thread.start()
        atexit.register(self.close)

    def record(self, rec: dict[str, Any]) -> None:
        """Enqueue one usage record. NEVER blocks, NEVER raises (X-01)."""
        if self._closed:
            return
        with self._lock:
            if len(self._queue) >= (self._queue.maxlen or 0):
                self.dropped += 1  # bounded buffer full — shed, never block
                return
            self._queue.append(rec)
            if len(self._queue) >= self._batch_size:
                self._wake.set()

    def _drain(self, limit: int) -> list[dict[str, Any]]:
        with self._lock:
            out = [self._queue.popleft() for _ in range(min(limit, len(self._queue)))]
        return out

    def _post(self, batch: list[dict[str, Any]]) -> None:
        body = json.dumps({"records": batch}).encode()
        key = hashlib.sha256(body).hexdigest()  # FR-26 idempotency
        req = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
                "Idempotency-Key": key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                resp.read()
            self.shipped += len(batch)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # OBSERVE-ONLY: a dead endpoint must never break or slow the
            # customer's app, and must never retry-storm. Drop and move on.
            self.dropped += len(batch)
            log.debug("sdk.ship_failed", error=str(exc)[:120], dropped=len(batch))

    def _run(self) -> None:
        while not self._closed:
            self._wake.wait(timeout=self._flush_interval)
            self._wake.clear()
            while True:
                batch = self._drain(self._batch_size)
                if not batch:
                    break
                self._post(batch)

    def flush(self) -> None:
        """Ship everything queued now (best-effort)."""
        while True:
            batch = self._drain(self._batch_size)
            if not batch:
                break
            self._post(batch)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._wake.set()
        self.flush()
