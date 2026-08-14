"""
Writes live PR report data into SQL Server (192.168.66.33) as a
timestamped history log. Every fetch adds new rows -- nothing is
overwritten -- so the table becomes a full history over time.

Database, table, and columns are all created automatically. Columns
are detected dynamically from whatever keys are present in the JSON,
so a new field showing up in the source report doesn't break anything.
"""

import re
import time
import threading
import os
import sys
from datetime import datetime

import requests
import pyodbc

# Ensure this script's own folder is importable (needed for embeddable/
# isolated Python distributions, which don't add the script dir automatically).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db_config as cfg

_lock = threading.Lock()
_known_columns = set()


def _sanitize_column_name(raw_name):
    name = re.sub(r"[^0-9A-Za-z_]", "_", str(raw_name)).strip("_")
    if not name:
        name = "col"
    if name[0].isdigit():
        name = "c_" + name
    return name[:120]


def _master_connection_string():
    return (
        f"DRIVER={{{cfg.ODBC_DRIVER}}};"
        f"SERVER={cfg.DB_SERVER};"
        f"DATABASE=master;"
        f"Trusted_Connection=yes;"
        f"TrustServerCertificate=yes;"
    )


def _db_connection_string():
    return (
        f"DRIVER={{{cfg.ODBC_DRIVER}}};"
        f"SERVER={cfg.DB_SERVER};"
        f"DATABASE={cfg.DB_NAME};"
        f"Trusted_Connection=yes;"
        f"TrustServerCertificate=yes;"
    )


def ensure_database_exists():
    conn = pyodbc.connect(_master_connection_string(), autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = ?) "
            "EXEC('CREATE DATABASE [' + ? + ']')",
            cfg.DB_NAME, cfg.DB_NAME,
        )
    finally:
        conn.close()


def ensure_table_exists(conn):
    cur = conn.cursor()
    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = ?) "
        "EXEC('CREATE TABLE [dbo].[' + ? + '] ("
        "id BIGINT IDENTITY(1,1) PRIMARY KEY, "
        "fetched_at DATETIME2 NOT NULL DEFAULT SYSDATETIME())')",
        cfg.TABLE_NAME, cfg.TABLE_NAME,
    )
    conn.commit()

    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_fetched_at') "
        f"CREATE INDEX ix_fetched_at ON [dbo].[{cfg.TABLE_NAME}] (fetched_at)"
    )
    conn.commit()

    cur.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?",
        cfg.TABLE_NAME,
    )
    global _known_columns
    _known_columns = {row[0] for row in cur.fetchall()}


def ensure_columns(conn, column_names):
    global _known_columns
    missing = [c for c in column_names if c not in _known_columns]
    if not missing:
        return
    cur = conn.cursor()
    for col in missing:
        cur.execute(
            f"ALTER TABLE [dbo].[{cfg.TABLE_NAME}] ADD [{col}] NVARCHAR(1000) NULL"
        )
    conn.commit()
    _known_columns.update(missing)


def normalize_rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "rows", "result", "results", "d"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    return []


def fetch_and_store():
    resp = requests.get(cfg.SOURCE_URL, timeout=15)
    resp.raise_for_status()
    rows = normalize_rows(resp.json())
    if not rows:
        return 0

    sanitized_rows = []
    all_columns = set()
    for row in rows:
        sanitized = {_sanitize_column_name(k): v for k, v in row.items()}
        sanitized_rows.append(sanitized)
        all_columns.update(sanitized.keys())

    fetched_at = datetime.now()

    with _lock:
        conn = pyodbc.connect(_db_connection_string(), autocommit=False)
        try:
            ensure_columns(conn, all_columns)
            cur = conn.cursor()
            for row in sanitized_rows:
                cols = ["fetched_at"] + list(row.keys())
                placeholders = ", ".join(["?"] * len(cols))
                col_list = ", ".join(f"[{c}]" for c in cols)
                values = [fetched_at] + [
                    None if v is None else str(v) for v in row.values()
                ]
                cur.execute(
                    f"INSERT INTO [dbo].[{cfg.TABLE_NAME}] ({col_list}) VALUES ({placeholders})",
                    values,
                )
            conn.commit()
        finally:
            conn.close()

    return len(sanitized_rows)


def init():
    """Call once at startup: creates DB/table if missing. Safe to call repeatedly."""
    ensure_database_exists()
    conn = pyodbc.connect(_db_connection_string(), autocommit=False)
    try:
        ensure_table_exists(conn)
    finally:
        conn.close()


def run_forever(interval_seconds=None):
    interval = interval_seconds or cfg.WRITE_INTERVAL_SECONDS
    init()
    print(f"[db_writer] Writing to {cfg.DB_SERVER}/{cfg.DB_NAME}.dbo.{cfg.TABLE_NAME} "
          f"every {interval}s")
    while True:
        try:
            n = fetch_and_store()
            print(f"[db_writer] {datetime.now().strftime('%H:%M:%S')} wrote {n} rows")
        except Exception as e:
            print(f"[db_writer] ERROR: {e}")
        time.sleep(interval)


def start_background_thread():
    t = threading.Thread(target=run_forever, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    run_forever()
