"""Postgres backend for SkyAssist (used when DATABASE_URL is set, e.g. Supabase).

The application code is written against sqlite3. This module gives it a connection object with the same surface
(execute / executemany / executescript / cursor / commit / rollback / close, rows indexable by name and position,
cursor.lastrowid, IntegrityError) and translates the SQLite dialect the code uses into Postgres at runtime:

* ``?`` placeholders -> ``%s`` (string literals are left alone, literal ``%`` is escaped)
* ``INSERT OR IGNORE`` -> ``ON CONFLICT DO NOTHING``; ``INSERT OR REPLACE`` -> upsert on the primary key
* ``strftime('%s','now')`` -> epoch seconds; ``GROUP_CONCAT`` -> ``string_agg``; ``rowid`` -> ``ctid``
* ``PRAGMA table_info(t)`` -> information_schema; other PRAGMAs are no-ops
* DDL: ``INTEGER PRIMARY KEY [AUTOINCREMENT]`` -> identity column, ``REAL`` -> double precision,
  SQLite ``RAISE(ABORT, …)`` triggers -> PL/pgSQL trigger functions (same append-only / immutability guarantees)
* ``BEGIN IMMEDIATE`` -> ``BEGIN`` + a transaction-scoped advisory lock, i.e. the same single-writer semantics.

Parameters are bound client-side and numbers are sent as untyped literals, so SQLite's loose typing
(e.g. comparing a TEXT column with an int) keeps working.
"""
import contextlib
import re
import threading

import psycopg
from psycopg import ClientCursor
from psycopg.adapt import Dumper

IntegrityError = psycopg.errors.IntegrityError
WRITE_LOCK_KEY = 4242001


# ------------------------------------------------------------------ untyped numeric literals
class _UnknownNumDumper(Dumper):
    oid = 0

    def dump(self, obj):
        if isinstance(obj, bool):
            obj = int(obj)
        return str(obj).encode()

    def quote(self, obj):
        return b"'" + self.dump(obj) + b"'"


def _configure(conn):
    for t in (int, float, bool):
        conn.adapters.register_dumper(t, _UnknownNumDumper)


# ------------------------------------------------------------------ rows
class Row(dict):
    """dict that is also indexable by position, like sqlite3.Row."""

    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return dict.__getitem__(self, k)

    def keys(self):  # sqlite3.Row.keys() returns a list
        return list(dict.keys(self))


# ------------------------------------------------------------------ SQL translation
_STR = re.compile(r"'(?:[^']|'')*'")


def _outside_literals(sql, fn):
    out, pos = [], 0
    for m in _STR.finditer(sql):
        out.append(fn(sql[pos:m.start()]))
        out.append(m.group(0).replace("%", "%%"))
        pos = m.end()
    out.append(fn(sql[pos:]))
    return "".join(out)


_pk_cache = {}
_cols_cache = {}
_cache_lock = threading.Lock()


def _table_pk(raw, table):
    with _cache_lock:
        if table in _pk_cache:
            return _pk_cache[table]
    rows = raw.execute(
        "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum = ANY(i.indkey) "
        "WHERE i.indrelid = to_regclass(%s) AND i.indisprimary ORDER BY array_position(i.indkey, a.attnum)",
        (table,)).fetchall()
    pk = [r[0] for r in rows]
    if not pk:  # no primary key: use the first unique index
        rows = raw.execute(
            "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum = ANY(i.indkey)"
            " WHERE i.indrelid = to_regclass(%s) AND i.indisunique ORDER BY i.indexrelid, "
            "array_position(i.indkey, a.attnum)", (table,)).fetchall()
        pk = [r[0] for r in rows[:1]] if rows else []
    with _cache_lock:
        _pk_cache[table] = pk
    return pk


def _table_cols(raw, table):
    with _cache_lock:
        if table in _cols_cache:
            return _cols_cache[table]
    cols = [r[0] for r in raw.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=%s "
        "ORDER BY ordinal_position", (table,)).fetchall()]
    with _cache_lock:
        _cols_cache[table] = cols
    return cols


def clear_caches():
    with _cache_lock:
        _pk_cache.clear()
        _cols_cache.clear()


_INS_OR = re.compile(r"^\s*INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO\s+([A-Za-z_][\w]*)\s*(\(([^)]*)\))?", re.I | re.S)


