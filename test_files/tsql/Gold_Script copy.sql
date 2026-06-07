-- Create Gold Schema
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'SalesLT_Gold')
BEGIN
    EXEC('CREATE SCHEMA SalesLT_Gold');
END
GO

-------------------------------------------------------------
-- 1. Customer Metrics
-------------------------------------------------------------
IF OBJECT_ID('SalesLT_Gold.gld_customer_metrics', 'U') IS NOT NULL
    DROP TABLE SalesLT_Gold.gld_customer_metrics;
GO

CREATE TABLE SalesLT_Gold.gld_customer_metrics (
    CustomerKey       INT IDENTITY(1,1) PRIMARY KEY,
    CustomerID        INT NOT NULL,
    FullName          NVARCHAR(200) NOT NULL,
    TotalOrders       INT NOT NULL,
    TotalQuantity     INT NOT NULL,
    TotalRevenue      DECIMAL(19,4) NOT NULL,
    TotalDiscount     DECIMAL(19,4) NOT NULL,
    AverageOrderValue DECIMAL(19,4) NOT NULL,
    FirstOrderDate    DATE NULL,
    LastOrderDate     DATE NULL,
    LoadDate          DATETIME NOT NULL DEFAULT GETDATE(),
    SourceSystemID    INT NOT NULL,
    CONSTRAINT UQ_Gold_Customer UNIQUE (CustomerID)
);
GO

INSERT INTO SalesLT_Gold.gld_customer_metrics (
    CustomerID, FullName,
    TotalOrders, TotalQuantity, TotalRevenue, TotalDiscount,
    AverageOrderValue, FirstOrderDate, LastOrderDate, SourceSystemID
)
SELECT
    c.CustomerID,
    c.FullName,
    COUNT(DISTINCT s.SalesOrderID) AS TotalOrders,
    SUM(ISNULL(s.OrderQty,0)) AS TotalQuantity,
    SUM(ISNULL(s.LineTotal,0)) AS TotalRevenue,
    SUM(ISNULL(s.UnitPriceDiscount,0)) AS TotalDiscount,
    CASE WHEN COUNT(DISTINCT s.SalesOrderID) > 0 
         THEN SUM(ISNULL(s.LineTotal,0))/COUNT(DISTINCT s.SalesOrderID) 
         ELSE 0 END AS AverageOrderValue,
    MIN(s.OrderDate) AS FirstOrderDate,
    MAX(s.OrderDate) AS LastOrderDate,
    1 AS SourceSystemID
FROM SalesLT_Silver.CustomerMaster AS c
LEFT JOIN SalesLT_Silver.SalesFact AS s ON c.CustomerID = s.CustomerID
GROUP BY c.CustomerID, c.FullName;
GO

-------------------------------------------------------------
-- 2. Product Metrics
-------------------------------------------------------------
IF OBJECT_ID('SalesLT_Gold.gld_product_metrics', 'U') IS NOT NULL
    DROP TABLE SalesLT_Gold.gld_product_metrics;
GO

CREATE TABLE SalesLT_Gold.gld_product_metrics (
    ProductKey          INT IDENTITY(1,1) PRIMARY KEY,
    ProductID           INT NOT NULL,
    ProductName         NVARCHAR(100) NOT NULL,
    TotalUnitsSold      INT NOT NULL,
    TotalRevenue        DECIMAL(19,4) NOT NULL,
    AverageSellingPrice DECIMAL(19,4) NOT NULL,
    GrossMargin         DECIMAL(19,4) NULL,
    FirstSaleDate       DATE NULL,
    LastSaleDate        DATE NULL,
    LoadDate            DATETIME NOT NULL DEFAULT GETDATE(),
    SourceSystemID      INT NOT NULL,
    CONSTRAINT UQ_Gold_Product UNIQUE (ProductID)
);
GO

INSERT INTO SalesLT_Gold.gld_product_metrics (
    ProductID, ProductName,
    TotalUnitsSold, TotalRevenue, AverageSellingPrice, GrossMargin,
    FirstSaleDate, LastSaleDate, SourceSystemID
)
SELECT
    p.ProductID,
    p.ProductName,
    SUM(ISNULL(s.OrderQty,0)) AS TotalUnitsSold,
    SUM(ISNULL(s.LineTotal,0)) AS TotalRevenue,
    CASE WHEN SUM(ISNULL(s.OrderQty,0)) > 0 
         THEN SUM(ISNULL(s.LineTotal,0))/SUM(ISNULL(s.OrderQty,0)) 
         ELSE 0 END AS AverageSellingPrice,
    SUM(ISNULL((s.UnitPrice - p.StandardCost) * s.OrderQty,0)) AS GrossMargin,
    MIN(s.OrderDate) AS FirstSaleDate,
    MAX(s.OrderDate) AS LastSaleDate,
    1 AS SourceSystemID
FROM SalesLT_Silver.ProductMaster AS p
LEFT JOIN SalesLT_Silver.SalesFact AS s ON p.ProductID = s.ProductID
GROUP BY p.ProductID, p.ProductName;
GO

PRINT 'Gold layer tables created and populated successfully.';
GO
