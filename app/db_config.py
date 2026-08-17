"""
SQL Server connection config.

Uses Windows Authentication (trusted connection) -- no password stored
here. Works as long as the Windows account running this script has
access to the SQL Server instance below (server 33).
"""

DB_SERVER = "192.168.66.33"
DB_NAME = "QMS_PR_Report"

# Check "ODBC Data Sources (64-bit)" on Windows -> Drivers tab if this
# doesn't match what's actually installed on server 34.
ODBC_DRIVER = "ODBC Driver 17 for SQL Server"

SOURCE_URL = "https://smartworlddevelopersonline.com/SapPrReport.php"
TABLE_NAME = "PRReportHistory"

# Used only by app.py's continuous background writer.
WRITE_INTERVAL_SECONDS = 45

# --- PR/NFA TAT report (SapPrNFATatReport.php) ---
# Takes a date range (?startdate=YYYY-MM-DD&enddate=YYYY-MM-DD).
# The writer below re-pulls a rolling window on every cycle.
NFATAT_SOURCE_URL_BASE = "https://smartworlddevelopersonline.com/SapPrNFATatReport.php"
NFATAT_TABLE_NAME = "PRNFATatReportHistory"
NFATAT_ROLLING_DAYS = 30          # window size: (today - N days) to today
NFATAT_WRITE_INTERVAL_SECONDS = 300  # 5 minutes -- less frequent than the main PR feed

# Best-guess column name holding the PR number in this report's JSON.
# Confirmed via SSMS: this report uses EPR_No (format like 0000010720),
# not PR_No -- that field only exists in the other report's table.
NFATAT_PR_COLUMN = "EPR_No"
