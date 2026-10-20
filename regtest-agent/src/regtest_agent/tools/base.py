"""Tool layer: every original workflow step / prompt is a registered, audited tool."""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from ..llm import LLM
from ..store import Store
from ..workers.client import Pool


class Cancelled(RuntimeError):
    pass


class ToolFailed(RuntimeError):
    pass


@dataclass
class ToolContext:
    run_id: str
    thread_id: str
    store: Store
    pool: Pool
    llm: LLM
    memory: Any = None
    step_id: str = ""
    emit: Callable[[str, dict], None] = lambda *_: None
    cancelled: Callable[[], bool] = lambda: False

    def save(self, name: str, data: Any) -> str:
        return self.store.save(self.run_id, name, data)

    def load(self, name: str, default: Any = None) -> Any:
        v = self.store.load(self.run_id, name, None)
        if v is None and default is None:
            raise ToolFailed(f"缺少上游产物: {name}")
        return default if v is None else v

    def has(self, name: str) -> bool:
        return self.store.art_path(self.run_id, name).exists()

    def progress(self, done: int, total: int, msg: str = "") -> None:
        self.emit("progress", {"step": self.step_id, "done": done, "total": total, "msg": msg})

    def check(self) -> None:
        if self.cancelled():
            raise Cancelled("任务已被用户取消")

    def worker(self, kind: str, op: str, args: dict | None = None, **kw) -> Any:
        self.check()
        return self.pool[kind].call(op, args, on_event=lambda e: self.emit("progress", {"step": self.step_id, **e}), **kw)

    def llm_map(self, fn: Callable[[Any], Any], items: list, label: str = "") -> list:
        """Thread-pool fan-out with progress + cancellation; exceptions are returned in place."""
        done = [0]
        total = len(items)

        def wrapped(x):
            if self.cancelled():
                raise Cancelled("任务已被用户取消")
            try:
                return fn(x)
            finally:
                done[0] += 1
                if total <= 20 or done[0] % max(1, total // 20) == 0 or done[0] == total:
                    self.progress(done[0], total, label)

        out = self.llm.map(wrapped, items)
        self.check()
        return out


@dataclass
class Tool:
    name: str
    title: str
    workflow: str
    origin: str
    backend: str
    desc: str
    fn: Callable[..., dict]
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    def info(self) -> dict:
        return {k: getattr(self, k) for k in ("name", "title", "workflow", "origin", "backend", "desc", "inputs", "outputs")}


REGISTRY: dict[str, Tool] = {}


def tool(name: str, title: str, workflow: str, origin: str, backend: str, desc: str,
         inputs: list[str] | None = None, outputs: list[str] | None = None):
    def deco(fn):
        REGISTRY[name] = Tool(name, title, workflow, origin, backend, desc, fn, inputs or [], outputs or [])
        return fn
    return deco


def run_tool(ctx: ToolContext, name: str, args: dict | None = None) -> dict:
    """Execute a registered tool with audit (tool, status, duration, LLM calls) and events."""
    t = REGISTRY[name]
    args = args or {}
    n_calls = len(ctx.llm.calls)
    t0 = time.time()
    ctx.emit("tool", {"step": ctx.step_id, "tool": name, "status": "running", "args": args})
    try:
        out = t.fn(ctx, **args) or {}
        status = out.get("status", "ok")
    except Cancelled:
        ctx.store.audit(ctx.run_id, ctx.thread_id, ctx.step_id, name, "cancelled", time.time() - t0, 1, {"args": args})
        raise
    except Exception as e:  # noqa: BLE001
        dt = time.time() - t0
        calls = ctx.llm.calls[n_calls:]
        ctx.store.audit(ctx.run_id, ctx.thread_id, ctx.step_id, name, "error", dt, 1,
                        {"args": args, "error": str(e), "trace": getattr(e, "trace", "") or traceback.format_exc()[-3000:],
                         "llm_calls": len(calls)})
        ctx.emit("tool", {"step": ctx.step_id, "tool": name, "status": "error", "seconds": round(dt, 2), "error": str(e)})
        raise ToolFailed(f"{t.title}（{name}）失败：{e}") from e
    dt = time.time() - t0
    calls = ctx.llm.calls[n_calls:]
    llm = {"calls": len(calls), "failed": sum(not c.ok for c in calls), "repairs": sum(c.repairs for c in calls),
           "truncated": sum(c.truncated for c in calls), "seconds": round(sum(c.seconds for c in calls), 1),
           "models": sorted({c.model for c in calls if c.model})}
    ctx.store.audit(ctx.run_id, ctx.thread_id, ctx.step_id, name, status, dt, 1,
                    {"args": args, "summary": out.get("summary"), "llm": llm if calls else None, "backend": t.backend})
    ctx.emit("tool", {"step": ctx.step_id, "tool": name, "status": status, "seconds": round(dt, 2), "summary": out.get("summary")})
    out.setdefault("summary", {})
    out["seconds"] = round(dt, 2)
    if calls:
        out["llm"] = llm
    return out
