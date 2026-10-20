"""SQLite persistence for threads, chat messages, events (SSE replay), runs and tool audit;
large step outputs are JSON files under .runtime/runs/<run_id>/."""
from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import Settings, get_settings

SCHEMA = """
create table if not exists threads(id text primary key, title text, created real, updated real, status text, meta text);
create table if not exists messages(id integer primary key autoincrement, thread_id text, role text, content text, cards text, created real);
create table if not exists events(seq integer primary key autoincrement, thread_id text, run_id text, type text, data text, created real);
create table if not exists runs(id text primary key, thread_id text, workflow text, domain text, status text, started real, ended real, plan text, summary text);
create table if not exists audit(id integer primary key autoincrement, run_id text, thread_id text, step text, tool text, status text, seconds real, attempts integer, detail text, created real);
create index if not exists ev_thread on events(thread_id, seq);
create index if not exists msg_thread on messages(thread_id, id);
create index if not exists audit_run on audit(run_id);
"""


def _dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


class Store:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.db = sqlite3.connect(self.s.db_path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("pragma journal_mode=wal")
        self.db.executescript(SCHEMA)
        self.lock = threading.RLock()
        self.cond = threading.Condition()

    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def _x(self, sql: str, args: tuple = ()) -> int:
        with self.lock:
            return self.db.execute(sql, args).lastrowid

    # threads ---------------------------------------------------------------
    def create_thread(self, title: str = "新对话") -> dict:
        tid = uuid.uuid4().hex[:12]
        now = time.time()
        self._x("insert into threads values(?,?,?,?,?,?)", (tid, title, now, now, "idle", "{}"))
        return self.thread(tid)

    def thread(self, tid: str) -> dict | None:
        r = self._q("select * from threads where id=?", (tid,))
        if not r:
            return None
        d = dict(r[0])
        d["meta"] = json.loads(d["meta"] or "{}")
        return d

    def threads(self) -> list[dict]:
        return [dict(r) | {"meta": json.loads(r["meta"] or "{}")} for r in self._q("select * from threads order by updated desc")]

    def update_thread(self, tid: str, **kw) -> None:
        if "meta" in kw:
            kw["meta"] = _dumps(kw["meta"])
        kw["updated"] = time.time()
        cols = ",".join(f"{k}=?" for k in kw)
        self._x(f"update threads set {cols} where id=?", (*kw.values(), tid))

    def delete_thread(self, tid: str) -> None:
        for r in self._q("select id from runs where thread_id=?", (tid,)):
            shutil.rmtree(self.s.runs_dir / r["id"], ignore_errors=True)
        for t in ("messages", "events", "audit"):
            self._x(f"delete from {t} where thread_id=?", (tid,))
        self._x("delete from runs where thread_id=?", (tid,))
        self._x("delete from threads where id=?", (tid,))

    # messages --------------------------------------------------------------
    def add_message(self, tid: str, role: str, content: str, cards: list | None = None) -> dict:
        mid = self._x("insert into messages(thread_id, role, content, cards, created) values(?,?,?,?,?)",
                      (tid, role, content, _dumps(cards or []), time.time()))
        msg = {"id": mid, "thread_id": tid, "role": role, "content": content, "cards": cards or [], "created": time.time()}
        self.event(tid, "message", msg)
        self.update_thread(tid)
        return msg

    def messages(self, tid: str) -> list[dict]:
        return [dict(r) | {"cards": json.loads(r["cards"] or "[]")} for r in self._q("select * from messages where thread_id=? order by id", (tid,))]

    # events ----------------------------------------------------------------
    def event(self, tid: str, type_: str, data: Any, run_id: str = "") -> int:
        seq = self._x("insert into events(thread_id, run_id, type, data, created) values(?,?,?,?,?)",
                      (tid, run_id, type_, _dumps(data), time.time()))
        with self.cond:
            self.cond.notify_all()
        return seq

    def events(self, tid: str, after: int = 0, limit: int = 500) -> list[dict]:
        rows = self._q("select * from events where thread_id=? and seq>? order by seq limit ?", (tid, after, limit))
        return [{"seq": r["seq"], "type": r["type"], "run_id": r["run_id"], "data": json.loads(r["data"]), "ts": r["created"]} for r in rows]

    def last_seq(self, tid: str) -> int:
        r = self._q("select max(seq) as m from events where thread_id=?", (tid,))
        return int(r[0]["m"] or 0)

    def wait(self, timeout: float) -> None:
        with self.cond:
            self.cond.wait(timeout)

    # runs ------------------------------------------------------------------
    def create_run(self, tid: str, workflow: str, domain: str, plan: dict) -> str:
        rid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self._x("insert into runs values(?,?,?,?,?,?,?,?,?)", (rid, tid, workflow, domain, "running", time.time(), None, _dumps(plan), "{}"))
        (self.s.runs_dir / rid).mkdir(parents=True, exist_ok=True)
        return rid

    def finish_run(self, rid: str, status: str, summary: dict) -> None:
        self._x("update runs set status=?, ended=?, summary=? where id=?", (status, time.time(), _dumps(summary), rid))

    def update_run(self, rid: str, **kw) -> None:
        for k in ("plan", "summary"):
            if k in kw:
                kw[k] = _dumps(kw[k])
        cols = ",".join(f"{k}=?" for k in kw)
        self._x(f"update runs set {cols} where id=?", (*kw.values(), rid))

    def run(self, rid: str) -> dict | None:
        r = self._q("select * from runs where id=?", (rid,))
        if not r:
            return None
        d = dict(r[0])
        d["plan"], d["summary"] = json.loads(d["plan"] or "{}"), json.loads(d["summary"] or "{}")
        return d

    def runs(self, tid: str | None = None) -> list[dict]:
        rows = self._q("select * from runs where thread_id=? order by started desc", (tid,)) if tid else \
            self._q("select * from runs order by started desc limit 200")
        return [dict(r) | {"plan": json.loads(r["plan"] or "{}"), "summary": json.loads(r["summary"] or "{}")} for r in rows]

    # audit -----------------------------------------------------------------
    def audit(self, rid: str, tid: str, step: str, tool: str, status: str, seconds: float, attempts: int, detail: Any) -> None:
        self._x("insert into audit(run_id, thread_id, step, tool, status, seconds, attempts, detail, created) values(?,?,?,?,?,?,?,?,?)",
                (rid, tid, step, tool, status, seconds, attempts, _dumps(detail), time.time()))

    def audits(self, rid: str) -> list[dict]:
        return [dict(r) | {"detail": json.loads(r["detail"] or "null")} for r in self._q("select * from audit where run_id=? order by id", (rid,))]

    # artifacts -------------------------------------------------------------
    def art_path(self, rid: str, name: str) -> Path:
        return self.s.runs_dir / rid / f"{name}.json"

    def save(self, rid: str, name: str, data: Any) -> str:
        p = self.art_path(rid, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_dumps(data), encoding="utf-8")
        return name

    def load(self, rid: str, name: str, default: Any = None) -> Any:
        p = self.art_path(rid, name)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))

    def artifacts(self, rid: str) -> list[dict]:
        d = self.s.runs_dir / rid
        if not d.exists():
            return []
        return [{"name": p.stem, "bytes": p.stat().st_size} for p in sorted(d.glob("*.json"))]


_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store
