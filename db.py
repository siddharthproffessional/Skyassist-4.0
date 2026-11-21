"""Shared SQLite helpers.

* One connection per call so Streamlit sessions and the approval event-loop thread never share one.
* The database path comes from SKYASSIST_DB (tests point it at a temp file).
* Stored timestamps are UTC ISO-8601; the UI converts them to the airport's local time.
"""
import contextlib
import os
import sqlite3
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

# On Vercel serverless the project root is read-only; /tmp is writable and survives within a warm instance.
# SKYASSIST_DB overrides everything (used by tests and local runs).
def _default_db_path() -> str:
    explicit = os.getenv("SKYASSIST_DB")
    if explicit:
        return explicit
    # Detect Vercel: VERCEL env var is "1" on all Vercel runtimes
    if os.getenv("VERCEL") == "1":
        return "/tmp/skyassist.sqlite"
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "airport_terminal_journey.sqlite")

DB_PATH = _default_db_path()
AIRPORT_TZ = os.getenv("AIRPORT_TZ", "Asia/Dubai")


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))
BACKEND = "postgres" if IS_PG else "sqlite"
BACKEND_ERROR = ""
if IS_PG:
    import db_pg
    try:
        db_pg.ping(DATABASE_URL)
    except Exception as _e:  # never take the whole app down because the shared database is unreachable
        IS_PG = False
        BACKEND = "sqlite-fallback"
        BACKEND_ERROR = str(_e).splitlines()[0][:300]
        print(f"[skyassist] DATABASE_URL unusable, falling back to SQLite: {BACKEND_ERROR}", flush=True)
        print(f"[skyassist] DATABASE_URL shape (password not shown): {db_pg.describe_dsn(DATABASE_URL)}", flush=True)
if IS_PG:
    IntegrityError = (sqlite3.IntegrityError, db_pg.IntegrityError)
    DatabaseError = (sqlite3.DatabaseError, db_pg.psycopg.Error)
else:
    IntegrityError = sqlite3.IntegrityError
    DatabaseError = sqlite3.DatabaseError


def connect():
    if IS_PG:
        return db_pg.connect(DATABASE_URL)
    con = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=15000")
    return con


@contextlib.contextmanager
def tx():
    """Explicit write transaction (BEGIN IMMEDIATE) for atomic state transitions."""
    con = connect()
    con.isolation_level = None
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def startup_lock():
    if IS_PG:
        return db_pg.startup_lock(DATABASE_URL)
    return contextlib.nullcontext()


def database_exists() -> bool:
    if IS_PG:
        return db_pg.has_schema(DATABASE_URL)
    return os.path.exists(DB_PATH)


def mark_ready():
    """Postgres: record that build + seed finished, so other instances never start on a half-built schema."""
    if IS_PG:
        db_pg.mark_ready(DATABASE_URL)


def drop_database():
    if IS_PG:
        db_pg.reset_schema(DATABASE_URL)
        return
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(DB_PATH + ext):
            os.remove(DB_PATH + ext)


def query(sql, args=()):
    con = connect()
    try:
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def query_one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def local_time(iso_utc: str, fmt_: str = "%H:%M") -> str:
    """UTC ISO string -> airport local time for display."""
    if not iso_utc:
        return "—"
    dt = datetime.fromisoformat(iso_utc)
    if ZoneInfo:
        try:
            dt = dt.astimezone(ZoneInfo(AIRPORT_TZ))
        except Exception:
            pass
    return dt.strftime(fmt_)


def seconds_since(iso_utc: str) -> int:
    if not iso_utc:
        return 0
    return int((datetime.now(timezone.utc) - datetime.fromisoformat(iso_utc)).total_seconds())


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt(minutes: int) -> str:
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"
