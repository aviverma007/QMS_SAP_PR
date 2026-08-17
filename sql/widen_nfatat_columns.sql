-- Run once in SSMS to widen any existing NVARCHAR(1000) columns in
-- PRNFATatReportHistory to NVARCHAR(MAX), fixing the truncation error.
-- Safe to run multiple times -- only touches columns still at width 1000.

USE QMS_PR_Report;
GO

DECLARE @sql NVARCHAR(MAX) = '';

SELECT @sql = @sql +
    'ALTER TABLE [dbo].[PRNFATatReportHistory] ALTER COLUMN [' + COLUMN_NAME + '] NVARCHAR(MAX) NULL;' + CHAR(13)
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'PRNFATatReportHistory'
  AND DATA_TYPE = 'nvarchar'
  AND CHARACTER_MAXIMUM_LENGTH = 1000;

PRINT @sql;
EXEC sp_executesql @sql;

PRINT 'Done widening columns.';
