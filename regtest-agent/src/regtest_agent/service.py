"""Agent runtime: one background LangGraph run per thread, events persisted for SSE replay,
human-in-the-loop resume via Command(resume=...), cooperative cancellation."""
from __future__ import annotations

import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from langgraph.types import Command

from .agent.graph import Deps, compile_app
from .agent.memory import Memory
from .config import Settings, get_settings
from .knowledge import KnowledgeBase, l4f_builtin, raft_assets, seed_packs
from .llm import LLM
from .store import Store
from .workers.client import Pool

ALLOWED = {".pdf", ".txt", ".md", ".docx", ".json"}


class Service:
    def __init__(self, settings: Settings | None = None, warm: bool = True):
        self.s = settings or get_settings()
        self.store = Store(self.s)
        self.memory = Memory(self.s)
        self.kb = KnowledgeBase(self.s)
        self.pool = Pool(self.s)
        self.llm = LLM(self.s)
        self.app = compile_app(self.s)
        self.active: dict[str, threading.Thread] = {}
        self.cancel: dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        try:
            seeded = seed_packs(self.kb, l4f_builtin(self.s), raft_assets(self.s))
        except Exception as e:  # noqa: BLE001
            seeded = []
            print(f"[warn] knowledge seeding failed: {e}")
        self.seeded = seeded
        for t in self.store.threads():
            if t["status"] == "running":  # interrupted by a restart
                self.store.update_thread(t["id"], status="idle")
        if warm:
            self.pool.warmup()

    # files -----------------------------------------------------------------
    def save_upload(self, tid: str, name: str, data: bytes) -> dict:
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED:
            raise ValueError(f"不支持的文件类型 {ext}（支持 {', '.join(sorted(ALLOWED))}）")
        fid = uuid.uuid4().hex[:10]
        d = self.s.uploads_dir / tid
        d.mkdir(parents=True, exist_ok=True)
        safe = "".join(c for c in Path(name).name if c not in "/\\:*?\"<>|") or f"file{ext}"
        p = d / f"{fid}_{safe}"
        p.write_bytes(data)
        return {"id": fid, "name": safe, "path": str(p), "ext": ext, "size": len(data)}

    def add_local_file(self, tid: str, path: str) -> dict:
        p = Path(path)
        return self.save_upload(tid, p.name, p.read_bytes())

    # runs ------------------------------------------------------------------
    def _deps(self, tid: str) -> Deps:
        ev = self.cancel.setdefault(tid, threading.Event())
        return Deps(store=self.store, pool=self.pool, llm=self.llm, memory=self.memory, kb=self.kb, thread_id=tid,
                    emit=lambda t, data: self.store.event(tid, t, data, data.get("run_id", "") if isinstance(data, dict) else ""),
                    cancelled=ev.is_set, settings=self.s)

    def busy(self, tid: str) -> bool:
        t = self.active.get(tid)
        return bool(t and t.is_alive())

    def pending(self, tid: str) -> dict | None:
        cfg = {"configurable": {"thread_id": tid}}
        st = self.app.get_state(cfg)
        for task in st.tasks:
            for it in task.interrupts:
                return {"id": it.id, "value": it.value, "node": task.name}
        return None

    def send(self, tid: str, text: str, files: list[dict] | None = None) -> dict:
        """New user message: resumes a pending interrupt if there is one, otherwise starts a new task."""
        if self.busy(tid):
            raise RuntimeError("当前会话正在执行任务，请等待完成或先取消")
        files = files or []
        self.store.add_message(tid, "user", text, [{"type": "files", "files": [{k: f[k] for k in ("id", "name", "size")} for f in files]}] if files else [])
        th = self.store.thread(tid)
        if th and th["title"] == "新对话" and text.strip():
            self.store.update_thread(tid, title=text.strip()[:24])
        p = self.pending(tid)
        if p:
            return self.resume(tid, {"text": text, "files": files}, record=False)
        inp = {"request": text, "files": files, "history": []}
        return self._start(tid, inp)

    def resume(self, tid: str, answer: dict, record: bool = True) -> dict:
        if self.busy(tid):
            raise RuntimeError("当前会话正在执行任务")
        if not self.pending(tid):
            raise RuntimeError("没有等待回答的问题")
        if record:
            label = answer.get("label") or (f"保留 {len(answer['keep'])} 条：{'、'.join(answer['keep']) or '无'}" if answer.get("keep") is not None else "") \
                or answer.get("choice") or answer.get("text") or ""
            self.store.add_message(tid, "user", str(label), [])
        return self._start(tid, Command(resume=answer))

    def _start(self, tid: str, inp: Any) -> dict:
        self.cancel[tid] = threading.Event()
        deps = self._deps(tid)
        cfg = {"configurable": {"thread_id": tid}, "recursion_limit": 200}

        def run():
            self.store.update_thread(tid, status="running")
            self.store.event(tid, "status", {"status": "running"})
            try:
                for upd in self.app.stream(inp, cfg, context=deps, stream_mode="updates"):
                    for node, val in upd.items():
                        if node == "__interrupt__":
                            continue
                        self.store.event(tid, "node", {"node": node, "keys": sorted((val or {}).keys())})
                st = self.app.get_state(cfg)
                p = self.pending(tid)
                if p:
                    self.store.add_message(tid, "assistant", p["value"].get("question", "需要你的输入"), [{"type": "question", **p["value"], "interrupt_id": p["id"]}])
                    self.store.update_thread(tid, status="waiting")
                    self.store.event(tid, "status", {"status": "waiting"})
                    return
                vals = st.values
                cards = []
                if vals.get("run_id") and vals.get("plan"):
                    cards.append({"type": "result", "run_id": vals["run_id"], "workflow": vals["plan"].get("workflow"),
                                  "verdict": (vals.get("verification") or {}).get("verdict")})
                self.store.add_message(tid, "assistant", vals.get("reply") or "完成。", cards)
                self.store.update_thread(tid, status="idle", meta={**(self.store.thread(tid) or {}).get("meta", {}), "last_run": vals.get("run_id")})
                self.store.event(tid, "status", {"status": "idle", "run_id": vals.get("run_id")})
            except Exception as e:  # noqa: BLE001
                tb = traceback.format_exc()
                self.store.event(tid, "error", {"error": str(e), "trace": tb[-4000:]})
                self.store.add_message(tid, "assistant", f"任务异常终止：{e}", [{"type": "error", "trace": tb[-2000:]}])
                self.store.update_thread(tid, status="idle")
                self.store.event(tid, "status", {"status": "idle"})

        t = threading.Thread(target=run, daemon=True, name=f"agent-{tid}")
        with self.lock:
            self.active[tid] = t
        t.start()
        return {"started": True}

    def stop(self, tid: str) -> dict:
        ev = self.cancel.get(tid)
        if ev:
            ev.set()
        return {"cancelling": self.busy(tid)}

    def wait(self, tid: str, timeout: float = 3600) -> str:
        t = self.active.get(tid)
        if t:
            t.join(timeout)
        return (self.store.thread(tid) or {}).get("status", "")

    def delete_thread(self, tid: str) -> None:
        self.stop(tid)
        self.store.delete_thread(tid)
        shutil.rmtree(self.s.uploads_dir / tid, ignore_errors=True)

    def health(self) -> dict:
        return {"llm": self.llm.health(), "workers": self.pool.status(), "knowledge": [k["domain"] for k in self.kb.list()],
                "time": time.time()}

    def close(self) -> None:
        for ev in self.cancel.values():
            ev.set()
        self.pool.close()
