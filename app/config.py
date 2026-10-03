import os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("PRINTING_DATA_DIR", ROOT / "data"))
UPLOADS = DATA / "uploads"
DB = DATA / "printing.sqlite3"
TOKEN = os.getenv("ADMIN_TOKEN", "change-me-now")
MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
UPLOADS.mkdir(parents=True, exist_ok=True)