def _append_clause(sql, clause):
    body = sql.rstrip().rstrip(";")
    m = re.search(r"\sRETURNING\s", body, re.I)
    if m:
        return body[:m.start()] + " " + clause + body[m.start():]
    return body + " " + clause


def translate(sql, raw=None, named=False):
    m = _INS_OR.match(sql)
    conflict = None
    if m:
        mode, table, cols = m.group(1).upper(), m.group(2), m.group(4)
        sql = re.sub(r"^\s*INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO", "INSERT INTO", sql, count=1, flags=re.I)
        if mode == "IGNORE":
            conflict = "ON CONFLICT DO NOTHING"
        else:
            collist = [c.strip() for c in cols.split(",")] if cols else _table_cols(raw, table)
            pk = _table_pk(raw, table)
            if not pk:
                conflict = "ON CONFLICT DO NOTHING"
            else:
                upd = [c for c in collist if c not in pk]
                sets = ", ".join(f"{c}=EXCLUDED.{c}" for c in upd)
                if sets:
                    # SQLite REPLACE never fires UPDATE triggers; only update rows whose values really change
                    lhs = ", ".join(f"{table}.{c}" for c in upd)
                    rhs = ", ".join(f"EXCLUDED.{c}" for c in upd)
                    conflict = (f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {sets} "
                                f"WHERE ({lhs}{',' if len(upd) == 1 else ''}) IS DISTINCT FROM ({rhs}{',' if len(upd) == 1 else ''})")
                else:
                    conflict = f"ON CONFLICT ({', '.join(pk)}) DO NOTHING"

    sql = re.sub(r"strftime\('%Y-%m-%dT%H:%M:%S\+00:00'\s*,\s*(\w+)\s*,\s*'unixepoch'\)",
                 r"""to_char(to_timestamp(\1) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"')""", sql)

    def code(s):
        s = s.replace("%", "%%").replace("?", "%s")
        if named:
            s = re.sub(r"(?<![:\w]):([A-Za-z_]\w*)", r"%(\1)s", s)
        s = re.sub(r"\bGROUP_CONCAT\s*\(\s*([^,()]+?)\s*\)", r"string_agg((\1)::text, ',')", s, flags=re.I)
        s = re.sub(r"\browid\b", "ctid", s, flags=re.I)
        s = re.sub(r"\bsqlite_master\b", "(SELECT 'table'::text AS type, table_name::text AS name, "
                   "table_name::text AS tbl_name FROM information_schema.tables "
                   "WHERE table_schema=current_schema()) AS sqlite_master", s)
        return s

    sql = _outside_literals(sql, code)
    sql = re.sub(r"strftime\('%%s'\s*,\s*'now'\)", "extract(epoch from now())", sql, flags=re.I)
    if conflict:
        sql = _append_clause(sql, conflict)
    return sql


# ------------------------------------------------------------------ DDL translation
_TRIGGER = re.compile(
    r"CREATE\s+TRIGGER\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+(BEFORE\s+(?:UPDATE|DELETE)(?:\s+OF\s+[\w\s,]+?)?)\s+ON\s+(\w+)"
    r"\s*(?:WHEN\s+(.+?))?\s*BEGIN\s+SELECT\s+RAISE\s*\(\s*ABORT\s*,\s*'([^']*)'\s*\)\s*;\s*END", re.I | re.S)


def _trigger_sql(m):
    name, timing, table, when, msg = m.groups()
    timing = re.sub(r"\s+", " ", timing.strip())
    when_sql = f" WHEN ({when.strip().replace('!=', 'IS DISTINCT FROM')})" if when else ""
    ret = "OLD"
    return (f"CREATE OR REPLACE FUNCTION {name}_fn() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN "
            f"RAISE EXCEPTION '{msg}' USING ERRCODE = 'integrity_constraint_violation'; RETURN {ret}; END $f$;\n"
            f"DROP TRIGGER IF EXISTS {name} ON {table};\n"
            f"CREATE TRIGGER {name} {timing} ON {table} FOR EACH ROW{when_sql} EXECUTE FUNCTION {name}_fn()")


