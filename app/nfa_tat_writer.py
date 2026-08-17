"""
Writes PR/NFA TAT report data into SQL Server as a timestamped history
log, same pattern as db_writer.py but for the date-ranged
SapPrNFATatReport.php source.

Every cycle, pulls a rolling window (today - NFATAT_ROLLING_DAYS to
today) and inserts a fresh timestamped batch. Nothing is overwritten.
"""

import re
import time
import threading
import os
import sys
from datetime import datetime, timedelta

import requests
import pyodbc

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


def _db_connection_string():
    return (
        f"DRIVER={{{cfg.ODBC_DRIVER}}};"
        f"SERVER={cfg.DB_SERVER};"
        f"DATABASE={cfg.DB_NAME};"
        f"Trusted_Connection=yes;"
        f"TrustServerCertificate=yes;"
    )


def _master_connection_string():
    return (
        f"DRIVER={{{cfg.ODBC_DRIVER}}};"
        f"SERVER={cfg.DB_SERVER};"
        f"DATABASE=master;"
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
        cfg.NFATAT_TABLE_NAME, cfg.NFATAT_TABLE_NAME,
    )
    conn.commit()

    cur.execute(
        "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_nfatat_fetched_at') "
        f"CREATE INDEX ix_nfatat_fetched_at ON [dbo].[{cfg.NFATAT_TABLE_NAME}] (fetched_at)"
    )
    conn.commit()

    cur.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?",
        cfg.NFATAT_TABLE_NAME,
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
            f"ALTER TABLE [dbo].[{cfg.NFATAT_TABLE_NAME}] ADD [{col}] NVARCHAR(MAX) NULL"
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


def _current_window():
    end = datetime.now().date()
    start = end - timedelta(days=cfg.NFATAT_ROLLING_DAYS)
    return start.isoformat(), end.isoformat()


def fetch_and_store():
    startdate, enddate = _current_window()
    url = f"{cfg.NFATAT_SOURCE_URL_BASE}?startdate={startdate}&enddate={enddate}"

    resp = requests.get(url, timeout=30)
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
                    f"INSERT INTO [dbo].[{cfg.NFATAT_TABLE_NAME}] ({col_list}) VALUES ({placeholders})",
                    values,
                )
            conn.commit()
        finally:
            conn.close()

    return len(sanitized_rows)


def init():
    ensure_database_exists()
    conn = pyodbc.connect(_db_connection_string(), autocommit=False)
    try:
        ensure_table_exists(conn)
    finally:
        conn.close()


def run_forever(interval_seconds=None):
    interval = interval_seconds or cfg.NFATAT_WRITE_INTERVAL_SECONDS
    init()
    print(f"[nfa_tat_writer] Writing to {cfg.DB_SERVER}/{cfg.DB_NAME}.dbo.{cfg.NFATAT_TABLE_NAME} "
          f"every {interval}s (rolling {cfg.NFATAT_ROLLING_DAYS}-day window)")
    while True:
        try:
            n = fetch_and_store()
            startdate, enddate = _current_window()
            print(f"[nfa_tat_writer] {datetime.now().strftime('%H:%M:%S')} "
                  f"wrote {n} rows ({startdate} to {enddate})")
        except Exception as e:
            print(f"[nfa_tat_writer] ERROR: {e}")
        time.sleep(interval)


def start_background_thread():
    t = threading.Thread(target=run_forever, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    run_forever()
