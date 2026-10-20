"""Agent-side handle for long-lived legacy workers (one subprocess per repo)."""
from __future__ import annotations

import itertools
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..config import ROOT, Settings, get_settings

KINDS = ("l4f", "care", "raft")
TITLES = {"l4f": "LLM4Fin", "care": "CARE", "raft": "RAFT"}


class WorkerError(RuntimeError):
    def __init__(self, msg: str, trace: str = ""):
        super().__init__(msg)
        self.trace = trace


class Worker:
    def __init__(self, kind: str, settings: Settings):
        self.kind, self.s = kind, settings
        self.proc: subprocess.Popen | None = None
        self.q: queue.Queue = queue.Queue()
        self.lock = threading.Lock()
        self.ids = itertools.count(1)
        self.info: dict = {"state": "stopped"}

    def _env(self) -> dict:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        env.update(HANLP_HOME=str(self.s.hanlp_home), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                   TOKENIZERS_PARALLELISM="false", PYTHONUNBUFFERED="1", PYTHONWARNINGS="ignore",
                   REGTEST_RUNTIME=str(self.s.runtime), REGTEST_MODEL_DIR=str(self.s.model_dir), REGTEST_HANLP_HOME=str(self.s.hanlp_home))
        return env

    def _reader(self, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            try:
                self.q.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        self.q.put({"id": "__eof__"})

    def start(self, timeout: float = 600) -> dict:
        if self.proc and self.proc.poll() is None:
            return self.info
        log = open(self.s.logs_dir / f"worker_{self.kind}.log", "a", encoding="utf-8")
        self.q = queue.Queue()
        self.info = {"state": "starting", "since": time.time()}
        self.proc = subprocess.Popen([self.s.worker_python, "-u", "-m", "regtest_agent.workers.host", self.kind],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
                                     encoding="utf-8", env=self._env(), cwd=str(ROOT), bufsize=1)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        msg = self._wait("__ready__", timeout, None)
        if not msg.get("ok"):
            self.info = {"state": "error", "error": msg.get("error")}
            raise WorkerError(f"{TITLES[self.kind]} worker failed to start: {msg.get('error')}", msg.get("trace", ""))
        self.info = {"state": "ready", "ops": msg.get("ops", []), "load_seconds": msg.get("seconds")}
        return self.info

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None
        self.info = {"state": "stopped"}

    def _wait(self, rid: Any, timeout: float, on_event: Callable[[dict], None] | None) -> dict:
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0:
                self.stop()
                raise WorkerError(f"{TITLES[self.kind]} worker timed out after {timeout:.0f}s")
            try:
                msg = self.q.get(timeout=min(left, 5))
            except queue.Empty:
                if self.proc is None or self.proc.poll() is not None:
                    raise WorkerError(f"{TITLES[self.kind]} worker exited (code {self.proc.poll() if self.proc else '?'})")
                continue
            if msg.get("id") == "__eof__":
                raise WorkerError(f"{TITLES[self.kind]} worker exited unexpectedly; see .runtime/logs/worker_{self.kind}.log")
            if msg.get("id") != rid:
                continue
            if "event" in msg:
                if on_event:
                    on_event(msg["event"])
                continue
            return msg

    def call(self, op: str, args: dict | None = None, *, on_event: Callable[[dict], None] | None = None,
             timeout: float | None = None, retries: int | None = None) -> Any:
        retries = self.s.tool_retries if retries is None else retries
        last: Exception | None = None
        for i in range(retries + 1):
            with self.lock:
                try:
                    self.start()
                    rid = next(self.ids)
                    self.proc.stdin.write(json.dumps({"id": rid, "op": op, "args": args or {}}, ensure_ascii=False) + "\n")
                    self.proc.stdin.flush()
                    msg = self._wait(rid, timeout or self.s.worker_timeout, on_event)
                except (WorkerError, BrokenPipeError, OSError) as e:
                    last = e
                    self.stop()
                    time.sleep(min(10, 1.5 * 2 ** i))
                    continue
            if msg.get("ok"):
                return msg.get("result")
            raise WorkerError(msg.get("error", "unknown error"), msg.get("trace", ""))
        raise WorkerError(f"{TITLES[self.kind]} worker unavailable: {last}")


class Pool:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.workers = {k: Worker(k, self.s) for k in KINDS}

    def __getitem__(self, kind: str) -> Worker:
        return self.workers[kind]

    def warmup(self, kinds=KINDS) -> None:
        def go(k):
            try:
                self.workers[k].start()
            except Exception as e:  # noqa: BLE001
                self.workers[k].info = {"state": "error", "error": str(e)}
        for k in kinds:
            threading.Thread(target=go, args=(k,), daemon=True).start()

    def status(self) -> dict:
        return {k: {"title": TITLES[k], **{x: y for x, y in w.info.items() if x != "ops"}} for k, w in self.workers.items()}

    def close(self) -> None:
        for w in self.workers.values():
            w.stop()


_pool: Pool | None = None


def get_pool() -> Pool:
    global _pool
    if _pool is None:
        _pool = Pool()
    return _pool
