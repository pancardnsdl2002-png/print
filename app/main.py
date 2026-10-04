import sqlite3
import uuid
import mimetypes

from pathlib import Path

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    Header,
    HTTPException,
)

from fastapi.responses import (
    HTMLResponse,
    FileResponse,
)

from fastapi.staticfiles import StaticFiles

from app.config import (
    UPLOADS,
    DB,
    TOKEN,
    MAX_MB,
)


# =========================================================
# APP CONFIGURATION
# =========================================================

app = FastAPI(
    title="Printing Request System"
)

WEB = Path(__file__).resolve().parent.parent / "web"

app.mount(
    "/static",
    StaticFiles(directory=WEB),
    name="static",
)


# =========================================================
# DATABASE
# =========================================================

def connect():
    connection = sqlite3.connect(DB)

    connection.row_factory = sqlite3.Row

    return connection


def init():
    with connect() as connection:

        # Original table
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT,
                stored_name TEXT,
                mime TEXT,
                pages INTEGER,
                duplex INTEGER,
                orientation TEXT,
                copies INTEGER,
                page_range TEXT DEFAULT 'All',
                color_mode TEXT DEFAULT 'color',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                reason TEXT
            )
            """
        )

        # -------------------------------------------------
        # Database migration
        # -------------------------------------------------
        # If the old database already exists without the
        # new columns, add them automatically.
        # -------------------------------------------------

        columns = connection.execute(
            "PRAGMA table_info(jobs)"
        ).fetchall()

        column_names = {
            column["name"]
            for column in columns
        }

        if "page_range" not in column_names:

            connection.execute(
                """
                ALTER TABLE jobs
                ADD COLUMN page_range TEXT DEFAULT 'All'
                """
            )

        if "color_mode" not in column_names:

            connection.execute(
                """
                ALTER TABLE jobs
                ADD COLUMN color_mode TEXT DEFAULT 'color'
                """
            )


init()


# =========================================================
# AUTHENTICATION
# =========================================================

def auth(token):
    if token != TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token",
        )


# =========================================================
# FILE CLEANUP
# =========================================================

def clean(name):

    path = (
        UPLOADS
        / Path(name).name
    ).resolve()

    if (
        path.parent == UPLOADS.resolve()
        and path.exists()
    ):
        path.unlink()


# =========================================================
# WEB PAGES
# =========================================================

@app.get(
    "/",
    response_class=HTMLResponse,
)
def home():

    return (
        WEB / "index.html"
    ).read_text(
        encoding="utf-8"
    )


@app.get(
    "/admin",
    response_class=HTMLResponse,
)
def admin():

    return (
        WEB / "admin.html"
    ).read_text(
        encoding="utf-8"
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():

    return {
        "ok": True
    }


# =========================================================
# CUSTOMER SUBMIT REQUEST
# =========================================================

@app.post("/api/requests")
async def submit(

    file: UploadFile = File(...),

    pages: int = Form(1),

    duplex: bool = Form(False),

    orientation: str = Form(
        "portrait"
    ),

    copies: int = Form(1),

    page_range: str = Form(
        "All"
    ),

    color_mode: str = Form(
        "color"
    ),
):

    # -----------------------------------------------------
    # FILE EXTENSION
    # -----------------------------------------------------

    ext = Path(
        file.filename or ""
    ).suffix.lower()

    if ext not in (
        ".pdf",
        ".jpg",
        ".jpeg",
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Only PDF/JPG/JPEG allowed"
            ),
        )

    # -----------------------------------------------------
    # VALIDATE PAGES
    # -----------------------------------------------------

    if pages not in (
        1,
        4,
        6,
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Pages must be 1, 4, or 6"
            ),
        )

    # -----------------------------------------------------
    # VALIDATE ORIENTATION
    # -----------------------------------------------------

    if orientation not in (
        "portrait",
        "landscape",
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid orientation",
        )

    # -----------------------------------------------------
    # VALIDATE COPIES
    # -----------------------------------------------------

    if not 1 <= copies <= 100:

        raise HTTPException(
            status_code=400,
            detail=(
                "Copies must be between 1 and 100"
            ),
        )

    # -----------------------------------------------------
    # VALIDATE COLOR
    # -----------------------------------------------------

    if color_mode not in (
        "color",
        "grayscale",
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid color mode",
        )

    # -----------------------------------------------------
    # CLEAN PAGE RANGE
    # -----------------------------------------------------

    page_range = (
        page_range.strip()
        or "All"
    )

    if len(page_range) > 200:

        raise HTTPException(
            status_code=400,
            detail="Page range is too long",
        )

    # -----------------------------------------------------
    # READ FILE
    # -----------------------------------------------------

    data = await file.read(
        MAX_MB * 1024 * 1024 + 1
    )

    if not data:

        raise HTTPException(
            status_code=400,
            detail="Empty file",
        )

    # -----------------------------------------------------
    # FILE SIZE
    # -----------------------------------------------------

    if len(data) > MAX_MB * 1024 * 1024:

        raise HTTPException(
            status_code=413,
            detail="File too large",
        )

    # -----------------------------------------------------
    # SAVE FILE
    # -----------------------------------------------------

    stored = (
        uuid.uuid4().hex
        + ext
    )

    file_path = (
        UPLOADS / stored
    )

    file_path.write_bytes(data)

    # -----------------------------------------------------
    # SAVE REQUEST TO DATABASE
    # -----------------------------------------------------

    with connect() as connection:

        cursor = connection.execute(
            """
            INSERT INTO jobs (
                original_name,
                stored_name,
                mime,
                pages,
                duplex,
                orientation,
                copies,
                page_range,
                color_mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                Path(
                    file.filename
                    or "document"
                ).name,

                stored,

                (
                    file.content_type
                    or mimetypes.guess_type(
                        ext
                    )[0]
                    or "application/octet-stream"
                ),

                pages,

                int(duplex),

                orientation,

                copies,

                page_range,

                color_mode,
            ),
        )

        job_id = cursor.lastrowid

    return {
        "id": job_id,
        "status": "pending",
    }


