import os
import sys
import tempfile
from pathlib import Path

# isolated data directory + SQLite DB for every test session (must be set before importing app)
_tmp = tempfile.mkdtemp(prefix="safemetric-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
