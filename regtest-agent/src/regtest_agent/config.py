"""Runtime settings (env vars prefixed with REGTEST_, optional .env at project root)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _env(name: str, default: str) -> str:
    v = os.environ.get(f"REGTEST_{name}")
    return default if v in (None, "") else v


@dataclass
class Settings:
    runtime: Path
    llm4fin_root: Path
    care_root: Path
    raft_root: Path
    model_dir: Path
    hanlp_home: Path
    worker_python: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    llm_timeout: float
    llm_retries: int
    llm_threads: int
    llm_max_input_chars: int
    llm_repairs: int
    fallback_base_url: str
    fallback_model: str
    fallback_key_file: str
    raft_n: int
    raft_k: int
    raft_temps: list[float]
    raft_repairs: int
    testability_min_pass: int
    judge_samples: int
    worker_timeout: float
    tool_retries: int
    host: str
    port: int
    extra: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.runtime / "agent.db"

    @property
    def checkpoint_path(self) -> Path:
        return self.runtime / "checkpoints.db"

    @property
    def memory_path(self) -> Path:
        return self.runtime / "memory.db"

    @property
    def runs_dir(self) -> Path:
        return self.runtime / "runs"

    @property
    def uploads_dir(self) -> Path:
        return self.runtime / "uploads"

    @property
    def knowledge_dir(self) -> Path:
        return self.runtime / "knowledge"

    @property
    def logs_dir(self) -> Path:
        return self.runtime / "logs"

    def ensure_dirs(self) -> None:
        for p in (self.runtime, self.runs_dir, self.uploads_dir, self.knowledge_dir, self.logs_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv(ROOT / ".env")
    # absolute: workers run with the legacy repo as cwd, so a relative runtime would point elsewhere there
    runtime = Path(_env("RUNTIME", str(ROOT / ".runtime"))).expanduser().resolve()
    assets = Path(_env("ASSETS", str(ROOT / ".runtime"))).expanduser().resolve()  # models / HanLP (kept apart from state)
    s = Settings(
        runtime=runtime,
        llm4fin_root=Path(_env("LLM4FIN_ROOT", "/Users/bytedance/Desktop/code/test/intelligent-test")),
        care_root=Path(_env("CARE_ROOT", "/Users/bytedance/Desktop/code/test/CARE")),
        raft_root=Path(_env("RAFT_ROOT", "/Users/bytedance/Desktop/code/fse 2027/RAFT")),
        model_dir=Path(_env("MODEL_DIR", str(assets / "models" / "llm4fin"))),
        hanlp_home=Path(_env("HANLP_HOME", str(assets / "hanlp"))),
        worker_python=_env("WORKER_PYTHON", sys.executable),
        llm_base_url=_env("LLM_BASE_URL", "http://127.0.0.1:8800/v1"),
        llm_model=_env("LLM_MODEL", str(assets / "models" / "llm" / "Qwen3-30B-A3B-Instruct-2507-4bit")),
        llm_api_key=_env("LLM_API_KEY", "local"),
        llm_timeout=float(_env("LLM_TIMEOUT", "900")),
        llm_retries=int(_env("LLM_RETRIES", "4")),
        llm_threads=int(_env("LLM_THREADS", "4")),
        llm_max_input_chars=int(_env("LLM_MAX_INPUT_CHARS", "28000")),
        llm_repairs=int(_env("LLM_REPAIRS", "2")),
        fallback_base_url=_env("FALLBACK_BASE_URL", ""),
        fallback_model=_env("FALLBACK_MODEL", ""),
        fallback_key_file=_env("FALLBACK_KEY_FILE", str(ROOT / ".secrets" / "openrouter_api_key")),
        raft_n=int(_env("RAFT_N", "3")),
        raft_k=int(_env("RAFT_K", "2")),
        raft_temps=[float(x) for x in _env("RAFT_TEMPS", "0.3,0.7,1.0").split(",")],
        raft_repairs=int(_env("RAFT_REPAIRS", "3")),
        # five-step testability: constraints that must pass (3/5 = best accuracy of the local model on RAFT's labeled set)
        testability_min_pass=int(_env("TESTABILITY_MIN_PASS", "3")),
        judge_samples=int(_env("JUDGE_SAMPLES", "6")),
        worker_timeout=float(_env("WORKER_TIMEOUT", "3600")),
        tool_retries=int(_env("TOOL_RETRIES", "2")),
        host=_env("HOST", "127.0.0.1"),
        port=int(_env("PORT", "8080")),
    )
    s.ensure_dirs()
    return s
