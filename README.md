# QMS SAP PR Report

Live viewer + SQL Server history logger for the SAP PR report
(`https://smartworlddevelopersonline.com/SapPrReport.php`).

## Setup

1. Create the database and table on SQL Server 192.168.66.33 -- run
   `sql/create_database.sql` once in SSMS.
2. Check the ODBC driver installed on this machine (server 34):
   Windows -> "ODBC Data Sources (64-bit)" -> Drivers tab. Update
   `app/db_config.py` if it doesn't say "ODBC Driver 17 for SQL Server".
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

## Run the live table + continuous SQL logging

```
cd app
py app.py
```

Open `http://localhost:5001` (or `http://<server-34-ip>:5001` from another
machine on the network).

This writes a new timestamped batch into SQL Server every 45 seconds
(configurable in `db_config.py`) while the app is running.

## Run as a scheduled push instead (Windows Task Scheduler)

If you'd rather have Task Scheduler trigger the write on its own schedule
(e.g. every 1 minute) instead of running `app.py` continuously:

```
cd app
py push_once.py
```

Set up a Task Scheduler task with:
- Trigger: Daily, repeat every 1 minute, indefinitely
- Action: Start a program -> `py`, arguments `push_once.py`,
  start in `<repo path>\app`

Logs go to `app/push_once.log`.

## Files

- `sql/create_database.sql` -- one-time SQL setup
- `app/db_config.py` -- connection settings (Windows Authentication, no password)
- `app/db_writer.py` -- fetch + auto-schema + insert logic
- `app/app.py` -- Flask live table viewer + continuous background writer
- `app/push_once.py` -- single-run script for Task Scheduler
