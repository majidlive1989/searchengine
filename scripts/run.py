"""Start the single-worker local pilot, loading the project's .env file."""

import os, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if not (root / ".env").exists():
    raise SystemExit("Run python scripts/configure.py first.")
for line in (root / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#"):
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))
os.chdir(root)
sys.path.insert(0, str(root / "backend"))
import uvicorn

uvicorn.run(
    "app.main:app",
    host=os.getenv("ATLAS_HOST", "127.0.0.1"),
    port=int(os.getenv("ATLAS_PORT", "8000")),
    workers=1,
    access_log=False,
)
