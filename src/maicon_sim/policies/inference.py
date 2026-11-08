"""One-frame latest-only inference worker, independent of control heartbeat."""
from __future__ import annotations

import queue
import threading


class LatestInference:
    def __init__(self, callback):
        self.callback = callback
        self.queue = queue.Queue(maxsize=1)
        self.latest = None
        self.submitted = 0
        self.in_flight = 0
        self.max_queue_size = 0
        self.dropped = 0
        self.processed = 0
        self.errors = 0
        self._metrics_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="participant-inference", daemon=True)
        self._thread.start()

    def submit(self, frame):
        if self._stop.is_set():
            raise RuntimeError("cannot submit to a closed inference worker")
        with self._metrics_lock:
            self.submitted += 1
        try:
            self.queue.put_nowait(frame)
        except queue.Full:
            try:
                self.queue.get_nowait()
                with self._metrics_lock:
                    self.dropped += 1
            except queue.Empty:
                pass
            self.queue.put_nowait(frame)
        with self._metrics_lock:
            self.max_queue_size = max(self.max_queue_size, self.queue.qsize())

    def _run(self):
        while not self._stop.is_set():
            try:
                frame = self.queue.get(timeout=.05)
            except queue.Empty:
                continue
            with self._metrics_lock:
                self.in_flight += 1
            try:
                value = self.callback(frame)
                with self._metrics_lock:
                    self.latest = value
                    self.processed += 1
            except Exception:
                # Error details are local diagnostic counters; no frame or token dump.
                with self._metrics_lock:
                    self.errors += 1
            finally:
                with self._metrics_lock:
                    self.in_flight -= 1

    def stats(self):
        with self._metrics_lock:
            return {"submitted": self.submitted, "processed": self.processed,
                    "dropped": self.dropped, "errors": self.errors,
                    "in_flight": self.in_flight, "pending": self.queue.qsize(),
                    "max_queue_size": self.max_queue_size}

    def close(self):
        self._stop.set()
        self._thread.join(timeout=5)
        if self._thread.is_alive():
            raise RuntimeError("participant inference callback did not stop within 5s")
