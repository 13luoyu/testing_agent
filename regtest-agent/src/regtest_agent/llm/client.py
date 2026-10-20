"""OpenAI-compatible LLM client: retries with exponential backoff, input truncation,
schema-constrained JSON (server-side lm-format-enforcer) + validation/repair prompt,
and a configurable thread pool for fan-out."""
from __future__ import annotations

import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx
import jsonschema

from ..config import Settings, get_settings


class LLMError(RuntimeError):
    pass


@dataclass
class Call:
    kind: str
    model: str
    ok: bool
    seconds: float
    prompt_chars: int
    output_chars: int
    attempts: int
    repairs: int = 0
    truncated: bool = False
    error: str = ""


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """Keep head and tail of over-long input instead of failing."""
    if len(text) <= limit:
        return text, False
    head = int(limit * 0.7)
    tail = limit - head
    return f"{text[:head]}\n……[中间省略 {len(text) - limit} 字]……\n{text[-tail:]}", True


def strip_fences(text: str) -> str:
    t = text.strip()
    m = re.search(r"```(?:json|plantuml|txt|text)?\s*\n(.*?)```", t, re.S)
    return m.group(1).strip() if m else t


def extract_json(text: str) -> Any:
    t = strip_fences(text)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for o, c in (("{", "}"), ("[", "]")):
        i, j = t.find(o), t.rfind(c)
        if 0 <= i < j:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON object found")


@dataclass
class LLM:
    settings: Settings = field(default_factory=get_settings)
    on_call: Callable[[Call], None] | None = None

    def __post_init__(self):
        s = self.settings
        self._http = httpx.Client(timeout=httpx.Timeout(s.llm_timeout, connect=10))
        self._pool = ThreadPoolExecutor(max_workers=max(1, s.llm_threads), thread_name_prefix="llm")
        self._lock = threading.Lock()
        self.calls: list[Call] = []

    # -- transport ---------------------------------------------------------
    def _endpoints(self) -> list[tuple[str, str, str]]:
        s = self.settings
        eps = [(s.llm_base_url, s.llm_model, s.llm_api_key)]
        if s.fallback_base_url and s.fallback_model and Path(s.fallback_key_file).exists():
            eps.append((s.fallback_base_url, s.fallback_model, Path(s.fallback_key_file).read_text().strip()))
        return eps

    def _post(self, body: dict) -> tuple[str, str, int]:
        last = None
        attempts = 0
        for base, model, key in self._endpoints():
            for i in range(self.settings.llm_retries):
                attempts += 1
                try:
                    r = self._http.post(f"{base.rstrip('/')}/chat/completions", json={**body, "model": model},
                                        headers={"Authorization": f"Bearer {key}"})
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
                    if r.status_code >= 400:
                        raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
                    msg = r.json()["choices"][0]["message"]
                    return msg.get("content") or "", model, attempts
                except (httpx.HTTPError, LLMError, KeyError, ValueError) as e:
                    last = e
                    if isinstance(e, LLMError) and "HTTP 4" in str(e) and "HTTP 429" not in str(e):
                        break
                    time.sleep(min(30.0, 0.8 * 2 ** i) + random.random() * 0.3)
        raise LLMError(f"LLM unavailable after {attempts} attempts: {last}")

    def _record(self, c: Call) -> None:
        with self._lock:
            self.calls.append(c)
        if self.on_call:
            try:
                self.on_call(c)
            except Exception:
                pass

    def _prep(self, messages: list[dict]) -> tuple[list[dict], bool, int]:
        lim = self.settings.llm_max_input_chars
        out, cut = [], False
        per = max(2000, lim // max(1, len(messages)))
        for m in messages:
            text, t = truncate(m["content"], per if len(messages) > 1 else lim)
            cut |= t
            out.append({"role": m["role"], "content": text})
        return out, cut, sum(len(m["content"]) for m in out)

    # -- public API ----------------------------------------------------------
    def chat(self, messages: list[dict], *, temperature: float = 0.0, max_tokens: int = 2048,
             stop: list[str] | None = None, kind: str = "chat") -> str:
        msgs, cut, n = self._prep(messages)
        body = {"messages": msgs, "temperature": temperature, "max_tokens": max_tokens}
        if stop:
            body["stop"] = stop
        t = time.time()
        try:
            text, model, att = self._post(body)
        except LLMError as e:
            self._record(Call(kind, "", False, time.time() - t, n, 0, self.settings.llm_retries, truncated=cut, error=str(e)))
            raise
        self._record(Call(kind, Path(model).name, True, time.time() - t, n, len(text), att, truncated=cut))
        return text

    def json(self, messages: list[dict], schema: dict, *, temperature: float = 0.0, max_tokens: int = 1500,
             kind: str = "json") -> Any:
        """Constrained decoding + jsonschema validation + repair prompt."""
        msgs, cut, n = self._prep(messages)
        body = {"messages": msgs, "temperature": temperature, "max_tokens": max_tokens,
                "response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}}
        t = time.time()
        repairs, err, att_total = 0, "", 0
        for r in range(self.settings.llm_repairs + 1):
            try:
                text, model, att = self._post(body)
            except LLMError as e:
                self._record(Call(kind, "", False, time.time() - t, n, 0, att_total, repairs, cut, str(e)))
                raise
            att_total += att
            try:
                obj = extract_json(text)
                jsonschema.validate(obj, schema)
                self._record(Call(kind, Path(model).name, True, time.time() - t, n, len(text), att_total, repairs, cut))
                return obj
            except (ValueError, jsonschema.ValidationError) as e:
                err = str(e).split("\n")[0][:300]
                repairs += 1
                body = {**body, "messages": msgs + [
                    {"role": "assistant", "content": text[:4000]},
                    {"role": "user", "content": f"上面的输出不符合要求的JSON结构：{err}。请只输出修正后的、完全符合schema的JSON，不要输出其他内容。"}]}
        self._record(Call(kind, "", False, time.time() - t, n, 0, att_total, repairs, cut, err))
        raise LLMError(f"invalid JSON after {repairs} repairs: {err}")

    def map(self, fn: Callable[[Any], Any], items: Iterable[Any]) -> list[Any]:
        """Run fn over items on the configured thread pool, preserving order; errors are returned as exceptions."""
        def safe(x):
            try:
                return fn(x)
            except Exception as e:  # noqa: BLE001
                return e
        return list(self._pool.map(safe, list(items)))

    def health(self) -> dict:
        base = self.settings.llm_base_url.rstrip("/").removesuffix("/v1")
        try:
            r = self._http.get(f"{base}/health", timeout=3)
            return {"ok": r.status_code == 200, "url": self.settings.llm_base_url, "model": Path(self.settings.llm_model).name}
        except httpx.HTTPError as e:
            return {"ok": False, "url": self.settings.llm_base_url, "error": str(e)}


_default: LLM | None = None


def get_llm() -> LLM:
    global _default
    if _default is None:
        _default = LLM()
    return _default
