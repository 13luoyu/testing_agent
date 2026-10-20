"""Helpers shared by legacy worker modules (run inside worker subprocesses only)."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path


def enter_repo(root: Path, cwd: Path, extra_paths: list[Path] = ()) -> None:
    for p in [root, *extra_paths]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    os.chdir(cwd)


def load_interface(path: Path, name: str, patches: list[tuple[str, str]]) -> dict:
    """Execute an original Flask interface.py with stub flask modules so its endpoint
    functions can be called directly. `patches` are exact (old, new) source replacements
    that only neutralise side effects (log files, upload dirs); each must match."""
    src = path.read_text(encoding="utf-8")
    for old, new in patches:
        if old not in src:
            raise RuntimeError(f"{path.name}: expected source fragment not found: {old[:60]!r}")
        src = src.replace(old, new)

    class _App:
        def __init__(self, *a, **k):
            self.config = {}

        def route(self, *a, **k):
            return lambda f: f

        def run(self, *a, **k):
            return None

    request = types.SimpleNamespace(json=None, files={})
    flask = types.ModuleType("flask")
    flask.Flask, flask.request, flask.Response = _App, request, object
    flask.jsonify = lambda *a, **k: a[0] if a else k
    cors = types.ModuleType("flask_cors")
    cors.CORS = lambda *a, **k: None
    saved = {k: sys.modules.get(k) for k in ("flask", "flask_cors")}
    sys.modules.update(flask=flask, flask_cors=cors)
    try:
        ns: dict = {"__name__": name, "__file__": str(path)}
        exec(compile(src, str(path), "exec"), ns)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    ns["_request"] = request
    return ns


def call_endpoint(ns: dict, fn: str, params: dict) -> dict:
    """Invoke an original endpoint function with `params` as request.json."""
    ns["_request"].json = params
    out = ns[fn]()
    if isinstance(out, tuple):
        out = out[0]
    if not isinstance(out, dict):
        raise RuntimeError(f"{fn}: unexpected response {type(out)}")
    if out.get("code") not in (200, "200"):
        raise RuntimeError(f"{fn} failed: {str(out.get('msg', ''))[-1500:]}")
    return out.get("data")
