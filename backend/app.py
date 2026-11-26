"""
RamanCloud preprocessing API.

FastAPI service for spectrum, time-series, and hyperspectral Raman preprocessing.
The original Streamlit site remains untouched in /media/ramancloud.
"""

import io
import hashlib
import hmac
import os
import json
import re
import secrets
import sqlite3
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np
import pandas as pd
import pywt
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from request_stream import stream_work
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, validator
from scipy import sparse
from scipy.signal import savgol_filter
from scipy.sparse.linalg import spsolve
from denoising.tshi import denoise as tshi_denoise, bm3d_available
from hyperspectral_io import mat_result, MAX_UPLOAD, time_series_preview
from hyperspectral_upload import CHUNK_BYTES, accept_chunk
from legacy_algorithms import TSVDWorkLimitError
from spectral_formats import parse_dataset, parse_single, SPECTRAL_EXTENSIONS
from preprocessing.despike import despike_matrix, validate_order as validate_despike_order
from project_collaboration import project_access, project_admin, project_list_query, event as project_event

try:
    import pymysql
    from pymysql.err import IntegrityError as PyMySQLIntegrityError
except ImportError:  # PyMySQL is only required when DATABASE_URL/MYSQL_* selects MySQL.
    pymysql = None
    PyMySQLIntegrityError = None

try:
    import boto3
except ImportError:  # boto3 is only required when RAMANCLOUD_STORAGE_BACKEND=s3.
    boto3 = None


ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
DATA_DIR = Path(os.environ.get("RAMANCLOUD_DATA_DIR") or (ROOT / "data"))
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("MYSQL_URL")
DB_ENGINE = "mysql" if (
    (DATABASE_URL or "").startswith(("mysql://", "mysql+pymysql://"))
    or os.environ.get("MYSQL_HOST")
) else "sqlite"
DB_PATH = Path(os.environ.get("RAMANCLOUD_DB_PATH", DATA_DIR / "ramancloud.db"))
STORAGE_DIR = Path(os.environ.get("RAMANCLOUD_STORAGE_DIR") or (DATA_DIR / "stored_files"))
S3_BUCKET = os.environ.get("RAMANCLOUD_S3_BUCKET") or os.environ.get("S3_BUCKET") or os.environ.get("AWS_S3_BUCKET")
STORAGE_BACKEND = (os.environ.get("RAMANCLOUD_STORAGE_BACKEND") or ("s3" if S3_BUCKET else "local")).lower()
S3_PREFIX = (os.environ.get("RAMANCLOUD_S3_PREFIX") or "ramancloud/uploads").strip("/")
S3_ENDPOINT_URL = os.environ.get("RAMANCLOUD_S3_ENDPOINT_URL") or os.environ.get("S3_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL")
S3_REGION = os.environ.get("RAMANCLOUD_S3_REGION") or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
S3_ACCESS_KEY_ID = os.environ.get("RAMANCLOUD_S3_ACCESS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = os.environ.get("RAMANCLOUD_S3_SECRET_ACCESS_KEY") or os.environ.get("AWS_SECRET_ACCESS_KEY")
SESSION_DAYS = 7
AUTH_ROLES = {"user", "admin"}
DATA_KINDS = {"raw", "processed"}
DATA_TYPES = {"auto", "spectrum", "mapping", "unknown"}
ANALYSIS_TYPES = {"spectrum", "hyperspectral", "structure_generation", "library_matching", "mixture_analysis", "peak_fitting"}
VERSION_TYPES = {"original", "processed", "result"}
DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError,) + ((PyMySQLIntegrityError,) if PyMySQLIntegrityError else ())

ID_SQL = "VARCHAR(64)" if DB_ENGINE == "mysql" else "TEXT"
TOKEN_SQL = "VARCHAR(64)" if DB_ENGINE == "mysql" else "TEXT"
USERNAME_SQL = "VARCHAR(64)" if DB_ENGINE == "mysql" else "TEXT"
EMAIL_SQL = "VARCHAR(255)" if DB_ENGINE == "mysql" else "TEXT"
SHORT_SQL = "VARCHAR(64)" if DB_ENGINE == "mysql" else "TEXT"
NAME_SQL = "VARCHAR(255)" if DB_ENGINE == "mysql" else "TEXT"
DATE_SQL = "VARCHAR(40)" if DB_ENGINE == "mysql" else "TEXT"
PATH_SQL = "VARCHAR(1024)" if DB_ENGINE == "mysql" else "TEXT"
JSON_SQL = "LONGTEXT" if DB_ENGINE == "mysql" else "TEXT"
JSON_OBJECT_COLUMN = f"{JSON_SQL} NOT NULL" if DB_ENGINE == "mysql" else f"{JSON_SQL} NOT NULL DEFAULT '{{}}'"
JSON_ARRAY_COLUMN = f"{JSON_SQL} NOT NULL" if DB_ENGINE == "mysql" else f"{JSON_SQL} NOT NULL DEFAULT '[]'"
TABLE_OPTIONS = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci" if DB_ENGINE == "mysql" else ""
_S3_CLIENT: Any = None

app = FastAPI(
    title="RamanCloud Preprocessing API",
    version="2.0.0",
    description="Cut, denoise, and baseline-correct Raman spectra and spectral cubes.",
)
allowed_origins = [origin.strip() for origin in os.getenv("RAMANCLOUD_ALLOWED_ORIGINS", "*").split(",") if origin.strip()]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


class Step(BaseModel):
    type: str
    method: str = "skip"
    params: Dict[str, Any] = Field(default_factory=dict)


class SpectrumPayload(BaseModel):
    wavenumber: List[float]
    intensity: List[float]
    steps: List[Step] = Field(default_factory=list)
    save_history: bool = False
    source_name: Optional[str] = None
    project_id: Optional[str] = None
    source_dataset_id: Optional[str] = None
    title: Optional[str] = Field(None, max_length=160)


class CubePayload(BaseModel):
    wavenumber: List[float]
    spectra: Optional[Any] = None
    dataset_id: Optional[str] = None
    shape: Optional[List[int]] = None
    mode: str = "spectra"
    steps: List[Step] = Field(default_factory=list)
    save_history: bool = False
    source_name: Optional[str] = None
    project_id: Optional[str] = None
    source_dataset_id: Optional[str] = None
    title: Optional[str] = Field(None, max_length=160)
    preview_wavenumber: Optional[float] = None

    @validator('preview_wavenumber')
    def finite_preview_wavenumber(cls, value):
        if value is not None and not np.isfinite(value):
            raise ValueError('Preview wavenumber must be finite.')
        return value


class DownloadPayload(BaseModel):
    wavenumber: List[float]
    intensity: Optional[List[float]] = None
    spectra: Optional[Any] = None
    dataset_id: Optional[str] = None
    shape: Optional[List[int]] = None
    mode: str = "spectrum"
    baseline: Optional[List[float]] = None
    filename: str = "processed.txt"
    format: str = "txt"


class RegisterPayload(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    email: Optional[str] = Field(None, max_length=120)
    display_name: Optional[str] = Field(None, max_length=80)
    role: str = "user"


class LoginPayload(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=128)


class PasswordChangePayload(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class UserUpdatePayload(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    display_name: Optional[str] = Field(None, max_length=80)
    email: Optional[str] = Field(None, max_length=120)


class ProjectPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=80)


class ProjectUpdatePayload(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=80)


class DatasetUpdatePayload(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=160)
    category: Optional[str] = Field(None, max_length=80)
    data_kind: Optional[str] = None


class AnalysisRunPayload(BaseModel):
    title: Optional[str] = Field(None, max_length=160)
    project_id: Optional[str] = None


DEMO_SPECTRA = {
    "bacteria": "Bacteria.txt",
    "ulf": "ULF.txt",
    "tutorial": "tutorial_raman.txt",
}

DEMO_MAPPING = {
    "timeseries_horiba": ("time_series_Horiba.txt", "Horiba", "time_series"),
    "timeseries_nanophoton": ("time_series_Nanophoton.txt", "Nanophoton", "time_series"),
    "imaging_horiba": ("imaging_Horiba_Graphene.txt", "Horiba", "imaging"),
    "imaging_nanophoton": ("imaging_Nanophoton_Hela.txt", "Nanophoton", "imaging"),
}

DATASETS: Dict[str, Dict[str, Any]] = {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def normalize_username(username: str) -> str:
    value = username.strip()
    if not re.match(r"^[A-Za-z0-9_-]{3,32}$", value):
        raise HTTPException(status_code=400, detail="Username must be 3-32 characters and use only letters, numbers, underscores, or hyphens.")
    return value


def normalize_email(email: Optional[str]) -> Optional[str]:
    value = normalize_optional_text(email)
    if value is None:
        return None
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
        raise HTTPException(status_code=400, detail="Email format is invalid.")
    return value.lower()


def password_hash(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120_000)
    return salt, digest.hex()


def verify_password(password: str, salt: str, digest: str) -> bool:
    _, candidate = password_hash(password, salt)
    return hmac.compare_digest(candidate, digest)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def mysql_config() -> Dict[str, Any]:
    if pymysql is None:
        raise RuntimeError("PyMySQL is not installed. Run `pip install -r requirements.txt` before using MySQL.")

    if DATABASE_URL:
        parsed = urlparse(DATABASE_URL)
        if parsed.scheme not in {"mysql", "mysql+pymysql"}:
            raise RuntimeError("DATABASE_URL must start with mysql:// or mysql+pymysql:// when MySQL is enabled.")
        query = parse_qs(parsed.query)
        database = unquote(parsed.path.lstrip("/"))
        if not database:
            raise RuntimeError("DATABASE_URL must include a database name.")
        return {
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or "root"),
            "password": unquote(parsed.password or ""),
            "database": database,
            "charset": query.get("charset", ["utf8mb4"])[0],
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": False,
        }

    database = os.environ.get("MYSQL_DATABASE") or os.environ.get("MYSQL_DB")
    if not database:
        raise RuntimeError("MYSQL_DATABASE is required when MYSQL_HOST is used.")
    return {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "database": database,
        "charset": os.environ.get("MYSQL_CHARSET", "utf8mb4"),
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }


class MySQLConnection:
    def __init__(self) -> None:
        config = mysql_config()
        self._conn = pymysql.connect(**config)

    def execute(self, sql: str, params: Any = ()) -> Any:
        cursor = self._conn.cursor()
        cursor.execute(sql.replace("?", "%s"), params or ())
        return cursor

    def __enter__(self) -> "MySQLConnection":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()


def db_connect() -> Any:
    if DB_ENGINE == "mysql":
        return MySQLConnection()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_index(conn: Any, name: str, table: str, columns: str) -> None:
    if DB_ENGINE == "mysql":
        existing = conn.execute(
            """
            SELECT COUNT(1) AS count
            FROM information_schema.statistics
            WHERE table_schema = DATABASE() AND table_name = ? AND index_name = ?
            """,
            (table, name),
        ).fetchone()
        if int(existing["count"] or 0) == 0:
            column_sql = ", ".join(f"`{column.strip()}`" for column in columns.split(","))
            conn.execute(f"CREATE INDEX `{name}` ON `{table}` ({column_sql})")
        return
    conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({columns})")


def init_auth_db() -> None:
    with db_connect() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS users (
                id {ID_SQL} PRIMARY KEY,
                username {USERNAME_SQL} NOT NULL UNIQUE,
                email {EMAIL_SQL} UNIQUE,
                display_name TEXT,
                password_salt {SHORT_SQL} NOT NULL,
                password_hash {NAME_SQL} NOT NULL,
                role {SHORT_SQL} NOT NULL DEFAULT 'user',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at {DATE_SQL} NOT NULL,
                updated_at {DATE_SQL} NOT NULL,
                last_login {DATE_SQL}
            ){TABLE_OPTIONS}
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash {TOKEN_SQL} PRIMARY KEY,
                user_id {ID_SQL} NOT NULL,
                created_at {DATE_SQL} NOT NULL,
                expires_at {DATE_SQL} NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            ){TABLE_OPTIONS}
            """
        )
        create_index(conn, "idx_sessions_user_id", "sessions", "user_id")
        create_index(conn, "idx_sessions_expires_at", "sessions", "expires_at")
        # Earlier versions issued a session during registration without recording the login.
        conn.execute(
            """
            UPDATE users
            SET last_login = (SELECT MAX(created_at) FROM sessions WHERE sessions.user_id = users.id)
            WHERE last_login IS NULL
              AND EXISTS (SELECT 1 FROM sessions WHERE sessions.user_id = users.id)
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS projects (
                id {ID_SQL} PRIMARY KEY,
                owner_id {ID_SQL} NOT NULL,
                name {NAME_SQL} NOT NULL,
                description TEXT,
                category {NAME_SQL},
                created_at {DATE_SQL} NOT NULL,
                updated_at {DATE_SQL} NOT NULL,
                FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
            ){TABLE_OPTIONS}
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS project_members (
                project_id {ID_SQL} NOT NULL,
                user_id {ID_SQL} NOT NULL,
                role {SHORT_SQL} NOT NULL DEFAULT 'member',
                created_at {DATE_SQL} NOT NULL,
                PRIMARY KEY(project_id, user_id),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            ){TABLE_OPTIONS}
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS data_assets (
                id {ID_SQL} PRIMARY KEY,
                project_id {ID_SQL} NOT NULL,
                owner_id {ID_SQL} NOT NULL,
                filename {NAME_SQL} NOT NULL,
                display_name {NAME_SQL} NOT NULL,
                category {NAME_SQL},
                data_kind {SHORT_SQL} NOT NULL DEFAULT 'raw',
                data_type {SHORT_SQL} NOT NULL DEFAULT 'unknown',
                instrument {NAME_SQL},
                mode {NAME_SQL},
                storage_path {PATH_SQL} NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                metadata_json {JSON_OBJECT_COLUMN},
                created_at {DATE_SQL} NOT NULL,
                updated_at {DATE_SQL} NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
            ){TABLE_OPTIONS}
            """
        )
        create_index(conn, "idx_projects_owner_id", "projects", "owner_id")
        create_index(conn, "idx_project_members_user_id", "project_members", "user_id")
        create_index(conn, "idx_data_assets_project_id", "data_assets", "project_id")
        create_index(conn, "idx_data_assets_owner_id", "data_assets", "owner_id")
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id {ID_SQL} PRIMARY KEY,
                user_id {ID_SQL} NOT NULL,
                project_id {ID_SQL},
                source_dataset_id {ID_SQL},
                result_dataset_id {ID_SQL},
                title {NAME_SQL} NOT NULL,
                analysis_type {SHORT_SQL} NOT NULL,
                source_name {NAME_SQL},
                steps_json {JSON_ARRAY_COLUMN},
                input_json {JSON_OBJECT_COLUMN},
                result_json {JSON_OBJECT_COLUMN},
                history_json {JSON_ARRAY_COLUMN},
                result_filename {NAME_SQL},
                created_at {DATE_SQL} NOT NULL,
                updated_at {DATE_SQL} NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL,
                FOREIGN KEY(source_dataset_id) REFERENCES data_assets(id) ON DELETE SET NULL,
                FOREIGN KEY(result_dataset_id) REFERENCES data_assets(id) ON DELETE SET NULL
            ){TABLE_OPTIONS}
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS analysis_versions (
                id {ID_SQL} PRIMARY KEY,
                run_id {ID_SQL} NOT NULL,
                version_type {SHORT_SQL} NOT NULL,
                label {NAME_SQL} NOT NULL,
                payload_json {JSON_OBJECT_COLUMN},
                created_at {DATE_SQL} NOT NULL,
                FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
            ){TABLE_OPTIONS}
            """
        )
        create_index(conn, "idx_analysis_runs_user_id", "analysis_runs", "user_id")
        create_index(conn, "idx_analysis_runs_project_id", "analysis_runs", "project_id")
        create_index(conn, "idx_analysis_versions_run_id", "analysis_versions", "run_id")


