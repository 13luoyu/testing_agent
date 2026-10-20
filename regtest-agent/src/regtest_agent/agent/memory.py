"""Long-term memory on LangGraph's SqliteStore.

Namespaces:
  ("prefs",)              durable user preferences the user explicitly asked to remember
  ("episodes", thread)    one record per completed task (request, route, metrics, verdict)
  ("docs",)               document fingerprint -> runs that processed it (result reuse)
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any

from langgraph.store.sqlite import SqliteStore

from ..config import Settings, get_settings

PREF_KEYS = {
    "default_workflow": "默认工作流（auto / llm4fin / raft）",
    "judge_samples": "验证时抽检的需求数量",
    "max_rules": "RAFT 单次处理的最大规则数",
    "untestable_policy": "RAFT 不可测需求的处理（ask 询问 / strict 直接丢弃 / keep 全部保留待复核）",
    "minimize": "是否对膨胀的用例组做成对覆盖精简（on 开启 / off 保留全量，默认 off）",
    "language": "回答语言",
    "note": "其他偏好",
}


class Memory:
    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self.conn = sqlite3.connect(s.memory_path, check_same_thread=False, isolation_level=None)
        self.store = SqliteStore(self.conn)
        self.store.setup()

    # preferences -----------------------------------------------------------
    def prefs(self) -> dict:
        return {i.key: i.value.get("value") for i in self.store.search(("prefs",), limit=100)}

    def set_pref(self, key: str, value: Any, source: str = "") -> None:
        self.store.put(("prefs",), key, {"value": value, "source": source, "ts": time.time()})

    def forget_pref(self, key: str) -> None:
        self.store.delete(("prefs",), key)

    # episodes --------------------------------------------------------------
    def add_episode(self, thread_id: str, run_id: str, ep: dict) -> None:
        self.store.put(("episodes", thread_id), run_id, {**ep, "ts": time.time()})

    def episodes(self, thread_id: str | None = None, limit: int = 20) -> list[dict]:
        ns = ("episodes", thread_id) if thread_id else ("episodes",)
        items = self.store.search(ns, limit=200)
        items.sort(key=lambda i: -(i.value.get("ts") or 0))
        return [{"run_id": i.key, "thread_id": i.namespace[-1], **i.value} for i in items[:limit]]

    # documents -------------------------------------------------------------
    def link_doc(self, sha: str, name: str, run_id: str, workflow: str, status: str, params: dict | None = None) -> None:
        cur = self.store.get(("docs",), sha)
        runs = (cur.value.get("runs") if cur else []) or []
        runs = [r for r in runs if r["run_id"] != run_id] + [{"run_id": run_id, "workflow": workflow, "status": status,
                                                               "params": params or {}, "ts": time.time()}]
        self.store.put(("docs",), sha, {"name": name, "runs": runs[-20:]})

    def doc_runs(self, sha: str) -> list[dict]:
        cur = self.store.get(("docs",), sha)
        return (cur.value.get("runs") if cur else []) or []

    def docs(self) -> list[dict]:
        return [{"sha": i.key, **i.value} for i in self.store.search(("docs",), limit=500)]

    def recall(self, thread_id: str) -> dict:
        return {"prefs": self.prefs(), "recent": self.episodes(thread_id, 5), "global_recent": self.episodes(None, 5)}
