import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
# isolated state; models / HanLP assets keep pointing at the project .runtime
os.environ.setdefault("REGTEST_RUNTIME", tempfile.mkdtemp(prefix="regtest_test_"))
os.environ.setdefault("REGTEST_ASSETS", str(ROOT / ".runtime"))