# =========================================================
# CUSTOMER STATUS
# =========================================================

@app.get("/api/requests/{jid}")
def status(jid: int):

    with connect() as connection:

        row = connection.execute(
            """
            SELECT
                id,
                original_name,
                pages,
                duplex,
                orientation,
                copies,
                page_range,
                color_mode,
                status,
                created_at,
                reason
            FROM jobs
            WHERE id = ?
            """,
            (jid,),
        ).fetchone()

    if not row:

        raise HTTPException(
            status_code=404,
            detail="Not found",
        )

    return dict(row)


# =========================================================
# ADMIN - GET REQUESTS
# =========================================================

@app.get("/api/admin/requests")
def requests(
    x_admin_token: str = Header(
        default=""
    ),
):

    auth(x_admin_token)

    with connect() as connection:

        rows = connection.execute(
            """
            SELECT
                id,
                original_name,
                pages,
                duplex,
                orientation,
                copies,
                page_range,
                color_mode,
                status,
                created_at,
                reason
            FROM jobs
            ORDER BY id DESC
            """
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# =========================================================
# ADMIN - UPDATE PRINT SETTINGS
# =========================================================

@app.post(
    "/api/admin/requests/{jid}/settings"
)
def update_settings(

    jid: int,

    pages: int = Form(1),

    duplex: bool = Form(False),

    orientation: str = Form(
        "portrait"
    ),

    copies: int = Form(1),

    page_range: str = Form(
        "All"
    ),

    color_mode: str = Form(
        "color"
    ),

    x_admin_token: str = Header(
        default=""
    ),
):

    auth(x_admin_token)

    # -----------------------------------------------------
    # VALIDATE
    # -----------------------------------------------------

    if pages not in (
        1,
        4,
        6,
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Pages must be 1, 4, or 6"
            ),
        )

    if orientation not in (
        "portrait",
        "landscape",
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid orientation",
        )

    if not 1 <= copies <= 100:

        raise HTTPException(
            status_code=400,
            detail=(
                "Copies must be between 1 and 100"
            ),
        )

    if color_mode not in (
        "color",
        "grayscale",
    ):

        raise HTTPException(
            status_code=400,
            detail="Invalid color mode",
        )

    page_range = (
        page_range.strip()
        or "All"
    )

    # -----------------------------------------------------
    # UPDATE
    # -----------------------------------------------------

    with connect() as connection:

        row = connection.execute(
            """
            SELECT id, status
            FROM jobs
            WHERE id = ?
            """,
            (jid,),
        ).fetchone()

        if not row:

            raise HTTPException(
                status_code=404,
                detail="Not found",
            )

        if row["status"] not in (
            "pending",
            "approved",
        ):

            raise HTTPException(
                status_code=409,
                detail=(
                    "Cannot change settings "
                    "for this job"
                ),
            )

        connection.execute(
            """
            UPDATE jobs
            SET
                pages = ?,
                duplex = ?,
                orientation = ?,
                copies = ?,
                page_range = ?,
                color_mode = ?
            WHERE id = ?
            """,
            (
                pages,
                int(duplex),
                orientation,
                copies,
                page_range,
                color_mode,
                jid,
            ),
        )

    return {
        "id": jid,
        "status": "settings_updated",
    }


