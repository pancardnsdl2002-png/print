import sqlite3
import uuid
import mimetypes
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.config import UPLOADS, DB, TOKEN, MAX_MB

app = FastAPI(title="Printing Request System")

# ডিরেক্টরি এবং ফোল্ডার নিশ্চিত করা
WEB = Path(__file__).resolve().parent.parent / "web"
UPLOADS.mkdir(parents=True, exist_ok=True)
DB.parent.mkdir(parents=True, exist_ok=True)

if WEB.exists():
    app.mount("/static", StaticFiles(directory=WEB), name="static")

def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init():
    with connect() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT,
                stored_name TEXT,
                mime TEXT,
                pages INTEGER,
                duplex INTEGER,
                orientation TEXT,
                copies INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                reason TEXT
            )
        """)

init()

def auth(token: str):
    if token != TOKEN:
        raise HTTPException(401, "Invalid admin token")

def clean(name: str):
    p = (UPLOADS / Path(name).name).resolve()
    if p.parent == UPLOADS.resolve() and p.exists():
        p.unlink()

@app.get("/", response_class=HTMLResponse)
def home():
    index_file = WEB / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Index file not found</h1>", status_code=404)
    return index_file.read_text(encoding="utf-8")

@app.get("/admin", response_class=HTMLResponse)
def admin():
    admin_file = WEB / "admin.html"
    if not admin_file.exists():
        return HTMLResponse("<h1>Admin file not found</h1>", status_code=404)
    return admin_file.read_text(encoding="utf-8")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/requests")
async def submit(
    file: UploadFile = File(...),
    pages: int = Form(1),
    duplex: bool = Form(False),
    orientation: str = Form("portrait"),
    copies: int = Form(1)
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".pdf", ".jpg", ".jpeg"):
        raise HTTPException(400, "Only PDF/JPG/JPEG allowed")
    if pages not in (1, 4, 6) or orientation not in ("portrait", "landscape") or not 1 <= copies <= 100:
        raise HTTPException(400, "Invalid print settings")
    
    data = await file.read(MAX_MB * 1024 * 1024 + 1)
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_MB * 1024 * 1024:
        raise HTTPException(413, "File too large")
    
    stored = uuid.uuid4().hex + ext
    (UPLOADS / stored).write_bytes(data)
    
    with connect() as c:
        cur = c.execute(
            "INSERT INTO jobs(original_name,stored_name,mime,pages,duplex,orientation,copies) VALUES(?,?,?,?,?,?,?)",
            (
                Path(file.filename or "document").name,
                stored,
                file.content_type or mimetypes.guess_type(ext)[0] or "application/octet-stream",
                pages,
                int(duplex),
                orientation,
                copies
            )
        )
        jid = cur.lastrowid
    return {"id": jid, "status": "pending"}

@app.get("/api/requests/{jid}")
def status(jid: int):
    with connect() as c:
        row = c.execute(
            "SELECT id,original_name,pages,duplex,orientation,copies,status,created_at,reason FROM jobs WHERE id=?",
            (jid,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)

@app.get("/api/admin/requests")
def requests(x_admin_token: str = Header(default="")):
    auth(x_admin_token)
    with connect() as c:
        rows = c.execute(
            "SELECT id,original_name,pages,duplex,orientation,copies,status,created_at,reason FROM jobs ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/admin/requests/{jid}/approve")
def approve(jid: int, x_admin_token: str = Header(default="")):
    auth(x_admin_token)
    with connect() as c:
        r = c.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()
        if not r:
            raise HTTPException(404, "Not found")
        if r["status"] != "pending":
            raise HTTPException(409, "Not pending")
        c.execute("UPDATE jobs SET status='approved' WHERE id=?", (jid,))
    return {"id": jid, "status": "approved"}

@app.post("/api/admin/requests/{jid}/reject")
def reject(jid: int, reason: str = Form("Rejected"), x_admin_token: str = Header(default="")):
    auth(x_admin_token)
    with connect() as c:
        r = c.execute("SELECT stored_name,status FROM jobs WHERE id=?", (jid,)).fetchone()
        if not r:
            raise HTTPException(404, "Not found")
        if r["status"] not in ("pending", "approved"):
            raise HTTPException(409, "Cannot reject")
        c.execute("UPDATE jobs SET status='rejected',reason=? WHERE id=?", (reason[:500], jid))
        stored = r["stored_name"]
    clean(stored)
    return {"id": jid, "status": "rejected", "file_deleted": True}

@app.get("/api/desktop/jobs")
def desktop_jobs(x_admin_token: str = Header(default="")):
    auth(x_admin_token)
    with connect() as c:
        rows = c.execute(
            "SELECT id,original_name,stored_name,mime,pages,duplex,orientation,copies FROM jobs WHERE status='approved' ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]

@app.get("/api/desktop/jobs/{jid}/file")
def job_file(jid: int, x_admin_token: str = Header(default="")):
    auth(x_admin_token)
    with connect() as c:
        r = c.execute("SELECT stored_name,original_name,status FROM jobs WHERE id=?", (jid,)).fetchone()
    if not r or r["status"] != "approved":
        raise HTTPException(404, "Approved job not found")
    p = UPLOADS / r["stored_name"]
    if not p.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(p, filename=r["original_name"])

@app.post("/api/desktop/jobs/{jid}/complete")
def complete(jid: int, x_admin_token: str = Header(default="")):
    auth(x_admin_token)
    with connect() as c:
        r = c.execute("SELECT stored_name,status FROM jobs WHERE id=?", (jid,)).fetchone()
        if not r:
            raise HTTPException(404, "Not found")
        if r["status"] != "approved":
            raise HTTPException(409, "Not approved")
        c.execute("UPDATE jobs SET status='completed' WHERE id=?", (jid,))
        stored = r["stored_name"]
    clean(stored)
    return {"id": jid, "status": "completed", "file_deleted": True}
