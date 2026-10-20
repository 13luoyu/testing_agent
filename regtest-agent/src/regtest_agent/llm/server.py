"""Local OpenAI-compatible LLM server: mlx_lm.server + JSON-schema constrained decoding.

Runs in the `regtest-llm` env (mlx-lm, lm-format-enforcer). Requests carrying
`response_format={"type": "json_schema", "json_schema": {"schema": ...}}` (or
`{"type": "json_object"}`) are decoded under an lm-format-enforcer token mask.

    python -m regtest_agent.llm.server --model <path> --port 8800
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
from collections import OrderedDict
from pathlib import Path

os.environ.setdefault("LMFE_MAX_JSON_ARRAY_LENGTH", "2000")
os.environ.setdefault("LMFE_MAX_CONSECUTIVE_WHITESPACES", "24")

import mlx.core as mx
import numpy as np
from lmformatenforcer import JsonSchemaParser, TokenEnforcer
from lmformatenforcer.tokenenforcer import TokenEnforcerTokenizerData
from mlx_lm import server as srv
from tokenizers import Tokenizer

_SCHEMAS: "OrderedDict[int, dict]" = OrderedDict()
_LOCK = threading.Lock()
_STATE: dict = {}


def _register(schema: dict) -> int:
    with _LOCK:
        sid = _STATE.get("next", 1)
        _STATE["next"] = sid + 1
        _SCHEMAS[sid] = schema
        while len(_SCHEMAS) > 256:
            _SCHEMAS.popitem(last=False)
        return sid


def _tokenizer_data(model_dir: Path) -> TokenEnforcerTokenizerData:
    tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    cfg = json.loads((model_dir / "tokenizer_config.json").read_text(encoding="utf-8"))
    special = {int(k) for k, v in cfg.get("added_tokens_decoder", {}).items() if v.get("special")}
    vocab = tok.get_vocab_size(with_added_tokens=True)
    zero = tok.encode("0", add_special_tokens=False).ids[-1]
    regular = []
    for i in range(vocab):
        if i in special:
            continue
        after0 = tok.decode([zero, i], skip_special_tokens=False)[1:]
        plain = tok.decode([i], skip_special_tokens=False)
        regular.append((i, after0, len(after0) > len(plain)))
    eos = [t for t in (cfg.get("eos_token"), "<|im_end|>", "<|endoftext|>") if t]
    eos_ids = sorted({tok.token_to_id(t) for t in eos if tok.token_to_id(t) is not None})
    _STATE["eos"] = eos_ids
    return TokenEnforcerTokenizerData(regular, lambda ids: tok.decode(ids, skip_special_tokens=False), eos_ids, False, vocab)


class SchemaProcessor:
    """mlx logits processor: tokens = full context (prompt + generated)."""

    def __init__(self, data: TokenEnforcerTokenizerData, schema: dict | None):
        self.enf = TokenEnforcer(data, JsonSchemaParser(schema or None))
        self.start = None

    def __call__(self, tokens, logits):
        if self.start is None:
            self.start = int(tokens.shape[0]) if hasattr(tokens, "shape") else len(tokens)
        gen = tokens[self.start:].tolist() if hasattr(tokens, "tolist") else list(tokens)[self.start:]
        allowed = self.enf.get_allowed_tokens(gen).allowed_tokens or _STATE["eos"]
        mask = np.full(logits.shape[-1], -np.inf, dtype=np.float32)
        mask[[a for a in allowed if a < mask.shape[0]]] = 0.0
        return logits + mx.array(mask)


def _patch(model_dir: Path) -> None:
    data_box: dict = {}

    def data():
        if "d" not in data_box:
            data_box["d"] = _tokenizer_data(model_dir)
        return data_box["d"]

    orig_validate = srv.APIHandler.validate_model_parameters

    def validate(self):
        orig_validate(self)
        rf = self.body.get("response_format") or {}
        schema = None
        if rf.get("type") == "json_schema":
            schema = (rf.get("json_schema") or {}).get("schema") or {}
        elif rf.get("type") == "json_object":
            schema = {}
        if schema is not None:
            bias = dict(self.logit_bias or {})
            bias[-_register(schema)] = 0.0
            self.logit_bias = bias

    orig_make = srv._make_logits_processors

    def make(args):
        bias = dict(args.logits.logit_bias or {})
        sids = [k for k in bias if k < 0]
        for k in sids:
            bias.pop(k)
        args.logits.logit_bias = bias or None
        procs = list(orig_make(args) or [])
        for k in sids:
            procs.append(SchemaProcessor(data(), _SCHEMAS.get(-k)))
        return procs

    srv.APIHandler.validate_model_parameters = validate
    srv._make_logits_processors = make
    threading.Thread(target=data, daemon=True).start()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8800)
    p.add_argument("--decode-concurrency", type=int, default=4)
    p.add_argument("--prompt-concurrency", type=int, default=2)
    p.add_argument("--max-tokens", type=int, default=4096)
    a = p.parse_args()
    _patch(Path(a.model))
    sys.argv = ["mlx_lm.server", "--model", a.model, "--host", a.host, "--port", str(a.port),
                "--decode-concurrency", str(a.decode_concurrency), "--prompt-concurrency", str(a.prompt_concurrency),
                "--max-tokens", str(a.max_tokens), "--temp", "0.0"]
    logging.basicConfig(level=logging.INFO)
    srv.main()


if __name__ == "__main__":
    main()