# =========================================================
# ADMIN - APPROVE
# =========================================================

@app.post(
    "/api/admin/requests/{jid}/approve"
)
def approve(
    jid: int,
    x_admin_token: str = Header(
        default=""
    ),
):

    auth(x_admin_token)

    with connect() as connection:

        row = connection.execute(
            """
            SELECT status
            FROM jobs
            WHERE id = ?
            """,
            (jid,),
        ).fetchone()

        if not row:

            raise HTTPException(
                status_code=404,
                detail="Not found",
            )

        if row["status"] != "pending":

            raise HTTPException(
                status_code=409,
                detail="Not pending",
            )

        connection.execute(
            """
            UPDATE jobs
            SET status = 'approved'
            WHERE id = ?
            """,
            (jid,),
        )

    return {
        "id": jid,
        "status": "approved",
    }


# =========================================================
# ADMIN - REJECT
# =========================================================

@app.post(
    "/api/admin/requests/{jid}/reject"
)
def reject(

    jid: int,

    reason: str = Form(
        "Rejected"
    ),

    x_admin_token: str = Header(
        default=""
    ),
):

    auth(x_admin_token)

    with connect() as connection:

        row = connection.execute(
            """
            SELECT
                stored_name,
                status
            FROM jobs
            WHERE id = ?
            """,
            (jid,),
        ).fetchone()

        if not row:

            raise HTTPException(
                status_code=404,
                detail="Not found",
            )

        if row["status"] not in (
            "pending",
            "approved",
        ):

            raise HTTPException(
                status_code=409,
                detail="Cannot reject",
            )

        connection.execute(
            """
            UPDATE jobs
            SET
                status = 'rejected',
                reason = ?
            WHERE id = ?
            """,
            (
                reason[:500],
                jid,
            ),
        )

        stored = row["stored_name"]

    clean(stored)

    return {
        "id": jid,
        "status": "rejected",
        "file_deleted": True,
    }


# =========================================================
# DESKTOP - APPROVED JOBS
# =========================================================

@app.get("/api/desktop/jobs")
def desktop_jobs(
    x_admin_token: str = Header(
        default=""
    ),
):

    auth(x_admin_token)

    with connect() as connection:

        rows = connection.execute(
            """
            SELECT
                id,
                original_name,
                stored_name,
                mime,
                pages,
                duplex,
                orientation,
                copies,
                page_range,
                color_mode
            FROM jobs
            WHERE status = 'approved'
            ORDER BY id
            """
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# =========================================================
# DESKTOP - DOWNLOAD FILE
# =========================================================

@app.get(
    "/api/desktop/jobs/{jid}/file"
)
def job_file(
    jid: int,
    x_admin_token: str = Header(
        default=""
    ),
):

    auth(x_admin_token)

    with connect() as connection:

        row = connection.execute(
            """
            SELECT
                stored_name,
                original_name,
                status
            FROM jobs
            WHERE id = ?
            """,
            (jid,),
        ).fetchone()

    if (
        not row
        or row["status"] != "approved"
    ):

        raise HTTPException(
            status_code=404,
            detail="Approved job not found",
        )

    path = (
        UPLOADS
        / row["stored_name"]
    )

    if not path.exists():

        raise HTTPException(
            status_code=404,
            detail="File missing",
        )

    return FileResponse(
        path,
        filename=row["original_name"],
    )


# =========================================================
# DESKTOP - COMPLETE JOB
# =========================================================

@app.post(
    "/api/desktop/jobs/{jid}/complete"
)
def complete(
    jid: int,
    x_admin_token: str = Header(
        default=""
    ),
):

    auth(x_admin_token)

    with connect() as connection:

        row = connection.execute(
            """
            SELECT
                stored_name,
                status
            FROM jobs
            WHERE id = ?
            """,
            (jid,),
        ).fetchone()

        if not row:

            raise HTTPException(
                status_code=404,
                detail="Not found",
            )

        if row["status"] != "approved":

            raise HTTPException(
                status_code=409,
                detail="Not approved",
            )

        connection.execute(
            """
            UPDATE jobs
            SET status = 'completed'
            WHERE id = ?
            """,
            (jid,),
        )

        stored = row["stored_name"]

    clean(stored)

    return {
        "id": jid,
        "status": "completed",
        "file_deleted": True,
    }
