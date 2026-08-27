-- ============================================================
-- ONE-TIME MIGRATION: collapse history tables to 1 row per PR
-- Run in SSMS on 192.168.66.33, connected as admin.
--
-- BEFORE RUNNING: stop the app on server 34:
--     Stop-Service QMSPRApp
--
-- What it does:
--   1. Builds a deduped copy of PRReportHistory keeping the LATEST
--      row per PR_No, plus a new first_seen column (earliest time
--      that PR was ever captured).
--   2. Renames the old bloated table to *_old, puts the deduped
--      table in its place (same name -> app/SAP unchanged).
--   3. Same for PRNFATatReportHistory on EPR_No.
--   4. Drops the *_old tables and shrinks the DB to reclaim ~10 GB.
--
-- Nothing about the CURRENT state of any PR is lost. Only the
-- thousands of identical duplicate snapshot copies are removed.
-- ============================================================

USE QMS_PR_Report;
SET NOCOUNT ON;
GO

-- ---------- 1. PRReportHistory -> one row per PR_No ----------
IF OBJECT_ID('dbo.PRReportHistory_new') IS NOT NULL DROP TABLE dbo.PRReportHistory_new;
GO

SELECT t.*
INTO dbo.PRReportHistory_new
FROM (
    SELECT h.*,
           ROW_NUMBER() OVER (PARTITION BY h.PR_No ORDER BY h.fetched_at DESC, h.id DESC) AS rn,
           MIN(h.fetched_at) OVER (PARTITION BY h.PR_No) AS first_seen
    FROM dbo.PRReportHistory h
) t
WHERE t.rn = 1;
GO

ALTER TABLE dbo.PRReportHistory_new DROP COLUMN rn;
GO
-- Old identity id is meaningless now (PR_No is the key) and would
-- block inserts because SELECT INTO strips the IDENTITY property.
ALTER TABLE dbo.PRReportHistory_new DROP COLUMN id;
GO

-- Rebuild identity + keys on the new table
ALTER TABLE dbo.PRReportHistory_new ALTER COLUMN PR_No NVARCHAR(100) NOT NULL;
GO
ALTER TABLE dbo.PRReportHistory_new ADD CONSTRAINT PK_PRReportHistory PRIMARY KEY (PR_No);
GO
CREATE INDEX ix_prh_fetched_at ON dbo.PRReportHistory_new (fetched_at);
GO

-- Swap
EXEC sp_rename 'dbo.PRReportHistory', 'PRReportHistory_old';
EXEC sp_rename 'dbo.PRReportHistory_new', 'PRReportHistory';
GO

-- ---------- 2. PRNFATatReportHistory -> one row per EPR_No ----------
IF OBJECT_ID('dbo.PRNFATatReportHistory_new') IS NOT NULL DROP TABLE dbo.PRNFATatReportHistory_new;
GO

SELECT t.*
INTO dbo.PRNFATatReportHistory_new
FROM (
    SELECT h.*,
           ROW_NUMBER() OVER (PARTITION BY h.EPR_No ORDER BY h.fetched_at DESC, h.id DESC) AS rn,
           MIN(h.fetched_at) OVER (PARTITION BY h.EPR_No) AS first_seen
    FROM dbo.PRNFATatReportHistory h
) t
WHERE t.rn = 1;
GO

ALTER TABLE dbo.PRNFATatReportHistory_new DROP COLUMN rn;
GO
ALTER TABLE dbo.PRNFATatReportHistory_new DROP COLUMN id;
GO

ALTER TABLE dbo.PRNFATatReportHistory_new ALTER COLUMN EPR_No NVARCHAR(100) NOT NULL;
GO
ALTER TABLE dbo.PRNFATatReportHistory_new ADD CONSTRAINT PK_PRNFATatReportHistory PRIMARY KEY (EPR_No);
GO
CREATE INDEX ix_nfatat_fetched_at ON dbo.PRNFATatReportHistory_new (fetched_at);
GO

EXEC sp_rename 'dbo.PRNFATatReportHistory', 'PRNFATatReportHistory_old';
EXEC sp_rename 'dbo.PRNFATatReportHistory_new', 'PRNFATatReportHistory';
GO

-- ---------- 3. Verify BEFORE dropping the old tables ----------
SELECT 'PRReportHistory (new)' AS tbl, COUNT(*) AS rows FROM dbo.PRReportHistory
UNION ALL
SELECT 'PRReportHistory_old', COUNT(*) FROM dbo.PRReportHistory_old
UNION ALL
SELECT 'PRNFATatReportHistory (new)', COUNT(*) FROM dbo.PRNFATatReportHistory
UNION ALL
SELECT 'PRNFATatReportHistory_old', COUNT(*) FROM dbo.PRNFATatReportHistory_old;
GO

-- ============================================================
-- STOP AND CHECK the counts above. New tables should have ~600-700
-- rows each (one per unique PR). If that looks right, run PART 2
-- below to reclaim the 10 GB.
-- ============================================================

-- ---------- PART 2: drop old tables + shrink (run after verifying) ----------
-- DROP TABLE dbo.PRReportHistory_old;
-- DROP TABLE dbo.PRNFATatReportHistory_old;
-- GO
-- DBCC SHRINKDATABASE (QMS_PR_Report, 10);
-- GO
-- SELECT name, CAST(size * 8.0 / 1024 AS INT) AS size_MB FROM sys.database_files;
