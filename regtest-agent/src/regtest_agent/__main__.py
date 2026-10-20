"""`python -m regtest_agent` — start the API + web UI."""
from __future__ import annotations

import argparse


def main() -> None:
    import uvicorn

    from .config import get_settings
    s = get_settings()
    p = argparse.ArgumentParser(prog="regtest_agent")
    p.add_argument("--host", default=s.host)
    p.add_argument("--port", type=int, default=s.port)
    a = p.parse_args()
    uvicorn.run("regtest_agent.api.app:app", host=a.host, port=a.port, log_level="info", timeout_graceful_shutdown=5)


if __name__ == "__main__":
    main()