def translate_ddl(script):
    s = _TRIGGER.sub(_trigger_sql, script)
    s = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
               s, flags=re.I)
    s = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\b(?!\s*\()", "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY",
               s, flags=re.I)
    s = re.sub(r"\bREAL\b", "DOUBLE PRECISION", s)
    s = re.sub(r"\bINTEGER\b", "BIGINT", s)
    s = re.sub(r"DEFAULT\s*\(\s*strftime\('%s'\s*,\s*'now'\)\s*\)", "DEFAULT (extract(epoch from now()))", s, flags=re.I)
    return s


def _split(script):
    """Split on ; outside string literals and $f$ bodies."""
    parts, buf, i, n = [], [], 0, len(script)
    in_str = in_dollar = False
    while i < n:
        ch = script[i]
        if not in_str and script.startswith("$f$", i):
            in_dollar = not in_dollar
            buf.append("$f$")
            i += 3
            continue
        if ch == "'" and not in_dollar:
            in_str = not in_str
        if ch == ";" and not in_str and not in_dollar:
            stmt = "".join(buf).strip()
            if stmt:
                parts.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    stmt = "".join(buf).strip()
    if stmt:
        parts.append(stmt)
    return parts


def _clean(v):
    """Postgres TEXT cannot hold NUL; keep it visible (as the 4 characters \\x00) instead of failing the write."""
    return v.replace("\x00", "\\x00") if isinstance(v, str) and "\x00" in v else v


# ------------------------------------------------------------------ connection wrapper
class Cursor:
    def __init__(self, conn):
        self._conn = conn
        self._cur = conn._raw.cursor()
        self.rowcount = -1
        self._buffer = None

    def _rows(self):
        if self._cur.description is None:
            return []
        names = [d.name for d in self._cur.description]
        return [Row(zip(names, r)) for r in self._cur.fetchall()]

    def execute(self, sql, args=()):
        self._conn._ensure_tx()
        stripped = sql.strip()
        up = stripped.upper()
        if up.startswith("PRAGMA"):
            m = re.match(r"PRAGMA\s+table_info\((\w+)\)", stripped, re.I)
            self._pending = []
            if m:
                cols = self._conn._raw.execute(
                    "SELECT ordinal_position-1, column_name, data_type, CASE WHEN is_nullable='NO' THEN 1 ELSE 0 END, "
                    "column_default, 0 FROM information_schema.columns WHERE table_schema=current_schema() AND "
                    "table_name=%s ORDER BY ordinal_position", (m.group(1),)).fetchall()
                names = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
                self._pending = [Row(zip(names, c)) for c in cols]
            self._buffer = self._pending
            return self
        if up.startswith(("BEGIN", "COMMIT", "ROLLBACK", "END")):
            self._conn._control(up)
            self._buffer = []
            return self
        if re.match(r"(CREATE|ALTER|DROP)\s", up):
            for stmt in _split(translate_ddl(stripped)):
                self._cur.execute(stmt)
            clear_caches()
            self._buffer = []
            return self
        named = isinstance(args, dict)
        q = translate(stripped, self._conn._raw, named)
        args = dict(args) if named else (tuple(args) if args is not None else ())
        args = ({k: _clean(v) for k, v in args.items()} if named else tuple(_clean(v) for v in args))
        if self._conn._in_tx:  # SQLite fails only the statement; Postgres would abort the whole transaction
            self._cur.execute("SAVEPOINT _st")
            try:
                self._cur.execute(q, args)
            except psycopg.Error:
                self._cur.execute("ROLLBACK TO SAVEPOINT _st")
                raise
            rows = self._rows()
            self.rowcount = self._cur.rowcount if self._cur.description is None else len(rows)
            self._cur.execute("RELEASE SAVEPOINT _st")
            self._buffer = rows
        else:
            self._cur.execute(q, args)
            self.rowcount = self._cur.rowcount
            self._buffer = None
        self._was_insert = up.startswith("INSERT")
        return self

    @property
    def lastrowid(self):
        return self._conn._lastval() if getattr(self, "_was_insert", False) else None

    @lastrowid.setter
    def lastrowid(self, v):
        pass

    def executemany(self, sql, seq):
        for a in seq:
            self.execute(sql, a)
        return self

    def fetchall(self):
        if self._buffer is not None:
            b, self._buffer = self._buffer, []
            return b
        return self._rows()

    def fetchone(self):
        if self._buffer is not None:
            return self._buffer.pop(0) if self._buffer else None
        if self._cur.description is None:
            return None
        r = self._cur.fetchone()
        if r is None:
            return None
        return Row(zip([d.name for d in self._cur.description], r))

    def __iter__(self):
        return iter(self.fetchall())


