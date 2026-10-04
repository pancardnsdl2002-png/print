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
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import UPLOADS, DB, TOKEN, MAX_MB


# =========================================================
# APP CONFIGURATION
# =========================================================

app = FastAPI(title="Radhakrishna Printing Request System")

WEB = Path(__file__).resolve().parent.parent / "web"

UPLOADS.mkdir(parents=True, exist_ok=True)
DB.parent.mkdir(parents=True, exist_ok=True)


if WEB.exists():
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


def column_exists(connection, table_name, column_name):
    columns = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return any(
        column["name"] == column_name
        for column in columns
    )


def init_database():

    with connect() as connection:

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                original_name TEXT,
                stored_name TEXT,
                mime TEXT,

                pages INTEGER DEFAULT 1,
                page_range TEXT DEFAULT '',

                duplex INTEGER DEFAULT 0,

                orientation TEXT DEFAULT 'portrait',

                copies INTEGER DEFAULT 1,

                color_mode TEXT DEFAULT 'color',

                status TEXT DEFAULT 'pending',

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                reason TEXT
            )
            """
        )

        # -------------------------------------------------
        # Migration for existing database
        # -------------------------------------------------

        if not column_exists(
            connection,
            "jobs",
            "page_range",
        ):
            connection.execute(
                """
                ALTER TABLE jobs
                ADD COLUMN page_range TEXT DEFAULT ''
                """
            )

        if not column_exists(
            connection,
            "jobs",
            "color_mode",
        ):
            connection.execute(
                """
                ALTER TABLE jobs
                ADD COLUMN color_mode TEXT DEFAULT 'color'
                """
            )

        connection.commit()


init_database()


# =========================================================
# HELPERS
# =========================================================

def auth(token: str):

    if not token or token != TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token",
        )


def clean(stored_name):

    if not stored_name:
        return

    file_path = (
        UPLOADS / Path(stored_name).name
    ).resolve()

    if file_path.parent == UPLOADS.resolve():
        if file_path.exists():
            file_path.unlink()


def validate_settings(
    pages,
    page_range,
    duplex,
    orientation,
    copies,
    color_mode,
):

    if pages not in (1, 4, 6):
        raise HTTPException(
            status_code=400,
            detail="Pages per sheet must be 1,4 or 6")
