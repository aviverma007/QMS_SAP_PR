-- Run once in SSMS, connected to 192.168.66.33 (your own Windows login is enough)

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'QMS_PR_Report')
BEGIN
    CREATE DATABASE QMS_PR_Report;
END
GO

USE QMS_PR_Report;
GO

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'PRReportHistory')
BEGIN
    CREATE TABLE dbo.PRReportHistory (
        id BIGINT IDENTITY(1,1) PRIMARY KEY,
        fetched_at DATETIME2 NOT NULL DEFAULT SYSDATETIME()
        -- Report-specific columns are added automatically by db_writer.py
        -- on first run, based on whatever fields the JSON contains.
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_fetched_at')
BEGIN
    CREATE INDEX ix_fetched_at ON dbo.PRReportHistory (fetched_at);
END
GO

PRINT 'Database and table ready.';