class Connection:
    def __init__(self, dsn):
        self._raw = psycopg.connect(dsn, autocommit=True, cursor_factory=ClientCursor, prepare_threshold=None)
        _configure(self._raw)
        self._in_tx = False
        self.isolation_level = ""  # "" = implicit transactions like sqlite3's default; None = autocommit

    # sqlite3 starts a transaction implicitly before writes unless isolation_level is None
    def _ensure_tx(self):
        if self.isolation_level is not None and not self._in_tx:
            self._raw.execute("BEGIN")
            self._in_tx = True

    def _control(self, up):
        if up.startswith("BEGIN"):
            if not self._in_tx:
                self._raw.execute("BEGIN")
                self._in_tx = True
            if "IMMEDIATE" in up or "EXCLUSIVE" in up:
                self._raw.execute("SELECT pg_advisory_xact_lock(%s)", (WRITE_LOCK_KEY,))
        elif up.startswith(("COMMIT", "END")):
            self.commit()
        elif up.startswith("ROLLBACK"):
            self.rollback()

    def _lastval(self):
        try:
            self._raw.execute("SAVEPOINT _lv")
            v = self._raw.execute("SELECT lastval()").fetchone()[0]
            self._raw.execute("RELEASE SAVEPOINT _lv")
            return v
        except psycopg.Error:
            self._raw.execute("ROLLBACK TO SAVEPOINT _lv") if self._in_tx else None
            return None

    def cursor(self):
        return Cursor(self)

    def execute(self, sql, args=()):
        return Cursor(self).execute(sql, args)

    def executemany(self, sql, seq):
        return Cursor(self).executemany(sql, seq)

    def executescript(self, script):
        self._ensure_tx()
        for stmt in _split(translate_ddl(script)):
            if stmt.upper().startswith("PRAGMA"):
                continue
            self._raw.execute(stmt)
        clear_caches()
        self.commit()

    def commit(self):
        if self._in_tx:
            self._raw.execute("COMMIT")
            self._in_tx = False

    def rollback(self):
        if self._in_tx:
            self._raw.execute("ROLLBACK")
            self._in_tx = False

    def close(self):
        try:
            self.rollback()
        finally:
            self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            self.commit()
        else:
            self.rollback()
        return False


def connect(dsn):
    return Connection(dsn)


COMPAT_SQL = """
CREATE OR REPLACE FUNCTION _sa_boolsum(bigint, boolean) RETURNS bigint LANGUAGE sql IMMUTABLE AS
  'SELECT $1 + CASE WHEN $2 THEN 1 ELSE 0 END';
DO $$ BEGIN
  CREATE AGGREGATE sum(boolean) (SFUNC = _sa_boolsum, STYPE = bigint, INITCOND = '0');
EXCEPTION WHEN duplicate_function THEN NULL; END $$;
"""


def reset_schema(dsn):
    c = psycopg.connect(dsn, autocommit=True)
    try:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE")
        c.execute("CREATE SCHEMA public")
        c.execute(COMPAT_SQL)
    finally:
        c.close()
    clear_caches()


@contextlib.contextmanager
def startup_lock(dsn, key=4242002):
    """Cross-instance lock so only one serverless instance builds/migrates the schema at a time."""
    c = psycopg.connect(dsn, autocommit=False, prepare_threshold=None)
    try:
        c.execute("SELECT pg_advisory_xact_lock(%s)", (key,))
        yield
    finally:
        try:
            c.rollback()
        finally:
            c.close()


def ping(dsn, timeout=6):
    c = psycopg.connect(dsn, autocommit=True, connect_timeout=timeout)
    try:
        c.execute("SELECT 1")
    finally:
        c.close()


def has_schema(dsn):
    c = psycopg.connect(dsn, autocommit=True)
    try:
        return c.execute("SELECT to_regclass('public._skyassist_ready') IS NOT NULL").fetchone()[0]
    finally:
        c.close()


def mark_ready(dsn):
    c = psycopg.connect(dsn, autocommit=True)
    try:
        c.execute("CREATE TABLE IF NOT EXISTS _skyassist_ready(done_at timestamptz DEFAULT now())")
    finally:
        c.close()
