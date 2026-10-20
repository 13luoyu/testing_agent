#!/usr/bin/env bash
# Start the local LLM server (regtest-llm env) if it is not running, then the agent API + web UI.
#   scripts/start.sh            # http://127.0.0.1:8080
#   PORT=9000 scripts/start.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONDA="${CONDA_PREFIX_1:-$HOME/miniconda3}"
AGENT_PY="${AGENT_PY:-$CONDA/envs/regtest-agent/bin/python}"
LLM_PY="${LLM_PY:-$CONDA/envs/regtest-llm/bin/python}"
MODEL="${REGTEST_LLM_MODEL:-$ROOT/.runtime/models/llm/Qwen3-30B-A3B-Instruct-2507-4bit}"
LLM_PORT="${LLM_PORT:-8800}"
mkdir -p "$ROOT/.runtime/logs"

if curl -sf -m 3 "http://127.0.0.1:$LLM_PORT/health" >/dev/null; then
  echo "LLM server already running on :$LLM_PORT"
else
  echo "starting LLM server on :$LLM_PORT ($MODEL)"
  PYTHONPATH="$ROOT/src" nohup "$LLM_PY" -m regtest_agent.llm.server --model "$MODEL" --port "$LLM_PORT" \
    >"$ROOT/.runtime/logs/llm_server.log" 2>&1 &
  for _ in $(seq 1 120); do
    curl -sf -m 3 "http://127.0.0.1:$LLM_PORT/health" >/dev/null && break
    sleep 2
  done
  curl -sf -m 3 "http://127.0.0.1:$LLM_PORT/health" >/dev/null || { echo "LLM server failed, see .runtime/logs/llm_server.log"; exit 1; }
fi

export REGTEST_LLM_BASE_URL="http://127.0.0.1:$LLM_PORT/v1"
cd "$ROOT"
PYTHONPATH="$ROOT/src" exec "$AGENT_PY" -m regtest_agent --port "${PORT:-8080}"
