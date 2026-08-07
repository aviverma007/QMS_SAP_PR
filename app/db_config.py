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
