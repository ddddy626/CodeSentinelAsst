import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.getenv("CODESENTINEL_DB", str(APP_DIR.parent / "data" / "reviews.sqlite3")))
LLM_API_URL = os.getenv("CODESENTINEL_LLM_URL", "").strip()
LLM_API_KEY = os.getenv("CODESENTINEL_LLM_KEY", "").strip()
LLM_MODEL = os.getenv("CODESENTINEL_LLM_MODEL", "").strip()
MAX_SOURCE_BYTES = 100_000
MAX_SOURCE_LINES = 2_000
RULE_VERSION = "v1-2"
BUILD_VERSION = os.getenv("CODESENTINEL_BUILD_VERSION", "v1-2")