def row_to_user(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"] or row["username"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login": row["last_login"],
    }


def row_to_project(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "owner_id": row["owner_id"],
        "name": row["name"],
        "description": row["description"] or "",
        "category": row["category"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "dataset_count": int(row["dataset_count"] or 0) if "dataset_count" in row.keys() else 0,
        "raw_count": int(row["raw_count"] or 0) if "raw_count" in row.keys() else 0,
        "processed_count": int(row["processed_count"] or 0) if "processed_count" in row.keys() else 0,
        "owner_username": row["owner_username"] if "owner_username" in row.keys() else None,
        "my_role": row["my_role"] if "my_role" in row.keys() else 'admin',
    }


def row_to_dataset(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "owner_id": row["owner_id"],
        "filename": row["filename"],
        "display_name": row["display_name"],
        "category": row["category"] or "",
        "data_kind": row["data_kind"],
        "data_type": row["data_type"],
        "instrument": row["instrument"] or "",
        "mode": row["mode"] or "",
        "file_size": int(row["file_size"]),
        "metadata": metadata,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "owner_username": row["owner_username"] if "owner_username" in row.keys() else None,
    }


def safe_json_load(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def row_to_analysis_run(row: sqlite3.Row, versions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    steps = safe_json_load(row["steps_json"], [])
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "project_id": row["project_id"],
        "source_dataset_id": row["source_dataset_id"],
        "result_dataset_id": row["result_dataset_id"],
        "title": row["title"],
        "analysis_type": row["analysis_type"],
        "source_name": row["source_name"] or "",
        "steps": steps,
        "step_count": len(steps),
        "input": safe_json_load(row["input_json"], {}),
        "result": safe_json_load(row["result_json"], {}),
        "history": safe_json_load(row["history_json"], []),
        "result_filename": row["result_filename"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "username": row["username"] if "username" in row.keys() else None,
        "project_name": row["project_name"] if "project_name" in row.keys() else None,
        "versions": versions or [],
    }


def row_to_analysis_version(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "version_type": row["version_type"],
        "label": row["label"],
        "payload": safe_json_load(row["payload_json"], {}),
        "created_at": row["created_at"],
    }


def create_session(conn: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = utc_now()
    created_at = now.isoformat()
    expires_at = (now + timedelta(days=SESSION_DAYS)).isoformat()
    conn.execute("UPDATE users SET last_login = ?, updated_at = ? WHERE id = ?", (created_at, created_at, user_id))
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (hash_token(token), user_id, created_at, expires_at),
    )
    return token


def active_admin_count(conn: sqlite3.Connection, exclude_user_id: Optional[str] = None) -> int:
    if exclude_user_id:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?",
            (exclude_user_id,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1").fetchone()
    return int(row["count"])


def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please log in first.")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Please log in first.")

    with db_connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (iso_now(),))
        row = conn.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at >= ? AND users.is_active = 1
            """,
            (hash_token(token), iso_now()),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return row_to_user(row)


def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    if not authorization:
        return None
    return get_current_user(authorization)


def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Administrator permission is required.")
    return current_user


init_auth_db()

from user_preferences import install_user_preferences
install_user_preferences(app, globals())


def project_query_for_user(current_user: Dict[str, Any], include_counts: bool = True) -> Tuple[str, Tuple[Any, ...]]:
    return project_list_query(current_user, include_counts)


def get_project_row(conn: sqlite3.Connection, project_id: str, current_user: Dict[str, Any]) -> sqlite3.Row:
    return project_access(conn, project_id, current_user)


def require_project_owner(conn: sqlite3.Connection, project_id: str, current_user: Dict[str, Any]) -> sqlite3.Row:
    return project_admin(conn, project_id, current_user)


def clean_storage_name(filename: Optional[str]) -> str:
    name = Path(filename or "dataset.txt").name
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return name or "dataset.txt"


def normalize_data_kind(value: Optional[str]) -> str:
    data_kind = (value or "raw").strip().lower()
    if data_kind not in DATA_KINDS:
        raise HTTPException(status_code=400, detail="Data kind must be raw or processed.")
    return data_kind


def normalize_data_type(value: Optional[str]) -> str:
    data_type = (value or "auto").strip().lower()
    if data_type not in DATA_TYPES:
        raise HTTPException(status_code=400, detail="Data type must be auto, spectrum, mapping, or unknown.")
    return data_type


def detect_dataset_metadata(content: bytes, filename: str, data_type: str, instrument: str, mode: str) -> Tuple[str, Dict[str, Any]]:
    try:
        requested = 'spectrum' if data_type == 'spectrum' else mode if data_type == 'mapping' else 'auto'
        wave, values, metadata = parse_dataset(content, filename, requested, instrument)
        metadata.update(parse_status='ok', points=len(wave), wavenumber_min=float(wave.min()),
                        wavenumber_max=float(wave.max()), intensity_min=float(values.min()), intensity_max=float(values.max()))
        return 'spectrum' if values.ndim == 1 else 'mapping', metadata
    except ValueError as exc:
        return data_type if data_type != 'auto' else 'unknown', dict(parse_status='failed', parse_error=str(exc), filename=filename)


def storage_key(project_id: str, dataset_id: str, safe_name: str) -> str:
    return f"{project_id}/{dataset_id}_{safe_name}".replace("\\", "/")


def is_s3_storage_path(storage_path: str) -> bool:
    return storage_path.startswith("s3://")


def s3_client() -> Any:
    global _S3_CLIENT
    if boto3 is None:
        raise HTTPException(status_code=500, detail="boto3 is not installed. Run `pip install -r requirements.txt` before using S3 storage.")
    if _S3_CLIENT is None:
        kwargs: Dict[str, Any] = {}
        if S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = S3_ENDPOINT_URL
        if S3_REGION:
            kwargs["region_name"] = S3_REGION
        if S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY:
            kwargs["aws_access_key_id"] = S3_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = S3_SECRET_ACCESS_KEY
        _S3_CLIENT = boto3.client("s3", **kwargs)
    return _S3_CLIENT


def s3_path_for_key(key: str) -> str:
    if not S3_BUCKET:
        raise HTTPException(status_code=500, detail="RAMANCLOUD_S3_BUCKET or S3_BUCKET is required when S3 storage is enabled.")
    clean_prefix = S3_PREFIX.strip("/")
    clean_key = key.strip("/").replace("\\", "/")
    object_key = f"{clean_prefix}/{clean_key}" if clean_prefix else clean_key
    return f"s3://{S3_BUCKET}/{object_key}"


def parse_s3_storage_path(storage_path: str) -> Tuple[str, str]:
    parsed = urlparse(storage_path)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise HTTPException(status_code=400, detail="S3 storage path is invalid.")
    return bucket, key


def stored_file_path(storage_path: str) -> Path:
    if is_s3_storage_path(storage_path):
        raise HTTPException(status_code=400, detail="S3 files are not stored on the local filesystem.")
    legacy_prefixes = ("stored_files/", "stored_files\\")
    base_dir = DATA_DIR if storage_path.startswith(legacy_prefixes) else STORAGE_DIR
    path = (base_dir / storage_path).resolve()
    storage_root = (DATA_DIR / "stored_files" if storage_path.startswith(legacy_prefixes) else STORAGE_DIR).resolve()
    if storage_root != path and storage_root not in path.parents:
        raise HTTPException(status_code=400, detail="Stored file path is invalid.")
    return path


def store_project_file(project_id: str, dataset_id: str, safe_name: str, content: bytes) -> str:
    key = storage_key(project_id, dataset_id, safe_name)
    if STORAGE_BACKEND == "s3":
        storage_path = s3_path_for_key(key)
        bucket, object_key = parse_s3_storage_path(storage_path)
        try:
            s3_client().put_object(Bucket=bucket, Key=object_key, Body=content)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to upload file to S3 storage: {exc}") from exc
        return storage_path
    if STORAGE_BACKEND != "local":
        raise HTTPException(status_code=500, detail=f"Unsupported storage backend: {STORAGE_BACKEND}")
    storage_dir = STORAGE_DIR / project_id
    storage_dir.mkdir(parents=True, exist_ok=True)
    target_path = storage_dir / f"{dataset_id}_{safe_name}"
    target_path.write_bytes(content)
    return key


def read_stored_file(storage_path: str) -> bytes:
    if is_s3_storage_path(storage_path):
        bucket, object_key = parse_s3_storage_path(storage_path)
        try:
            response = s3_client().get_object(Bucket=bucket, Key=object_key)
            return response["Body"].read()
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise HTTPException(status_code=404, detail="Stored file is missing.") from exc
            raise HTTPException(status_code=502, detail=f"Failed to read file from S3 storage: {exc}") from exc
    path = stored_file_path(storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored file is missing.")
    return path.read_bytes()


def remove_stored_file(storage_path: str) -> None:
    if is_s3_storage_path(storage_path):
        try:
            bucket, object_key = parse_s3_storage_path(storage_path)
            s3_client().delete_object(Bucket=bucket, Key=object_key)
        except Exception:
            pass
        return
    try:
        path = stored_file_path(storage_path)
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        pass


def analysis_query_for_user(current_user: Dict[str, Any]) -> Tuple[str, Tuple[Any, ...]]:
    base = """
        SELECT analysis_runs.*, users.username, projects.name AS project_name
        FROM analysis_runs
        JOIN users ON users.id = analysis_runs.user_id
        LEFT JOIN projects ON projects.id = analysis_runs.project_id
    """
    return base + """ WHERE analysis_runs.user_id = ? AND (analysis_runs.project_id IS NULL OR
        projects.owner_id = ? OR EXISTS (SELECT 1 FROM project_members m WHERE m.project_id=projects.id AND m.user_id=?))
        ORDER BY analysis_runs.created_at DESC""", (current_user['id'], current_user['id'], current_user['id'])


def get_analysis_run_row(conn: sqlite3.Connection, run_id: str, current_user: Dict[str, Any]) -> sqlite3.Row:
    row = conn.execute("""SELECT r.*,u.username,p.name AS project_name FROM analysis_runs r
        JOIN users u ON u.id=r.user_id LEFT JOIN projects p ON p.id=r.project_id WHERE r.id=?""", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis history not found.")
    if row['project_id']:
        get_project_row(conn, row['project_id'], current_user)
    if row['user_id'] != current_user['id'] and not conn.execute('SELECT run_id FROM project_result_shares WHERE run_id=?', (run_id,)).fetchone():
        raise HTTPException(404, '结果未发布或不存在。')
    return row


def summarize_array(values: Any) -> Dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {"points": 0}
    return {
        "points": int(arr.size),
        "min": float(np.nanmin(arr)),
        "max": float(np.nanmax(arr)),
    }


def spectrum_result_content(result: Dict[str, Any]) -> bytes:
    wave = clean_floats(result.get("wavenumber", []))
    intensity = clean_floats(result.get("intensity", []))
    data = {"wavenumber": wave, "intensity": intensity}
    if result.get("baseline") is not None:
        data["baseline"] = clean_floats(result["baseline"])
    content = pd.DataFrame(data).to_csv(sep="\t", index=False, header=False, float_format="%.8g")
    return content.encode("utf-8")


def save_analysis_run(
    current_user: Dict[str, Any],
    analysis_type: str,
    source_name: str,
    steps: List[Step],
    input_payload: Dict[str, Any],
    result_payload: Dict[str, Any],
    history: List[Dict[str, Any]],
    title: Optional[str] = None,
    project_id: Optional[str] = None,
    source_dataset_id: Optional[str] = None,
    result_dataset_id: Optional[str] = None,
    result_filename: Optional[str] = None,
) -> Dict[str, Any]:
    if analysis_type not in ANALYSIS_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported analysis type.")
    run_id = uuid.uuid4().hex
    now = iso_now()
    clean_source = source_name or ("spectrum" if analysis_type == "spectrum" else "hyperspectral")
    clean_title = normalize_optional_text(title) or f"{clean_source} analysis"
    steps_payload = [step.dict() if hasattr(step, "dict") else step for step in steps]
    if analysis_type == 'hyperspectral':
        original = DATASETS.get(input_payload.get('dataset_id'))
        if original is not None:
            cube = original['data']
            input_payload = dict(input_payload, mean_spectrum=cube.reshape(-1, cube.shape[-1]).mean(axis=0).tolist())

    with db_connect() as conn:
        if project_id:
            get_project_row(conn, project_id, current_user)
        for asset_id in (source_dataset_id, result_dataset_id):
            if asset_id:
                asset = conn.execute('SELECT project_id FROM data_assets WHERE id=?', (asset_id,)).fetchone()
                if not asset or not project_id or asset['project_id'] != project_id:
                    raise HTTPException(400, '关联数据必须属于当前项目。')
        conn.execute(
            """
            INSERT INTO analysis_runs (
                id, user_id, project_id, source_dataset_id, result_dataset_id, title,
                analysis_type, source_name, steps_json, input_json, result_json,
                history_json, result_filename, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                current_user["id"],
                project_id,
                source_dataset_id,
                result_dataset_id,
                clean_title,
                analysis_type,
                clean_source,
                json.dumps(steps_payload, ensure_ascii=False),
                json.dumps(input_payload, ensure_ascii=False),
                json.dumps(result_payload, ensure_ascii=False),
                json.dumps(history, ensure_ascii=False),
                result_filename,
                now,
                now,
            ),
        )
        from history_resources import persist_arrays
        persist_arrays(globals(), conn, run_id, current_user, input_payload, result_payload)
        versions = [
            ("original", "Original version", input_payload),
            ("processed", "Processed version", {"steps": steps_payload, "history": history}),
            ("result", "Result version", result_payload),
        ]
        for version_type, label, payload in versions:
            conn.execute(
                """
                INSERT INTO analysis_versions (id, run_id, version_type, label, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uuid.uuid4().hex, run_id, version_type, label, json.dumps(payload, ensure_ascii=False), now),
            )
        row = conn.execute(
            """
            SELECT analysis_runs.*, users.username, projects.name AS project_name
            FROM analysis_runs
            JOIN users ON users.id = analysis_runs.user_id
            LEFT JOIN projects ON projects.id = analysis_runs.project_id
            WHERE analysis_runs.id = ?
            """,
            (run_id,),
        ).fetchone()
        version_rows = conn.execute("SELECT * FROM analysis_versions WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
    if project_id:
        for key in ('dataset_id', 'processed_dataset_id'):
            cached_id = input_payload.get(key) or result_payload.get(key)
            if cached_id in DATASETS:
                DATASETS[cached_id].setdefault('project_id', project_id)
    return row_to_analysis_run(row, [row_to_analysis_version(version) for version in version_rows])


def clean_floats(values: Any) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("empty numeric array")
    return np.nan_to_num(arr, copy=False)


def read_spectrum_with_metadata(content: bytes, filename: str = '', spectrum_index=None, allow_selection_preview=False):
    return parse_single(content, filename, spectrum_index, allow_selection_preview)


def read_spectrum(content: bytes, filename: str = '') -> Tuple[np.ndarray, np.ndarray]:
    wave, intensity, _ = read_spectrum_with_metadata(content, filename)
    return wave, intensity


def read_time_series(content: bytes, instrument: str) -> Tuple[np.ndarray, np.ndarray, List[Any]]:
    if instrument == "Horiba":
        df = pd.read_csv(io.BytesIO(content), sep="\t", header=None)
        wavenumber = df.iloc[0].dropna().values.astype(float)
        data = df.iloc[1:, 1 : len(wavenumber) + 1].values.astype(float)
        index = list(range(data.shape[0]))
        return wavenumber, data, index

    if instrument == "Renishaw":
        df = pd.read_csv(io.BytesIO(content), sep="\t", header=None)
        if df.shape[1] < 3:
            raise ValueError("Renishaw time series requires time, wavenumber, intensity columns.")
        df = df.iloc[:, :3]
        df.columns = ["time", "wavenumber", "intensity"]
        pivot = df.pivot_table(index="time", columns="wavenumber", values="intensity", aggfunc="first")
        return pivot.columns.values.astype(float), pivot.values.astype(float), pivot.index.tolist()

    if instrument == "Nanophoton":
        df = pd.read_csv(io.BytesIO(content), sep="\t")
        wavenumber = df.iloc[:, 0].values.astype(float)
        data_cols = np.arange(1, df.shape[1], 2)
        data = df.iloc[:, data_cols].values.astype(float).T[::-1]
        return wavenumber, data, list(range(data.shape[0]))

    raise ValueError(f"Unsupported instrument: {instrument}")


def extract_xy(name: str, key: str) -> int:
    match = re.match(r"x(?P<x>\d+)_y(?P<y>\d+)", str(name))
    if not match:
        raise ValueError(f"Cannot read Nanophoton coordinate from column {name!r}.")
    return int(match.group(key))


def read_imaging(content: bytes, instrument: str) -> Tuple[np.ndarray, np.ndarray, List[Any]]:
    if instrument == "Horiba":
        df = pd.read_csv(io.BytesIO(content), sep="\t", header=None)
        wavenumber = df.iloc[0].dropna().values.astype(float)
        coords = df.iloc[1:, :2].values.astype(float)
        spectra = df.iloc[1:, 2 : len(wavenumber) + 2].values.astype(float)
        x_vals = np.sort(np.unique(coords[:, 0]))
        y_vals = np.sort(np.unique(coords[:, 1]))
        data = np.zeros((len(x_vals), len(y_vals), spectra.shape[1]), dtype=float)
        x_lookup = {v: i for i, v in enumerate(x_vals)}
        y_lookup = {v: i for i, v in enumerate(y_vals)}
        for coord, spectrum in zip(coords, spectra):
            data[x_lookup[coord[0]], y_lookup[coord[1]]] = spectrum
        return wavenumber, data, coords.tolist()

    if instrument == "Nanophoton":
        df = pd.read_csv(io.BytesIO(content), sep="\t")
        wavenumber = df["Wavenumber"].values.astype(float)
        cols = [c for c in df.columns if str(c).startswith("x")]
        x_size = max(extract_xy(c, "x") for c in cols) + 1
        y_size = max(extract_xy(c, "y") for c in cols) + 1
        data = np.zeros((y_size, x_size, len(wavenumber)), dtype=float)
        for col in cols:
            x, y = extract_xy(col, "x"), extract_xy(col, "y")
            data[y, x] = df[col].values.astype(float)
        return wavenumber, data, [(extract_xy(c, "x"), extract_xy(c, "y")) for c in cols]

    raise ValueError(f"Unsupported imaging instrument: {instrument}")


def split_mapping_file(content: bytes, instrument: str, filename: str) -> bytes:
    from spectral_formats import standard_spectra_archive
    hints = {'auto': 'auto', 'Horiba': 'horiba', 'Renishaw': 'renishaw', 'Nanophoton': 'columns'}
    if instrument not in hints:
        raise ValueError('请选择自动识别或支持的仪器格式。')
    return standard_spectra_archive(content, filename, hint=hints[instrument], require_multiple=True)


def merge_spectrum_files(files: List[Tuple[str, bytes]]) -> bytes:
    mapping_data = []
    wavenumber = None
    for name, content in files:
        try:
            try:
                tmp = np.loadtxt(io.BytesIO(content), delimiter="\t")
            except ValueError:
                tmp = np.loadtxt(io.BytesIO(content), delimiter=",")
            tmp = np.atleast_2d(tmp)
            if tmp.shape[1] < 2:
                raise ValueError("expected at least two numeric columns")
            mapping_data.append(tmp[:, -1])
            if wavenumber is None:
                wavenumber = tmp[:, 0]
            elif len(wavenumber) != tmp.shape[0]:
                raise ValueError(f"{name} has a different spectral length.")
        except Exception as exc:
            raise ValueError(f"Error processing {name}: {exc}") from exc
    if wavenumber is None or not mapping_data:
        raise ValueError("Upload at least one spectrum file.")
    merged_array = np.vstack([wavenumber] + mapping_data)
    return pd.DataFrame(merged_array.T).to_csv(sep="\t", index=False, header=False, float_format="%.4f").encode("utf-8")


def horiba_to_nanophoton(content: bytes) -> bytes:
    stringio = io.StringIO(content.decode("utf-8-sig"))
    wavenumber = np.array([float(s) for s in stringio.readline().strip().split("\t") if s])
    remaining_data = np.loadtxt(stringio, delimiter="\t")
    remaining_data = np.atleast_2d(remaining_data)
    x_coords = remaining_data[:, 0]
    y_coords = remaining_data[:, 1]
    spectra = remaining_data[:, 2:]
    if wavenumber[0] > wavenumber[-1]:
        wavenumber = wavenumber[::-1]
        spectra = spectra[:, ::-1]
    x_unique = np.sort(np.unique(x_coords))
    y_unique = np.sort(np.unique(y_coords))
    x_index = np.searchsorted(x_unique, x_coords)
    y_index = np.searchsorted(y_unique, y_coords)
    order = np.lexsort((x_index, y_index))
    df = pd.DataFrame({"Wavenumber": wavenumber})
    for i in order:
        df[f"x{x_index[i]}_y{y_index[i]}"] = spectra[i, :]
    return df.to_csv(sep="\t", index=False, float_format="%.1f").encode("utf-8")


def nanophoton_to_horiba(content: bytes) -> bytes:
    imaging = pd.read_csv(io.BytesIO(content), delimiter="\t")
    wavenumber = imaging["Wavenumber"].values
    data_columns = [col for col in imaging.columns if str(col).startswith("x")]
    data = imaging[data_columns].values
    coords = pd.Series(data_columns).str.extract(r"x(\d+)_y(\d+)").astype(int)
    x_coords, y_coords = coords[0].values, coords[1].values
    if wavenumber[0] > wavenumber[-1]:
        wavenumber = wavenumber[::-1]
        data = data[::-1, :]
    x_unique = np.sort(np.unique(x_coords))
    y_unique = np.sort(np.unique(y_coords))
    x_index = np.searchsorted(x_unique, x_coords)
    y_index = np.searchsorted(y_unique, y_coords)
    order = np.lexsort((y_index, x_index))
    horiba_rows = []
    for idx in order:
        spectrum = data[:, idx]
        horiba_rows.append(np.concatenate([[x_index[idx], y_index[idx]], spectrum]))
    output = io.StringIO()
    output.write("\t\t" + "\t".join(map(str, wavenumber)) + "\n")
    np.savetxt(output, np.asarray(horiba_rows), fmt="%.1f", delimiter="\t")
    return output.getvalue().encode("utf-8")


def attachment_response(content: bytes, filename: str, media_type: str = "text/plain; charset=utf-8") -> Response:
    quoted = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{quoted}"'})


def normalize_window(window: int, order: int, length: int) -> int:
    window = max(3, int(window))
    if window % 2 == 0:
        window += 1
    if window >= length:
        window = length - 1 if (length - 1) % 2 else length - 2
    if window <= order:
        window = order + 2 + ((order + 2) % 2 == 0)
    if window >= length:
        raise ValueError("Savitzky-Golay window is too large for the selected range.")
    return window


def denoise_spectrum(y: np.ndarray, params: Dict[str, Any], method: str) -> np.ndarray:
    if method in __import__('legacy_algorithms').METHODS or str(method).startswith('v2_'):
        from legacy_algorithms import process
        return process(y.reshape(1,-1), params, method)[0][0]
    if method in ("skip", "", None):
        return y.copy()
    if method in ("sg", "savitzky_golay"):
        order = int(params.get("order", 3))
        window = normalize_window(int(params.get("window_size", 7)), order, len(y))
        return savgol_filter(y, window, order)
    if method == "wtd":
        wavelet = params.get("wavelet", "db3")
        level = int(params.get("level", 3))
        max_level = pywt.dwt_max_level(len(y), pywt.Wavelet(wavelet).dec_len)
        level = max(1, min(level, max_level))
        coeffs = pywt.wavedec(y, wavelet, level=level)
        sigma = np.median(np.abs(coeffs[-1])) / 0.6745 if len(coeffs[-1]) else 0
        threshold = 0.8 * np.sqrt(2 * np.log(max(len(y), 2))) * sigma
        coeffs = [c if i == 0 else pywt.threshold(c, threshold, mode="soft") for i, c in enumerate(coeffs)]
        return pywt.waverec(coeffs, wavelet)[: len(y)]
    if method == "tsvd":
        matrix = y.reshape(1, -1)
        return denoise_matrix(matrix, params, method)[0]
    if method == "peer":
        loops = int(params.get("loops", 3))
        window = normalize_window(2 * int(params.get("half_k_threshold", 2)) + 3, 2, len(y))
        out = y.copy()
        for _ in range(max(1, loops)):
            smooth = savgol_filter(out, window, 2)
            residual = out - smooth
            keep = np.abs(residual) > np.percentile(np.abs(residual), 85)
            out = np.where(keep, out, smooth)
        return out
    raise ValueError(f"Unknown denoise method: {method}")


def whittaker_baseline(y: np.ndarray, lam: float = 1e7, diff_order: int = 2, p: float = 0.01, niter: int = 15) -> np.ndarray:
    length = len(y)
    diff_order = max(1, min(int(diff_order), 3))
    dmat = sparse.eye(length, format="csc")
    for _ in range(diff_order):
        dmat = dmat[1:] - dmat[:-1]
    weights = np.ones(length)
    for _ in range(max(1, int(niter))):
        wmat = sparse.diags(weights, 0, shape=(length, length), format="csc")
        baseline = spsolve(wmat + float(lam) * (dmat.T @ dmat), weights * y)
        weights = p * (y > baseline) + (1 - p) * (y <= baseline)
    return baseline


def rolling_min_baseline(y: np.ndarray, half_window: int = 40) -> np.ndarray:
    half = max(2, int(half_window))
    series = pd.Series(y)
    base = series.rolling(2 * half + 1, center=True, min_periods=1).min()
    base = base.rolling(2 * half + 1, center=True, min_periods=1).mean()
    return base.values.astype(float)


def polynomial_baseline(y: np.ndarray, order: int = 3, quantile: float = 0.35) -> np.ndarray:
    x = np.linspace(-1, 1, len(y))
    mask = np.ones(len(y), dtype=bool)
    order = max(1, min(int(order), 5))
    for _ in range(8):
        coeff = np.polyfit(x[mask], y[mask], order)
        base = np.polyval(coeff, x)
        residual = y - base
        mask = residual <= np.quantile(residual, quantile)
        if mask.sum() <= order + 1:
            break
    return base


def baseline_correct(y: np.ndarray, params: Dict[str, Any], method: str) -> Tuple[np.ndarray, Optional[np.ndarray]]:
    if method in __import__('legacy_algorithms').METHODS or str(method).startswith('v2_'):
        from legacy_algorithms import process
        corrected, baseline = process(y.reshape(1,-1),params,method)
        return corrected[0], baseline[0]
    if method in ("skip", "", None):
        return y.copy(), None
    if method in ("airpls", "aspls", "aabs", "irsqr"):
        lam = float(params.get("lam", params.get("lambda_", 1e7)))
        order = int(params.get("diff_order", params.get("order_", 2)))
        p = float(params.get("quantile", 0.01))
        baseline = whittaker_baseline(y, lam=lam, diff_order=order, p=max(0.001, min(p, 0.49)))
    elif method in ("imodpoly", "penalizedpoly", "airpls_old"):
        baseline = polynomial_baseline(y, int(params.get("poly_order", params.get("order_", 3))))
    elif method in ("rollingball", "mormol", "snip"):
        baseline = rolling_min_baseline(y, int(params.get("half_window", params.get("max_half_window", 40))))
    else:
        raise ValueError(f"Unknown baseline method: {method}")
    return y - baseline, baseline


def denoise_matrix(matrix: np.ndarray, params: Dict[str, Any], method: str, *, hyperspectral=False) -> np.ndarray:
    if method in __import__('legacy_algorithms').METHODS or str(method).startswith('v2_'):
        from legacy_algorithms import process
        return process(matrix, params, method, hyperspectral=hyperspectral)[0]
    if method == "tsvd":
        threshold = float(params.get("threshold", 1e-3))
        u, s, vh = np.linalg.svd(matrix, full_matrices=False)
        keep = max(1, int(np.sum((s / max(s[0], 1e-12)) > threshold)))
        return (u[:, :keep] * s[:keep]) @ vh[:keep]
    return np.vstack([denoise_spectrum(row, params, method) for row in matrix])


def apply_pipeline(wavenumber: np.ndarray, data: np.ndarray, steps: List[Step], spatial_shape=None, *, hyperspectral=False) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray], List[Dict[str, Any]]]:
    validate_despike_order(steps)
    current_wn = wavenumber.copy()
    current = data.copy()
    baseline = None
    history: List[Dict[str, Any]] = []

    is_vector = current.ndim == 1
    if is_vector:
        current = current.reshape(1, -1)

    for step in steps:
        params = step.params or {}
        if step.type == "cut":
            start = float(params.get("start", current_wn.min()))
            end = float(params.get("end", current_wn.max()))
            mask = (current_wn >= min(start, end)) & (current_wn <= max(start, end))
            if not mask.any():
                raise ValueError("Cut range does not overlap with the wavenumber axis.")
            current_wn = current_wn[mask]
            current = current[:, mask]
            if baseline is not None:
                baseline = baseline[:, mask]
            history.append({"type": "cut", "range": [min(start, end), max(start, end)]})
        elif step.type == "despike":
            record = {"type": "despike", "method": step.method, "params": params}
            if step.method == 'despike':
                current, record['details'] = despike_matrix(current_wn, current, params)
            elif step.method != 'skip':
                raise ValueError('不支持的去鬼峰算法。')
            history.append(record)
        elif step.type == "denoise":
            record = {"type": "denoise", "method": step.method, "params": params}
            if step.method == "tshi":
                if is_vector or not spatial_shape or len(spatial_shape) != 2 or np.prod(spatial_shape) != len(current):
                    raise ValueError("TSHI 仅支持具有行列尺寸的高光谱成像数据，不支持时间序列或单光谱。")
                cube = current.reshape(*spatial_shape, current.shape[-1])
                current_wn, cube, details = tshi_denoise(current_wn, cube, params)
                current = cube.reshape(-1, cube.shape[-1])
                if baseline is not None:
                    baseline = baseline[:, details['selected_band_indices']]
                record['details'] = details
            else:
                current = denoise_matrix(current, params, step.method, hyperspectral=hyperspectral)
            history.append(record)
        elif step.type == "baseline":
            if step.method in __import__('legacy_algorithms').METHODS or step.method.startswith('v2_'):
                from legacy_algorithms import process
                current, baseline = process(current, params, step.method, hyperspectral=hyperspectral)
                history.append({"type":"baseline","method":step.method,"params":params})
                continue
            corrected = []
            baselines = []
            for row in current:
                row_corrected, row_baseline = baseline_correct(row, params, step.method)
                corrected.append(row_corrected)
                if row_baseline is not None:
                    baselines.append(row_baseline)
            current = np.vstack(corrected)
            baseline = np.vstack(baselines) if baselines else None
            history.append({"type": "baseline", "method": step.method, "params": params})

    return current_wn, current[0] if is_vector else current, (baseline[0] if is_vector and baseline is not None else baseline), history


def register_dataset(wavenumber: np.ndarray, data: np.ndarray, mode: str, filename: str, user=None, project_id=None) -> str:
    dataset_id = uuid.uuid4().hex
    DATASETS[dataset_id] = {
        "wavenumber": np.asarray(wavenumber, dtype=float),
        "data": np.asarray(data, dtype=float),
        "mode": mode,
        "filename": filename,
        "owner_id": user['id'] if user else None,
    }
    if project_id:
        DATASETS[dataset_id]['project_id'] = project_id
    return dataset_id


def cached_dataset(dataset_id, user):
    dataset = DATASETS.get(dataset_id)
    if dataset is None or dataset.get('owner_id') and (not user or dataset['owner_id'] != user['id']):
        raise HTTPException(404, '数据不存在、已过期或无权访问。')
    if dataset.get('project_id'):
        if not user:
            raise HTTPException(404, '数据不存在或无权访问。')
        with db_connect() as conn:
            get_project_row(conn, dataset['project_id'], user)
    return dataset


def closest_wavenumber_index(wavenumber: np.ndarray, target: Optional[float] = None) -> int:
    if target is None:
        target = float((wavenumber.min() + wavenumber.max()) / 2)
    return int(np.abs(wavenumber - float(target)).argmin())


def rounded_list(data: np.ndarray, decimals: int = 5) -> List[Any]:
    return np.round(np.nan_to_num(data), decimals=decimals).tolist()


def cube_preview(data: np.ndarray, max_pixels: int = 60) -> Tuple[np.ndarray, int]:
    if data.ndim != 3:
        return data, 1
    height, width, _ = data.shape
    scale = max(1, int(np.ceil(max(height, width) / max_pixels)))
    return data[::scale, ::scale], scale


def mapping_preview(wavenumber: np.ndarray, data: np.ndarray, target: Optional[float] = None) -> Dict[str, Any]:
    idx = closest_wavenumber_index(wavenumber, target)
    result = {"preview_wavenumber": float(wavenumber[idx]), "preview_wavenumber_index": idx, "preview_scale": 1}
    if data.ndim == 3:
        scale = max(1, int(np.ceil(max(data.shape[:2]) / 96)))
        result.update(preview=rounded_list(data[::scale, ::scale, idx]), preview_scale=scale)
    else:
        preview, axis, indices = time_series_preview(wavenumber, data)
        result.update(preview=rounded_list(preview), preview_x=axis.tolist(), preview_y=indices.tolist())
    return result


def mapping_payload(wavenumber: np.ndarray, data: np.ndarray, mode: str, filename: str, user=None) -> Dict[str, Any]:
    dataset_id = register_dataset(wavenumber, data, mode, filename, user)
    if data.ndim == 3:
        flat = data.reshape(-1, data.shape[-1])
        mean = flat.mean(axis=0)
    else:
        mean = data.mean(axis=0)
    return {
        "dataset_id": dataset_id,
        "filename": filename,
        "mode": mode,
        "wavenumber": wavenumber.tolist(),
        "shape": list(data.shape),
        **mapping_preview(wavenumber, data),
        "mean_spectrum": rounded_list(mean),
    }


@app.get('/api/legacy-algorithms')
def legacy_algorithm_options(user=Depends(get_current_user)):
    from legacy_algorithms import catalog
    return {'algorithms': catalog()}


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "code": 0,
        "msg": "RamanCloud preprocessing API is running",
        "data": {
            "framework": "FastAPI",
            "database": DB_ENGINE,
            "storage": STORAGE_BACKEND,
            "despike": {"method": "despike", "threshold": None, "fwhm_threshold": 4, "interpolation": "linear"},
            "denoise": ["sg", "wtd", "peer", "tsvd", "tshi", "skip"],
            "tshi": {"bm3d_available": bm3d_available(), "max_elements": 8000000, "max_bands": 256},
            "upload_formats": sorted(SPECTRAL_EXTENSIONS),
            "baseline": ["airpls", "aspls", "aabs", "imodpoly", "penalizedpoly", "rollingball", "mormol", "snip", "irsqr", "skip"],
            "spectra_demos": list(DEMO_SPECTRA),
            "mapping_demos": list(DEMO_MAPPING),
            "hyperspectral_upload": {"chunk_bytes": CHUNK_BYTES},
        },
    }


@app.post("/api/auth/register")
def register(payload: RegisterPayload) -> Dict[str, Any]:
    username = normalize_username(payload.username)
    email = normalize_email(payload.email)
    display_name = normalize_optional_text(payload.display_name) or username
    if payload.role != 'user':
        raise HTTPException(status_code=403, detail='注册仅创建普通用户，系统管理员由部署初始化或已有管理员授权。')
    role = 'user'
    salt, digest = password_hash(payload.password)
    user_id = uuid.uuid4().hex
    now = iso_now()

    with db_connect() as conn:
        try:
            conn.execute(
                """
                INSERT INTO users (
                    id, username, email, display_name, password_salt, password_hash,
                    role, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (user_id, username, email, display_name, salt, digest, role, now, now),
            )
        except DB_INTEGRITY_ERRORS as exc:
            raise HTTPException(status_code=409, detail="Username or email already exists.") from exc
        token = create_session(conn, user_id)
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return {"code": 0, "msg": "Registration successful", "data": {"token": token, "user": row_to_user(user_row)}}


@app.post("/api/auth/login")
def login(payload: LoginPayload) -> Dict[str, Any]:
    identifier = payload.identifier.strip()
    with db_connect() as conn:
        user_row = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (identifier, identifier.lower()),
        ).fetchone()
        if user_row is None or not verify_password(payload.password, user_row["password_salt"], user_row["password_hash"]):
            raise HTTPException(status_code=401, detail="Username or password is incorrect.")
        if not bool(user_row["is_active"]):
            raise HTTPException(status_code=403, detail="This account has been disabled.")
        token = create_session(conn, user_row["id"])
        updated_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_row["id"],)).fetchone()

    return {"code": 0, "msg": "Login successful", "data": {"token": token, "user": row_to_user(updated_row)}}


