-- Run once in SSMS on 192.168.66.33, connected as an admin login.
-- Creates a dedicated SQL-authenticated, read-only login for external
-- consumers (e.g. SAP ABAP via DB Connect / ADBC) to query QMS_PR_Report
-- without needing your Windows credentials or write access.

USE master;
GO

-- Change this password before running.
CREATE LOGIN qms_pr_reader WITH PASSWORD = 'ChangeThisPassword123!';
GO

USE QMS_PR_Report;
GO

CREATE USER qms_pr_reader FOR LOGIN qms_pr_reader;
GO

ALTER ROLE db_datareader ADD MEMBER qms_pr_reader;
GO

PRINT 'Read-only login qms_pr_reader created on QMS_PR_Report.';
