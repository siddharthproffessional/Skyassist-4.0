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

DB_PATH = os.getenv("SKYASSIST_DB") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                    "airport_terminal_journey.sqlite")
AIRPORT_TZ = os.getenv("AIRPORT_TZ", "Asia/Dubai")


def connect():
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
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
