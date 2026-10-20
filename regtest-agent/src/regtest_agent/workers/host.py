"""Worker process entry: `python -m regtest_agent.workers.host <kind>`.

Speaks JSON lines on the original stdout; legacy code's prints are redirected to
stderr (the worker log). Each request: {"id", "op", "args"} -> {"id", "ok", "result"|"error"}.
Ops may emit progress lines: {"id", "event": {...}}.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
import traceback

_OUT = None
_CUR = {"id": None}


def emit(**event) -> None:
    if _OUT is None or _CUR["id"] is None:
        return
    _OUT.write(json.dumps({"id": _CUR["id"], "event": event}, ensure_ascii=False, default=str) + "\n")
    _OUT.flush()


def main() -> None:
    global _OUT
    kind = sys.argv[1]
    _OUT = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    # legacy code calls site's exit(-1), which closes sys.stdin: read requests from a private fd
    inp = os.fdopen(os.dup(0), "r", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    sys.stdin = open(os.devnull, encoding="utf-8")
    t = time.time()
    try:
        ops = importlib.import_module(f"regtest_agent.workers.{kind}").setup()
    except BaseException as e:  # noqa: BLE001
        _OUT.write(json.dumps({"id": "__ready__", "ok": False, "error": f"{type(e).__name__}: {e}",
                               "trace": traceback.format_exc()[-6000:]}) + "\n")
        _OUT.flush()
        raise SystemExit(1)
    _OUT.write(json.dumps({"id": "__ready__", "ok": True, "ops": sorted(ops), "seconds": round(time.time() - t, 2)}) + "\n")
    _OUT.flush()
    for line in inp:
        if not line.strip():
            continue
        req = json.loads(line)
        _CUR["id"] = req["id"]
        t = time.time()
        try:
            fn = ops[req["op"]]
            out = {"id": req["id"], "ok": True, "result": fn(**(req.get("args") or {}))}
        except KeyboardInterrupt:
            raise
        except BaseException as e:  # noqa: BLE001 - legacy code calls exit(-1)
            out = {"id": req["id"], "ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-6000:]}
        out["seconds"] = round(time.time() - t, 3)
        _CUR["id"] = None
        _OUT.write(json.dumps(out, ensure_ascii=False, default=str) + "\n")
        _OUT.flush()


if __name__ == "__main__":
    main()