@app.get("/api/auth/me")
def me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return {"code": 0, "msg": "Current user loaded", "data": {"user": current_user}}


@app.post("/api/auth/logout")
def logout(
    current_user: Dict[str, Any] = Depends(get_current_user),
    authorization: Optional[str] = Header(None),
) -> Dict[str, Any]:
    token = authorization.split(" ", 1)[1].strip() if authorization else ""
    with db_connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash = ? AND user_id = ?", (hash_token(token), current_user["id"]))
    return {"code": 0, "msg": "Logout successful", "data": {}}


@app.post("/api/auth/change-password")
def change_password(payload: PasswordChangePayload, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with db_connect() as conn:
        user_row = conn.execute("SELECT * FROM users WHERE id = ?", (current_user["id"],)).fetchone()
        if user_row is None or not verify_password(payload.old_password, user_row["password_salt"], user_row["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect.")
        salt, digest = password_hash(payload.new_password)
        now = iso_now()
        conn.execute(
            "UPDATE users SET password_salt = ?, password_hash = ?, updated_at = ? WHERE id = ?",
            (salt, digest, now, current_user["id"]),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (current_user["id"],))
    return {"code": 0, "msg": "Password updated. Please log in again.", "data": {}}


@app.get("/api/account/space")
def account_space(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with db_connect() as conn:
        if current_user["role"] == "admin":
            project_count = int(conn.execute("SELECT COUNT(*) AS count FROM projects").fetchone()["count"])
            dataset_count = int(conn.execute("SELECT COUNT(*) AS count FROM data_assets").fetchone()["count"])
            analysis_count = int(conn.execute("SELECT COUNT(*) AS count FROM analysis_runs").fetchone()["count"])
        else:
            project_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM projects
                    WHERE owner_id = ?
                       OR EXISTS (
                            SELECT 1 FROM project_members
                            WHERE project_members.project_id = projects.id
                              AND project_members.user_id = ?
                       )
                    """,
                    (current_user["id"], current_user["id"]),
                ).fetchone()["count"]
            )
            dataset_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM data_assets
                    JOIN projects ON projects.id = data_assets.project_id
                    WHERE projects.owner_id = ?
                       OR EXISTS (
                            SELECT 1 FROM project_members
                            WHERE project_members.project_id = projects.id
                              AND project_members.user_id = ?
                       )
                    """,
                    (current_user["id"], current_user["id"]),
                ).fetchone()["count"]
            )
            analysis_count = int(
                conn.execute(
                    "SELECT COUNT(*) AS count FROM analysis_runs WHERE user_id = ?",
                    (current_user["id"],),
                ).fetchone()["count"]
            )
    return {
        "code": 0,
        "msg": "Personal space loaded",
        "data": {
            "user": current_user,
            "sections": [
                {"key": "projects", "label": "My Projects", "count": project_count, "status": "Project management is available."},
                {"key": "datasets", "label": "My Data", "count": dataset_count, "status": "Saved data is available."},
                {"key": "analyses", "label": "Recent Analyses", "count": analysis_count, "status": "Analysis history is available."},
            ],
        },
    }


@app.get("/api/projects")
def list_projects(
    q: Optional[str] = None,
    category: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    query, params = project_query_for_user(current_user)
    with db_connect() as conn:
        rows = conn.execute(query, params).fetchall()

    projects = [row_to_project(row) for row in rows]
    if q:
        needle = q.strip().lower()
        projects = [
            project for project in projects
            if needle in project["name"].lower()
            or needle in project["description"].lower()
            or needle in project["category"].lower()
        ]
    if category:
        wanted = category.strip().lower()
        projects = [project for project in projects if project["category"].lower() == wanted]
    return {"code": 0, "msg": "Projects loaded", "data": {"projects": projects}}


@app.post("/api/projects")
def create_project(payload: ProjectPayload, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    name = payload.name.strip()
    description = normalize_optional_text(payload.description)
    category = normalize_optional_text(payload.category)
    project_id = uuid.uuid4().hex
    now = iso_now()
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, owner_id, name, description, category, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, current_user["id"], name, description, category, now, now),
        )
        row = conn.execute(
            """
            SELECT projects.*, users.username AS owner_username, 0 AS dataset_count, 0 AS raw_count, 0 AS processed_count
            FROM projects
            JOIN users ON users.id = projects.owner_id
            WHERE projects.id = ?
            """,
            (project_id,),
        ).fetchone()
        project_event(conn, project_id, current_user, 'create_project', name)
    return {"code": 0, "msg": "Project created", "data": {"project": row_to_project(row)}}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with db_connect() as conn:
        access = get_project_row(conn, project_id, current_user)
        row = conn.execute(
            """
            SELECT projects.*, users.username AS owner_username,
                   COUNT(data_assets.id) AS dataset_count,
                   SUM(CASE WHEN data_assets.data_kind = 'raw' THEN 1 ELSE 0 END) AS raw_count,
                   SUM(CASE WHEN data_assets.data_kind = 'processed' THEN 1 ELSE 0 END) AS processed_count
            FROM projects
            JOIN users ON users.id = projects.owner_id
            LEFT JOIN data_assets ON data_assets.project_id = projects.id
            WHERE projects.id = ?
            GROUP BY projects.id
            """,
            (project_id,),
        ).fetchone()
    return {"code": 0, "msg": "Project loaded", "data": {"project": dict(row_to_project(row), my_role=access['my_role'])}}


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdatePayload, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    updates: List[str] = []
    params: List[Any] = []
    if payload.name is not None:
        updates.append("name = ?")
        params.append(payload.name.strip())
    if payload.description is not None:
        updates.append("description = ?")
        params.append(normalize_optional_text(payload.description))
    if payload.category is not None:
        updates.append("category = ?")
        params.append(normalize_optional_text(payload.category))
    if not updates:
        raise HTTPException(status_code=400, detail="No project fields were provided.")
    updates.append("updated_at = ?")
    params.append(iso_now())
    params.append(project_id)
    with db_connect() as conn:
        require_project_owner(conn, project_id, current_user)
        conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params)
        row = conn.execute(
            """
            SELECT projects.*, users.username AS owner_username,
                   COUNT(data_assets.id) AS dataset_count,
                   SUM(CASE WHEN data_assets.data_kind = 'raw' THEN 1 ELSE 0 END) AS raw_count,
                   SUM(CASE WHEN data_assets.data_kind = 'processed' THEN 1 ELSE 0 END) AS processed_count
            FROM projects
            JOIN users ON users.id = projects.owner_id
            LEFT JOIN data_assets ON data_assets.project_id = projects.id
            WHERE projects.id = ?
            GROUP BY projects.id
            """,
            (project_id,),
        ).fetchone()
        project_event(conn, project_id, current_user, 'update_project', project_id)
    return {"code": 0, "msg": "Project updated", "data": {"project": row_to_project(row)}}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with db_connect() as conn:
        p = require_project_owner(conn, project_id, current_user)
        if p['owner_id'] != current_user['id']:
            raise HTTPException(403, '只有项目所有者可删除项目。')
        if (conn.execute('SELECT id FROM data_assets WHERE project_id=? LIMIT 1', (project_id,)).fetchone()
                or conn.execute('SELECT id FROM analysis_runs WHERE project_id=? LIMIT 1', (project_id,)).fetchone()
                or conn.execute('SELECT id FROM ai_workflows WHERE project_id=? LIMIT 1', (project_id,)).fetchone()):
            raise HTTPException(409, '项目含数据或处理记录，不能直接删除，请保留或先整理未引用内容。')
        dataset_rows = conn.execute("SELECT storage_path FROM data_assets WHERE project_id = ?", (project_id,)).fetchall()
        conn.execute("DELETE FROM data_assets WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM project_members WHERE project_id = ?", (project_id,))
        conn.execute('DELETE FROM project_invitations WHERE project_id=?', (project_id,))
        conn.execute('DELETE FROM project_events WHERE project_id=?', (project_id,))
        conn.execute('DELETE FROM project_result_shares WHERE project_id=?', (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    for row in dataset_rows:
        remove_stored_file(row["storage_path"])
    return {"code": 0, "msg": "Project deleted", "data": {}}


@app.get("/api/projects/{project_id}/datasets")
def list_project_datasets(
    project_id: str,
    q: Optional[str] = None,
    category: Optional[str] = None,
    data_kind: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    with db_connect() as conn:
        get_project_row(conn, project_id, current_user)
        rows = conn.execute(
            """
            SELECT data_assets.*, users.username AS owner_username
            FROM data_assets
            JOIN users ON users.id = data_assets.owner_id
            WHERE data_assets.project_id = ?
            ORDER BY data_assets.updated_at DESC
            """,
            (project_id,),
        ).fetchall()

    datasets = [item for item in (row_to_dataset(row) for row in rows) if not item['metadata'].get('withdrawn')]
    if q:
        needle = q.strip().lower()
        datasets = [
            item for item in datasets
            if needle in item["display_name"].lower()
            or needle in item["filename"].lower()
            or needle in item["category"].lower()
        ]
    if category:
        wanted = category.strip().lower()
        datasets = [item for item in datasets if item["category"].lower() == wanted]
    if data_kind:
        wanted_kind = normalize_data_kind(data_kind)
        datasets = [item for item in datasets if item["data_kind"] == wanted_kind]
    return {"code": 0, "msg": "Datasets loaded", "data": {"datasets": datasets}}


@app.post("/api/projects/{project_id}/datasets/upload")
async def upload_project_datasets(
    project_id: str,
    files: List[UploadFile] = File(...),
    data_kind: str = Form("raw"),
    category: Optional[str] = Form(None),
    data_type: str = Form("auto"),
    instrument: str = Form("auto"),
    mode: str = Form("imaging"),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    normalized_kind = normalize_data_kind(data_kind)
    normalized_type = normalize_data_type(data_type)
    normalized_category = normalize_optional_text(category)
    created: List[Dict[str, Any]] = []

    with db_connect() as conn:
        get_project_row(conn, project_id, current_user)
        for file in files:
            content = await file.read(MAX_UPLOAD + 1)
            if not content or len(content) > MAX_UPLOAD:
                raise HTTPException(400, '文件为空或超过 128 MB。')
            dataset_id = uuid.uuid4().hex
            safe_name = clean_storage_name(file.filename)
            relative_path = store_project_file(project_id, dataset_id, safe_name, content)
            detected_type, metadata = detect_dataset_metadata(content, safe_name, normalized_type, instrument, mode)
            now = iso_now()
            conn.execute(
                """
                INSERT INTO data_assets (
                    id, project_id, owner_id, filename, display_name, category, data_kind,
                    data_type, instrument, mode, storage_path, file_size, metadata_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dataset_id,
                    project_id,
                    current_user["id"],
                    safe_name,
                    Path(safe_name).stem,
                    normalized_category,
                    normalized_kind,
                    detected_type,
                    instrument if detected_type == "mapping" else None,
                    metadata.get('detected_mode', mode) if detected_type == "mapping" else None,
                    relative_path,
                    len(content),
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
            row = conn.execute(
                """
                SELECT data_assets.*, users.username AS owner_username
                FROM data_assets
                JOIN users ON users.id = data_assets.owner_id
                WHERE data_assets.id = ?
                """,
                (dataset_id,),
            ).fetchone()
            created.append(row_to_dataset(row))
            project_event(conn, project_id, current_user, 'upload_dataset', safe_name)

    return {"code": 0, "msg": "Datasets uploaded", "data": {"datasets": created}}


@app.patch("/api/datasets/{dataset_id}")
def update_dataset(dataset_id: str, payload: DatasetUpdatePayload, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    updates: List[str] = []
    params: List[Any] = []
    if payload.display_name is not None:
        updates.append("display_name = ?")
        params.append(payload.display_name.strip())
    if payload.category is not None:
        updates.append("category = ?")
        params.append(normalize_optional_text(payload.category))
    if payload.data_kind is not None:
        updates.append("data_kind = ?")
        params.append(normalize_data_kind(payload.data_kind))
    if not updates:
        raise HTTPException(status_code=400, detail="No dataset fields were provided.")

    with db_connect() as conn:
        row = conn.execute("SELECT * FROM data_assets WHERE id = ?", (dataset_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        get_project_row(conn, row['project_id'], current_user)
        if row['owner_id'] != current_user['id']:
            require_project_owner(conn, row['project_id'], current_user)
        if payload.data_kind is not None and normalize_data_kind(payload.data_kind) != row['data_kind']:
            raise HTTPException(400, '原始数据和处理后数据的来源分类不可更改，请保存新的处理结果。')
        now = iso_now()
        updates.append("updated_at = ?")
        params.append(now)
        params.append(dataset_id)
        conn.execute(f"UPDATE data_assets SET {', '.join(updates)} WHERE id = ?", params)
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, row["project_id"]))
        updated = conn.execute(
            """
            SELECT data_assets.*, users.username AS owner_username
            FROM data_assets
            JOIN users ON users.id = data_assets.owner_id
            WHERE data_assets.id = ?
            """,
            (dataset_id,),
        ).fetchone()
    return {"code": 0, "msg": "Dataset updated", "data": {"dataset": row_to_dataset(updated)}}


@app.delete("/api/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM data_assets WHERE id = ?", (dataset_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        get_project_row(conn, row['project_id'], current_user)
        if row['owner_id'] != current_user['id']:
            raise HTTPException(403, '共享数据目前仅允许上传者删除，不能删除他人的科研数据。')
        if (conn.execute('SELECT id FROM analysis_runs WHERE source_dataset_id=? OR result_dataset_id=? LIMIT 1', (dataset_id, dataset_id)).fetchone()
                or conn.execute('SELECT id FROM ai_workflows WHERE source_dataset_id=? LIMIT 1', (dataset_id,)).fetchone()):
            raise HTTPException(409, '此数据已被处理记录引用，不能删除。')
        project_event(conn, row['project_id'], current_user, 'delete_dataset', dataset_id)
        conn.execute("DELETE FROM data_assets WHERE id = ?", (dataset_id,))
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (iso_now(), row["project_id"]))
    remove_stored_file(row["storage_path"])
    return {"code": 0, "msg": "Dataset deleted", "data": {}}


@app.get("/api/datasets/{dataset_id}/download")
def download_dataset(dataset_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> Response:
    with db_connect() as conn:
        row = conn.execute("SELECT * FROM data_assets WHERE id = ?", (dataset_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Dataset not found.")
        get_project_row(conn, row["project_id"], current_user)
        project_event(conn, row['project_id'], current_user, 'download_dataset', dataset_id)
    return attachment_response(read_stored_file(row["storage_path"]), row["filename"])


@app.get("/api/analysis-runs")
def list_analysis_runs(
    q: Optional[str] = None,
    analysis_type: Optional[str] = None,
    project_id: Optional[str] = None,
    summary: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    query, params = analysis_query_for_user(current_user)
    with db_connect() as conn:
        if project_id:
            get_project_row(conn, project_id, current_user)
            query = """SELECT r.*,u.username,p.name AS project_name FROM analysis_runs r
                JOIN users u ON u.id=r.user_id JOIN projects p ON p.id=r.project_id
                JOIN project_result_shares s ON s.run_id=r.id WHERE p.id=? ORDER BY s.shared_at DESC"""
            params = (project_id,)
        rows = conn.execute(query, params).fetchall()
        runs = []
        for row in rows:
            version_rows = [] if summary else conn.execute(
                "SELECT * FROM analysis_versions WHERE run_id = ? ORDER BY created_at ASC",
                (row["id"],),
            ).fetchall()
            run = row_to_analysis_run(row, [row_to_analysis_version(version) for version in version_rows])
            run['is_shared'] = bool(conn.execute('SELECT run_id FROM project_result_shares WHERE run_id=?', (row['id'],)).fetchone())
            if run['analysis_type'] == 'spectrum' and run['result'].get('ai_workflow_id'):
                batch = conn.execute('''SELECT b.id,b.name,b.user_id FROM ai_batch_items i
                    JOIN ai_workflow_batches b ON b.id=i.batch_id WHERE i.workflow_id=?''',
                    (run['result']['ai_workflow_id'],)).fetchone()
                if batch:
                    run['batch_id'], run['batch_name'] = batch['id'], batch['name']
                    run['batch_owned'] = batch['user_id'] == current_user['id']
            runs.append(run)
            if summary:
                result = run['result']
                compact = {k: result[k] for k in ('ai_workflow_id','job_id') if k in result}
                values = result.get('intensity', result.get('mean_spectrum', []))
                axis = result.get('wavenumber', [])
                if len(values) and len(values) == len(axis):
                    indices = np.linspace(0,len(values)-1,min(60,len(values)),dtype=int)
                    compact.update(wavenumber=[axis[i] for i in indices], intensity=[values[i] for i in indices])
                run.update(input={}, result=compact, history=[], steps=[], versions=[])
    if analysis_type:
        wanted = analysis_type.strip().lower()
        runs = [run for run in runs if run["analysis_type"] == wanted]
    if q:
        needle = q.strip().lower()
        runs = [
            run for run in runs
            if needle in run["title"].lower()
            or needle in run["source_name"].lower()
            or needle in (run["project_name"] or "").lower()
        ]
    return {"code": 0, "msg": "Analysis history loaded", "data": {"runs": runs}}


@app.get("/api/analysis-runs/{run_id}")
def get_analysis_run(run_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with db_connect() as conn:
        row = get_analysis_run_row(conn, run_id, current_user)
        version_rows = conn.execute("SELECT * FROM analysis_versions WHERE run_id = ? ORDER BY created_at ASC", (run_id,)).fetchall()
        shared = bool(conn.execute('SELECT run_id FROM project_result_shares WHERE run_id=?', (run_id,)).fetchone())
    run = row_to_analysis_run(row, [row_to_analysis_version(version) for version in version_rows])
    from model_history import enrich_model_history
    with db_connect() as conn:
        run = enrich_model_history(conn, run)
    run['is_shared'] = shared
    # Derive the display number for older saved spectra without rewriting them.
    result = run['result']
    if result.get('ai_workflow_id') and result.get('ai_version_id') and not result.get('ai_version_number'):
        with db_connect() as conn:
            ordered = conn.execute('SELECT id FROM ai_plan_versions WHERE workflow_id=? ORDER BY created_at,id', (result['ai_workflow_id'],)).fetchall()
        result['ai_version_number'] = next((i + 1 for i, item in enumerate(ordered) if item['id'] == result['ai_version_id']), None)
    return {"code": 0, "msg": "Analysis history loaded", "data": {"run": run}}


@app.delete("/api/analysis-runs/{run_id}")
def delete_analysis_run(run_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with db_connect() as conn:
        row = get_analysis_run_row(conn, run_id, current_user)
        if row['user_id'] != current_user['id']:
            raise HTTPException(403, '不能删除他人的处理记录。')
        if conn.execute('SELECT run_id FROM project_result_shares WHERE run_id=?', (run_id,)).fetchone():
            raise HTTPException(409, '请先撤下项目共享结果，再删除自己的记录。')
        from history_resources import delete_artifacts
        paths = delete_artifacts(globals(), conn, run_id)
        conn.execute("DELETE FROM analysis_versions WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM analysis_runs WHERE id = ?", (run_id,))
    for path in paths:
        remove_stored_file(path)
    return {"code": 0, "msg": "Analysis history deleted", "data": {}}


@app.get("/api/analysis-runs/{run_id}/download")
def download_analysis_result(run_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> Response:
    with db_connect() as conn:
        row = get_analysis_run_row(conn, run_id, current_user)
        run = row_to_analysis_run(row)
        if row['project_id']:
            project_event(conn, row['project_id'], current_user, 'download_result', run_id)
    if run["analysis_type"] == "hyperspectral":
        from history_resources import restore_arrays
        restore_arrays(globals(), run)
        dataset = DATASETS.get(run['result'].get('processed_dataset_id'))
        if not dataset:
            raise HTTPException(status_code=400, detail="完整成像数据缓存已过期，请重新上传源文件并使用已保存参数处理。")
        if dataset['data'].ndim != 3:
            raise HTTPException(status_code=400, detail="时间序列结果请在处理页面下载。")
        return attachment_response(mat_result(dataset['wavenumber'], dataset['data'], dataset.get('history', [])), f"{run['title']}_result.mat", 'application/x-matlab-data')
    if run["analysis_type"] in {"structure_generation", "library_matching", "mixture_analysis", "peak_fitting"}:
        return attachment_response(json.dumps(run, ensure_ascii=False).encode('utf-8'), run['result_filename'] or 'result.json', 'application/json')
    if run["analysis_type"] != "spectrum":
        raise HTTPException(status_code=400, detail="Only saved single-spectrum results can be downloaded directly from history.")
    content = spectrum_result_content(run["result"])
    filename = run["result_filename"] or f"{run['title']}_result.txt"
    return attachment_response(content, filename)


@app.post("/api/analysis-runs/{run_id}/rerun")
def rerun_analysis(run_id: str, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with db_connect() as conn:
        row = get_analysis_run_row(conn, run_id, current_user)
        run = row_to_analysis_run(row)
    if run["analysis_type"] in {"structure_generation", "library_matching", "mixture_analysis"}:
        raise HTTPException(400, '请在相应功能页面打开保存任务，检查模型与输入后重新运行。')
    if run["analysis_type"] == "hyperspectral":
        source = run["input"]
        from history_resources import restore_arrays
        restore_arrays(globals(), run)
        dataset_id = source.get("dataset_id")
        if not dataset_id or dataset_id not in DATASETS:
            raise HTTPException(status_code=400, detail="The source mapping dataset has expired. Load the same data and use the saved parameters to rerun.")
        dataset = DATASETS[dataset_id]
        if dataset.get('owner_id') != current_user['id']:
            # A member reruns the shared input as their own private analysis.
            dataset_id = register_dataset(dataset['wavenumber'], dataset['data'], dataset['mode'], dataset['filename'], current_user, run['project_id'])
            source = dict(source, dataset_id=dataset_id)
            dataset = DATASETS[dataset_id]
        steps = [Step(**step) for step in run["steps"]]
        source_data = dataset["data"]
        wave = dataset["wavenumber"]
        spectra = source_data.reshape(-1, source_data.shape[-1]) if source_data.ndim == 3 else source_data
        try:
            spatial_shape = source_data.shape[:2] if dataset['mode'] == 'imaging' and source_data.ndim == 3 else None
            out_wave, out_spectra, baseline, history = apply_pipeline(wave, spectra, steps, spatial_shape, hyperspectral=True)
        except TSVDWorkLimitError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        mean = out_spectra.mean(axis=0)
        mode = dataset["mode"]
        if mode == "imaging" and source_data.ndim == 3:
            processed_cube = out_spectra.reshape(source_data.shape[0], source_data.shape[1], out_spectra.shape[-1])
        else:
            processed_cube = out_spectra
        processed_id = register_dataset(out_wave, processed_cube, mode, "rerun_" + dataset["filename"], current_user, run['project_id'])
        DATASETS[processed_id]['history'] = history
        tshi = next((item['details'] for item in reversed(history) if item.get('method') == 'tshi'), None)
        result_payload = {
            "wavenumber": out_wave.tolist(),
            "mean_spectrum": rounded_list(mean),
            **mapping_preview(out_wave, processed_cube, tshi['center_wavenumber'] if tshi else None),
            "shape": list(processed_cube.shape),
            "processed_dataset_id": processed_id,
            "baseline_mean": rounded_list(baseline.mean(axis=0)) if baseline is not None else None,
            "summary": {
                "wavenumber": summarize_array(out_wave),
                "shape": list(processed_cube.shape),
                "mode": mode,
                "has_baseline": baseline is not None,
            },
        }
        rerun = save_analysis_run(
            current_user=current_user,
            analysis_type="hyperspectral",
            source_name=run["source_name"],
            steps=steps,
            input_payload=dict(source, wavenumber=wave.tolist(),
                               mean_spectrum=rounded_list(spectra.mean(axis=0))),
            result_payload=result_payload,
            history=history,
            title=f"{run['title']} rerun",
            project_id=run["project_id"],
            source_dataset_id=run["source_dataset_id"],
            result_filename=run["result_filename"] or f"rerun_{run['source_name'] or 'hyperspectral'}",
        )
        return {"code": 0, "msg": "Analysis rerun completed", "data": {"run": rerun, "result": result_payload}}
    if run["analysis_type"] != "spectrum":
        raise HTTPException(status_code=400, detail="Unsupported analysis type.")
    source = run["input"]
    if "wavenumber" not in source or "intensity" not in source:
        raise HTTPException(status_code=400, detail="This history does not contain enough source data to rerun.")
    steps = [Step(**step) for step in run["steps"]]
    wave = clean_floats(source["wavenumber"])
    intensity = clean_floats(source["intensity"])
    out_wave, out_intensity, baseline, history = apply_pipeline(wave, intensity, steps)
    result_payload = {
        "wavenumber": out_wave.tolist(),
        "intensity": out_intensity.tolist(),
        "baseline": baseline.tolist() if baseline is not None else None,
        "summary": {
            "wavenumber": summarize_array(out_wave),
            "intensity": summarize_array(out_intensity),
            "has_baseline": baseline is not None,
        },
    }
    rerun = save_analysis_run(
        current_user=current_user,
        analysis_type="spectrum",
        source_name=run["source_name"],
        steps=steps,
        input_payload=source,
        result_payload=result_payload,
        history=history,
        title=f"{run['title']} rerun",
        project_id=run["project_id"],
        source_dataset_id=run["source_dataset_id"],
        result_filename=run["result_filename"] or f"rerun_{run['source_name'] or 'spectrum'}.txt",
    )
    return {"code": 0, "msg": "Analysis rerun completed", "data": {"run": rerun, "result": result_payload}}


@app.get("/api/users")
def list_users(_: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    with db_connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    return {"code": 0, "msg": "Users loaded", "data": {"users": [row_to_user(row) for row in rows]}}


@app.patch("/api/users/{user_id}")
def update_user(user_id: str, payload: UserUpdatePayload, admin_user: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    updates: List[str] = []
    params: List[Any] = []

    if payload.role is not None:
        if payload.role not in AUTH_ROLES:
            raise HTTPException(status_code=400, detail="Unsupported role.")
        updates.append("role = ?")
        params.append(payload.role)
    if payload.is_active is not None:
        if user_id == admin_user["id"] and payload.is_active is False:
            raise HTTPException(status_code=400, detail="You cannot disable your own administrator account.")
        updates.append("is_active = ?")
        params.append(1 if payload.is_active else 0)
    if payload.display_name is not None:
        updates.append("display_name = ?")
        params.append(normalize_optional_text(payload.display_name) or None)
    if payload.email is not None:
        updates.append("email = ?")
        params.append(normalize_email(payload.email))

    if not updates:
        raise HTTPException(status_code=400, detail="No user fields were provided.")

    with db_connect() as conn:
        target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        if target["role"] == "admin":
            role_after = payload.role if payload.role is not None else target["role"]
            active_after = payload.is_active if payload.is_active is not None else bool(target["is_active"])
            if (role_after != "admin" or not active_after) and active_admin_count(conn, exclude_user_id=user_id) == 0:
                raise HTTPException(status_code=400, detail="At least one active administrator is required.")
        updates.append("updated_at = ?")
        params.append(iso_now())
        params.append(user_id)
        try:
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        except DB_INTEGRITY_ERRORS as exc:
            raise HTTPException(status_code=409, detail="Email already exists.") from exc
        if payload.is_active is False:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        updated = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return {"code": 0, "msg": "User updated", "data": {"user": row_to_user(updated)}}


@app.get("/api/demo/{name}")
def demo_spectrum(name: str) -> Dict[str, Any]:
    if name not in DEMO_SPECTRA:
        raise HTTPException(status_code=404, detail="Demo spectrum not found.")
    wave, intensity = read_spectrum((SAMPLES / DEMO_SPECTRA[name]).read_bytes())
    return {"code": 0, "msg": "Demo loaded", "data": {"name": name, "wavenumber": wave.tolist(), "intensity": intensity.tolist()}}


@app.post("/api/upload")
async def upload(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    spectra = []
    for file in files:
        try:
            wave, intensity, metadata = read_spectrum_with_metadata(await file.read(MAX_UPLOAD + 1), file.filename or '')
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        spectra.append({"filename": file.filename, "wavenumber": wave.tolist(), "intensity": intensity.tolist(), "length": len(wave), "import_metadata": metadata})
    return {"code": 0, "msg": "Upload successful", "data": {"spectra": spectra}}


@app.get("/api/demo-hyperspectral/{name}")
def demo_mapping(name: str, current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)) -> Dict[str, Any]:
    if name not in DEMO_MAPPING:
        raise HTTPException(status_code=404, detail="Demo mapping not found.")
    sample, instrument, mode = DEMO_MAPPING[name]
    content = (SAMPLES / sample).read_bytes()
    if mode == "time_series":
        wave, data, _ = read_time_series(content, instrument)
    else:
        wave, data, _ = read_imaging(content, instrument)
    return {"code": 0, "msg": "Demo mapping loaded", "data": mapping_payload(wave, data, mode, sample, current_user)}


@app.post("/api/upload-hyperspectral")
async def upload_mapping(
    file: UploadFile = File(...),
    instrument: str = Form("auto"),
    mode: str = Form("imaging"),
    height: Optional[int] = Form(None),
    width: Optional[int] = Form(None),
    layout: str = Form("auto"),
    pixel_order: str = Form("F"),
    upload_id: Optional[str] = Form(None),
    chunk_index: int = Form(0),
    total_size: Optional[int] = Form(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    if upload_id is None:
        content = await file.read(MAX_UPLOAD + 1)
    else:
        chunk = await file.read(CHUNK_BYTES + 1)
        descriptor = (file.filename, mode, instrument, height, width, layout, pixel_order)
        content = await run_in_threadpool(accept_chunk, DATA_DIR, str(current_user['id']), upload_id,
                                          chunk_index, total_size, chunk, MAX_UPLOAD, descriptor)
        if content is None:
            return {"code": 0, "data": {"complete": False}}
    if not content or len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=400, detail="文件为空或超过 128 MB。")
    try:
        if mode not in {"imaging", "time_series"}:
            raise ValueError("请选择成像或时间序列模式。")
        wave, data, metadata = await run_in_threadpool(parse_dataset, content, file.filename or '', mode, instrument, height, width, layout, pixel_order)
        result = await run_in_threadpool(mapping_payload, wave, data, mode, file.filename or "mapping.txt", current_user)
        result['import_metadata'] = metadata
        return {"code": 0, "msg": "Mapping uploaded", "data": result}
    except (ValueError, KeyError, UnicodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/tools/split")
async def split_mapping_tool(file: UploadFile = File(...), instrument: str = Form("auto")) -> Response:
    try:
        content = await file.read(MAX_UPLOAD + 1)
        content = await run_in_threadpool(split_mapping_file, content, instrument, file.filename or 'mapping.txt')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attachment_response(content, "split_files.zip", "application/zip")


@app.post("/api/tools/merge")
async def merge_files_tool(files: List[UploadFile] = File(...)) -> Response:
    try:
        payload = [(file.filename or f"spectrum_{idx + 1}.txt", await file.read()) for idx, file in enumerate(files)]
        content = merge_spectrum_files(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attachment_response(content, "merged_mapping.txt")


@app.post('/api/tools/standardize')
async def standardize_instrument_file(file: UploadFile = File(...)) -> Response:
    from spectral_formats import standard_spectra_archive
    content = await file.read(4 * 1024 * 1024 + 1)
    if not content or len(content) > 4 * 1024 * 1024:
        raise HTTPException(400, '文件为空或超过 4 MB。')
    try:
        converted = await run_in_threadpool(standard_spectra_archive, content, file.filename or 'spectrum.txt')
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return attachment_response(converted, 'standard_spectra.zip', 'application/zip')


@app.post("/api/tools/convert")
async def convert_mapping_tool(file: UploadFile = File(...), conversion: str = Form("horiba_to_nanophoton")) -> Response:
    try:
        content = await file.read()
        stem = Path(file.filename or "mapping.txt").stem
        if conversion == "horiba_to_nanophoton":
            converted = horiba_to_nanophoton(content)
            filename = f"{stem}_to_Nanophoton.txt"
        elif conversion == "nanophoton_to_horiba":
            converted = nanophoton_to_horiba(content)
            filename = f"{stem}_to_Horiba.txt"
        else:
            raise ValueError("Unsupported conversion.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return attachment_response(converted, filename)


@app.post("/api/process")
def process_spectrum(payload: SpectrumPayload, current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)) -> Dict[str, Any]:
    wave = clean_floats(payload.wavenumber)
    intensity = clean_floats(payload.intensity)
    out_wave, out_intensity, baseline, history = apply_pipeline(wave, intensity, payload.steps)
    analysis_run = None
    result_payload = {
        "wavenumber": out_wave.tolist(),
        "intensity": out_intensity.tolist(),
        "baseline": baseline.tolist() if baseline is not None else None,
        "summary": {
            "wavenumber": summarize_array(out_wave),
            "intensity": summarize_array(out_intensity),
            "has_baseline": baseline is not None,
        },
    }
    if payload.save_history and current_user is not None:
        source_name = payload.source_name or "spectrum"
        input_payload = {
            "wavenumber": wave.tolist(),
            "intensity": intensity.tolist(),
            "summary": {
                "wavenumber": summarize_array(wave),
                "intensity": summarize_array(intensity),
            },
        }
        analysis_run = save_analysis_run(
            current_user=current_user,
            analysis_type="spectrum",
            source_name=source_name,
            steps=payload.steps,
            input_payload=input_payload,
            result_payload=result_payload,
            history=history,
            title=payload.title,
            project_id=payload.project_id,
            source_dataset_id=payload.source_dataset_id,
            result_filename=f"processed_{source_name}.txt",
        )
    return {
        "code": 0,
        "msg": "Pipeline completed",
        "data": {
            "wavenumber": out_wave.tolist(),
            "intensity": out_intensity.tolist(),
            "baseline": baseline.tolist() if baseline is not None else None,
            "history": history,
            "analysis_run": analysis_run,
        },
    }


@app.post("/api/process-hyperspectral")
def process_cube(payload: CubePayload, current_user: Optional[Dict[str, Any]] = Depends(get_optional_user), stream: bool = False):
    if stream:
        if current_user is None:
            raise HTTPException(401, "请先登录。")
        return stream_work(lambda emit: _process_cube(payload, current_user), "高光谱处理失败，请重新提交。")
    return _process_cube(payload, current_user)


def _process_cube(payload, current_user):
    if payload.dataset_id:
        if payload.dataset_id not in DATASETS:
            raise HTTPException(status_code=404, detail="Dataset not found or expired.")
        source = cached_dataset(payload.dataset_id, current_user)
        wave = source["wavenumber"]
        source_data = source["data"]
        mode = source["mode"]
        filename = source["filename"]
        original_shape = source_data.shape
        spectra = source_data.reshape(-1, source_data.shape[-1]) if source_data.ndim == 3 else source_data
    else:
        wave = clean_floats(payload.wavenumber)
        spectra = clean_floats(payload.spectra)
        source_data = spectra
        mode = payload.mode
        filename = "processed_mapping.txt"
        original_shape = tuple(payload.shape or list(spectra.shape))
        if mode == 'imaging' and len(original_shape) == 3:
            if original_shape[-1] != len(wave) or int(np.prod(original_shape)) != source_data.size:
                raise HTTPException(400, '成像尺寸与光谱数组不一致。')
            source_data = source_data.reshape(original_shape)
        if spectra.ndim > 2:
            spectra = spectra.reshape(-1, spectra.shape[-1])
    spatial_shape = original_shape[:2] if mode == 'imaging' and len(original_shape) == 3 else None
    try:
        out_wave, out_spectra, baseline, history = apply_pipeline(wave, spectra, payload.steps, spatial_shape, hyperspectral=True)
    except TSVDWorkLimitError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    mean = out_spectra.mean(axis=0)
    if mode == "imaging" and len(original_shape) >= 2:
        processed_cube = out_spectra.reshape(int(original_shape[0]), int(original_shape[1]), out_spectra.shape[-1])
    else:
        processed_cube = out_spectra
    processed_id = register_dataset(out_wave, processed_cube, mode, "processed_" + filename, current_user, payload.project_id or (source.get('project_id') if payload.dataset_id else None))
    DATASETS[processed_id]['history'] = history
    tshi = next((item['details'] for item in reversed(history) if item.get('method') == 'tshi'), None)
    requested_preview = payload.preview_wavenumber
    if requested_preview is not None and not (out_wave.min() <= requested_preview <= out_wave.max()):
        requested_preview = None
    preview = mapping_preview(out_wave, processed_cube, tshi['center_wavenumber'] if tshi else requested_preview)
    response = {
        "processed_dataset_id": processed_id,
        "wavenumber": out_wave.tolist(),
        **preview,
        "mean_spectrum": rounded_list(mean),
        "shape": list(processed_cube.shape),
        "history": history,
    }
    if baseline is not None:
        response["baseline_mean"] = rounded_list(baseline.mean(axis=0))
    if payload.save_history and current_user is not None:
        source_name = payload.source_name or filename or "hyperspectral"
        source_id = payload.dataset_id
        if DATASETS.get(source_id, {}).get('owner_id') != current_user['id']:
            source_id = register_dataset(wave, source_data, mode, filename, current_user, payload.project_id)
        input_payload = {
            "dataset_id": source_id,
            "source_name": source_name,
            "mode": mode,
            "shape": list(original_shape),
            "wavenumber": wave.tolist(),
            "mean_spectrum": rounded_list(spectra.reshape(-1, len(wave)).mean(axis=0)),
            "summary": {
                "wavenumber": summarize_array(wave),
                "shape": list(original_shape),
                "mode": mode,
            },
        }
        result_payload = {
            "wavenumber": out_wave.tolist(),
            "mean_spectrum": rounded_list(mean),
            **preview,
            "shape": list(processed_cube.shape),
            "processed_dataset_id": processed_id,
            "baseline_mean": response.get("baseline_mean"),
            "summary": {
                "wavenumber": summarize_array(out_wave),
                "shape": list(processed_cube.shape),
                "mode": mode,
                "has_baseline": baseline is not None,
            },
        }
        response["analysis_run"] = save_analysis_run(
            current_user=current_user,
            analysis_type="hyperspectral",
            source_name=source_name,
            steps=payload.steps,
            input_payload=input_payload,
            result_payload=result_payload,
            history=history,
            title=payload.title,
            project_id=payload.project_id,
            source_dataset_id=payload.source_dataset_id,
            result_dataset_id=None,
            result_filename=f"processed_{source_name}",
        )
    return {"code": 0, "msg": "Mapping pipeline completed", "data": response}


@app.get("/api/hyperspectral-slice/{dataset_id}")
def get_hyperspectral_slice(dataset_id: str, wavenumber_value: Optional[float] = None, current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)) -> Dict[str, Any]:
    if dataset_id not in DATASETS:
        raise HTTPException(status_code=404, detail="Dataset not found or expired.")
    dataset = cached_dataset(dataset_id, current_user)
    if wavenumber_value is not None and not np.isfinite(wavenumber_value):
        raise HTTPException(status_code=422, detail="Preview wavenumber must be finite.")
    preview = mapping_preview(dataset["wavenumber"], dataset["data"], wavenumber_value)
    return {
        "code": 0,
        "msg": "Slice loaded",
        "data": {
            **preview,
            "wavenumber": preview["preview_wavenumber"],
            "wavenumber_index": preview["preview_wavenumber_index"],
        },
    }


@app.get("/api/hyperspectral-pixel/{dataset_id}")
def get_hyperspectral_pixel(dataset_id: str, x: int = 0, y: int = 0, current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)) -> Dict[str, Any]:
    if dataset_id not in DATASETS:
        raise HTTPException(status_code=404, detail="Dataset not found or expired.")
    dataset = cached_dataset(dataset_id, current_user)
    data = dataset["data"]
    if data.ndim != 3:
        raise HTTPException(status_code=400, detail="Pixel spectra are only available for imaging datasets.")
    row = int(max(0, min(y, data.shape[0] - 1)))
    col = int(max(0, min(x, data.shape[1] - 1)))
    return {
        "code": 0,
        "msg": "Pixel spectrum loaded",
        "data": {
            "x": col,
            "y": row,
            "wavenumber": dataset["wavenumber"].tolist(),
            "intensity": rounded_list(data[row, col]),
        },
    }


@app.get("/api/hyperspectral-spectrum/{dataset_id}")
def get_hyperspectral_spectrum(dataset_id: str, index: int = 0, current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)) -> Dict[str, Any]:
    if dataset_id not in DATASETS:
        raise HTTPException(status_code=404, detail="Dataset not found or expired.")
    dataset = cached_dataset(dataset_id, current_user)
    data = dataset["data"]
    if data.ndim != 2:
        raise HTTPException(status_code=400, detail="Indexed spectra are only available for time-series datasets.")
    row = int(max(0, min(index, data.shape[0] - 1)))
    return {
        "code": 0,
        "msg": "Time-series spectrum loaded",
        "data": {
            "index": row,
            "wavenumber": dataset["wavenumber"].tolist(),
            "intensity": rounded_list(data[row]),
        },
    }


@app.post("/api/download")
def download(payload: DownloadPayload, current_user: Optional[Dict[str, Any]] = Depends(get_optional_user)) -> Response:
    filename = payload.filename or "processed.txt"
    if payload.format not in {'txt', 'mat'}:
        raise HTTPException(status_code=400, detail="不支持的下载格式。")
    if payload.format == 'mat':
        dataset = cached_dataset(payload.dataset_id, current_user)
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found or expired.")
        if dataset['data'].ndim != 3:
            raise HTTPException(status_code=400, detail="MAT 导出仅支持成像数据。")
        return attachment_response(mat_result(dataset['wavenumber'], dataset['data'], dataset.get('history', [])), str(Path(filename).with_suffix('.mat')), 'application/x-matlab-data')
    if payload.dataset_id is not None:
        if payload.dataset_id not in DATASETS:
            raise HTTPException(status_code=404, detail="Dataset not found or expired.")
        dataset = cached_dataset(payload.dataset_id, current_user)
        wave = dataset["wavenumber"]
        data = dataset["data"]
        spectra = data.reshape(-1, data.shape[-1]) if data.ndim == 3 else data
        matrix = np.vstack([wave, spectra]).T
        content = pd.DataFrame(matrix).to_csv(sep="\t", index=False, header=False, float_format="%.8g")
    elif payload.spectra is not None:
        spectra = clean_floats(payload.spectra)
        wave = clean_floats(payload.wavenumber)
        matrix = np.vstack([wave, spectra]).T
        content = pd.DataFrame(matrix).to_csv(sep="\t", index=False, header=False, float_format="%.8g")
    else:
        wave = clean_floats(payload.wavenumber)
        intensity = clean_floats(payload.intensity)
        data = {"wavenumber": wave, "intensity": intensity}
        if payload.baseline is not None:
            data["baseline"] = clean_floats(payload.baseline)
        content = pd.DataFrame(data).to_csv(sep="\t", index=False, header=False, float_format="%.8g")
    quoted = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{quoted}"'},
    )


from project_collaboration import install_collaboration

install_collaboration(app, globals())
from history_resources import install_history_resources
install_history_resources(app, globals())

from ai_workflow import install_ai_workflow

install_ai_workflow(app, globals())

from structure_generation import install_structure_generation

install_structure_generation(app, globals())

from library_matching import install_library_matching

install_library_matching(app, globals())

from ssnet import install_ssnet

install_ssnet(app, globals())

from peak_fitting import install_peak_fitting
install_peak_fitting(app, globals())

from assistant_api import install_assistant

install_assistant(app, globals())

from qa_assistant import install_qa_assistant
install_qa_assistant(app, globals())

from feedback import install_feedback
install_feedback(app, globals())

from analysis_records import install_analysis_records
install_analysis_records(app, globals())
from spectrum_exports import install_spectrum_exports
install_spectrum_exports(app, globals())

from qa_actions import install_qa_actions
install_qa_actions(app, globals())


if __name__ == "__main__":
    import asyncio
    import uvicorn

    if not hasattr(asyncio, "current_task"):
        asyncio.current_task = asyncio.Task.current_task

    config = uvicorn.Config("app:app", host="127.0.0.1", port=5000, reload=False)
    server = uvicorn.Server(config)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(server.serve())
