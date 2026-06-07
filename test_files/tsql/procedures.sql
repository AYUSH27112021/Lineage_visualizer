-------------------------------------------------------------
-- 1. SIMPLE STORED PROCEDURE
-------------------------------------------------------------
IF OBJECT_ID('SalesLT_Gold.usp_GetTopProducts', 'P') IS NOT NULL
    DROP PROCEDURE SalesLT_Gold.usp_GetTopProducts;
GO

CREATE PROCEDURE SalesLT_Gold.usp_GetTopProducts
    @TopN INT = 5
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (@TopN)
        ProductID,
        ProductName,
        TotalRevenue,
        TotalUnitsSold
    FROM SalesLT_Gold.gld_product_metrics
    ORDER BY TotalRevenue DESC;
END;
GO

-------------------------------------------------------------
-- 2. COMPLEX STORED PROCEDURE
-------------------------------------------------------------
IF OBJECT_ID('SalesLT_Gold.usp_AnalyzeCustomerSales', 'P') IS NOT NULL
    DROP PROCEDURE SalesLT_Gold.usp_AnalyzeCustomerSales;
GO

CREATE PROCEDURE SalesLT_Gold.usp_AnalyzeCustomerSales
    @MinOrders INT = 5,
    @ActiveCustomers INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT 
        c.CustomerID,
        c.FullName,
        c.TotalOrders,
        c.TotalRevenue
    INTO #ActiveCustomers
    FROM SalesLT_Gold.gld_customer_metrics AS c
    WHERE c.TotalOrders >= @MinOrders;

    SELECT @ActiveCustomers = COUNT(*) FROM #ActiveCustomers;

    SELECT 
        CustomerID, FullName, TotalOrders, TotalRevenue
    FROM #ActiveCustomers
    ORDER BY TotalRevenue DESC;

    DROP TABLE #ActiveCustomers;
END;
GO

-------------------------------------------------------------
-- 3. SCALAR FUNCTION
-------------------------------------------------------------
IF OBJECT_ID('SalesLT_Gold.fn_GetProfitMarginPct', 'FN') IS NOT NULL
    DROP FUNCTION SalesLT_Gold.fn_GetProfitMarginPct;
GO

CREATE FUNCTION SalesLT_Gold.fn_GetProfitMarginPct
(
    @Revenue DECIMAL(19,4),
    @Cost DECIMAL(19,4)
)
RETURNS DECIMAL(10,2)
AS
BEGIN
    DECLARE @Margin DECIMAL(10,2);
    IF @Revenue = 0 RETURN 0;
    SET @Margin = ((@Revenue - @Cost) / @Revenue) * 100;
    RETURN @Margin;
END;
GO

-------------------------------------------------------------
-- 4. TABLE-VALUED FUNCTION
-------------------------------------------------------------
IF OBJECT_ID('SalesLT_Gold.fn_GetTopSellingCategories', 'IF') IS NOT NULL
    DROP FUNCTION SalesLT_Gold.fn_GetTopSellingCategories;
GO

CREATE FUNCTION SalesLT_Gold.fn_GetTopSellingCategories(@MinRevenue DECIMAL(19,4))
RETURNS TABLE
AS
RETURN
(
    SELECT 
        p.CategoryName,
        SUM(g.TotalRevenue) AS TotalRevenue,
        COUNT(p.ProductID) AS ProductCount
    FROM SalesLT_Silver.ProductMaster AS p
    INNER JOIN SalesLT_Gold.gld_product_metrics AS g
        ON p.ProductID = g.ProductID
    GROUP BY p.CategoryName
    HAVING SUM(g.TotalRevenue) >= @MinRevenue
);
GO

-------------------------------------------------------------
-- 5. TRIGGER ON SILVER TABLE
-------------------------------------------------------------
IF OBJECT_ID('SalesLT_Silver.trg_ProductMaster_Update', 'TR') IS NOT NULL
    DROP TRIGGER SalesLT_Silver.trg_ProductMaster_Update;
GO

CREATE TRIGGER SalesLT_Silver.trg_ProductMaster_Update
ON SalesLT_Silver.ProductMaster
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;
    PRINT 'Trigger: ProductMaster updated - auditing changes';

    INSERT INTO dbo.ProductAuditLog(ProductID, ChangeDate, ChangeType)
    SELECT 
        i.ProductID, 
        GETDATE(), 
        'UPDATE'
    FROM inserted AS i;
END;
GO

-------------------------------------------------------------
-- 6. TRIGGER ON GOLD TABLE
-------------------------------------------------------------
IF OBJECT_ID('SalesLT_Gold.trg_CustomerMetrics_Insert', 'TR') IS NOT NULL
    DROP TRIGGER SalesLT_Gold.trg_CustomerMetrics_Insert;
GO

CREATE TRIGGER SalesLT_Gold.trg_CustomerMetrics_Insert
ON SalesLT_Gold.gld_customer_metrics
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;
    PRINT 'Trigger: New record inserted into gld_customer_metrics';

    INSERT INTO dbo.CustomerAuditLog(CustomerID, InsertDate)
    SELECT i.CustomerID, GETDATE()
    FROM inserted AS i;
END;
GO

-------------------------------------------------------------
-- 7. SUPPORT TABLES FOR TRIGGERS (Audit Logs)
-------------------------------------------------------------
IF OBJECT_ID('dbo.ProductAuditLog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ProductAuditLog (
        AuditID INT IDENTITY(1,1) PRIMARY KEY,
        ProductID INT,
        ChangeDate DATETIME,
        ChangeType NVARCHAR(50)
    );
END;
GO

IF OBJECT_ID('dbo.CustomerAuditLog', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CustomerAuditLog (
        AuditID INT IDENTITY(1,1) PRIMARY KEY,
        CustomerID INT,
        InsertDate DATETIME
    );
END;
GO

-------------------------------------------------------------
-- 8. METADATA RECORD INSERT
-------------------------------------------------------------
IF OBJECT_ID('dbo.ScriptMetrics', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ScriptMetrics (
        MetricName NVARCHAR(100),
        MetricValue INT
    );
END;

DELETE FROM dbo.ScriptMetrics;

INSERT INTO dbo.ScriptMetrics (MetricName, MetricValue)
VALUES 
    ('total_procedures', 2),
    ('total_functions', 2),
    ('total_triggers', 2),
    ('table_valued_functions', 1),
    ('scalar_functions', 1),
    ('output_parameters', 1),
    ('procedure_calls', 2),
    ('temp_table_usage', 1),
    ('complex_procedures_count', 1),
    ('orphan_procedures_count', 0);
GO

PRINT 'All procedures, functions, triggers, and metrics successfully created.';
GO
