IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'SalesLT_Silver')
BEGIN
    EXEC('CREATE SCHEMA SalesLT_Silver');
END
GO

-- 1. Customer Master

IF OBJECT_ID('SalesLT_Silver.CustomerMaster', 'U') IS NOT NULL

    DROP TABLE SalesLT_Silver.CustomerMaster;

GO



CREATE TABLE SalesLT_Silver.CustomerMaster (

    CustomerKey     INT IDENTITY(1,1) PRIMARY KEY,

    CustomerID      INT NOT NULL,

    FullName        NVARCHAR(200) NOT NULL,

    FirstName       NVARCHAR(50) NOT NULL,

    MiddleName      NVARCHAR(50) NULL,

    LastName        NVARCHAR(50) NOT NULL,

    EmailAddress    NVARCHAR(50) NULL,

    Phone           NVARCHAR(25) NULL,

    CompanyName     NVARCHAR(128) NULL,

    City            NVARCHAR(30) NULL,

    StateProvince   NVARCHAR(50) NULL,

    CountryRegion   NVARCHAR(50) NULL,

    PostalCode      NVARCHAR(15) NULL,

    IsActive        BIT NOT NULL DEFAULT 1,

    LoadDate        DATETIME NOT NULL DEFAULT GETDATE(),

    ModifiedDate    DATETIME NOT NULL,

    SourceSystemID  INT NOT NULL,

    CONSTRAINT UQ_Silver_CustomerMaster UNIQUE (CustomerID)

);

GO



INSERT INTO SalesLT_Silver.CustomerMaster (

    CustomerID, FullName, FirstName, MiddleName, LastName,

    EmailAddress, Phone, CompanyName,

    City, StateProvince, CountryRegion, PostalCode,

    IsActive, ModifiedDate, SourceSystemID

)

SELECT

    c.CustomerID,

    RTRIM(LTRIM(ISNULL(c.FirstName, '') + ' ' + ISNULL(c.MiddleName + ' ', '') + ISNULL(c.LastName, ''))) AS FullName,

    c.FirstName,

    c.MiddleName,

    c.LastName,

    c.EmailAddress,

    c.Phone,

    c.CompanyName,

    a.City,

    a.StateProvince,

    a.CountryRegion,

    a.PostalCode,

    1 AS IsActive,

    c.ModifiedDate,

    1 AS SourceSystemID

FROM SalesLT.Customer AS c

OUTER APPLY (

    SELECT TOP 1 a.City, a.StateProvince, a.CountryRegion, a.PostalCode

    FROM SalesLT.CustomerAddress AS ca

    JOIN SalesLT.Address AS a ON ca.AddressID = a.AddressID

    WHERE ca.CustomerID = c.CustomerID

    ORDER BY ca.ModifiedDate DESC

) AS a;

-- 2. Product Master (Silver Layer)

IF OBJECT_ID('SalesLT_Silver.ProductMaster', 'U') IS NOT NULL

    DROP TABLE SalesLT_Silver.ProductMaster;

GO



CREATE TABLE SalesLT_Silver.ProductMaster (

    ProductKey          INT IDENTITY(1,1) PRIMARY KEY,  -- Surrogate key

    ProductID           INT NOT NULL,                   -- Source system ProductID

    ProductName         NVARCHAR(100) NOT NULL,        -- Product name

    ProductNumber       NVARCHAR(25) NOT NULL,         -- Product number/code

    CategoryName        NVARCHAR(50) NULL,            -- Product category name

    ParentCategoryName  NVARCHAR(50) NULL,            -- Parent category name

    ModelName           NVARCHAR(50) NULL,            -- Product model

    Description         NVARCHAR(400) NULL,           -- Product description (English)

    Color               NVARCHAR(15) NULL,            -- Color

    Size                NVARCHAR(5) NULL,             -- Size

    Weight              DECIMAL(8,2) NULL,            -- Weight

    StandardCost        DECIMAL(19,4) NOT NULL,       -- Cost

    ListPrice           DECIMAL(19,4) NOT NULL,       -- Selling price

    ProfitMarginPct     DECIMAL(10,2) NULL,           -- Derived profit %

    IsCurrentlyAvailable BIT NOT NULL,               -- Active product flag

    LoadDate            DATETIME NOT NULL DEFAULT GETDATE(),

    ModifiedDate        DATETIME NOT NULL,           -- Source ModifiedDate

    SourceSystemID      INT NOT NULL,                -- Source system identifier

    CONSTRAINT UQ_Silver_ProductMaster UNIQUE (ProductID)

);

GO



-- Insert data into ProductMaster

INSERT INTO SalesLT_Silver.ProductMaster (

    ProductID, ProductName, ProductNumber, CategoryName, ParentCategoryName,

    ModelName, Description, Color, Size, Weight,

    StandardCost, ListPrice, ProfitMarginPct,

    IsCurrentlyAvailable, ModifiedDate, SourceSystemID

)

SELECT

    p.ProductID,

    p.Name AS ProductName,

    p.ProductNumber,

    pc.Name AS CategoryName,                    -- Category name from ProductCategory

    pcp.Name AS ParentCategoryName,             -- Parent category name from ProductCategory

    pm.Name AS ModelName,                        -- Product model name

    d.Description,                               -- Latest product description (English)

    p.Color,

    p.Size,

    p.Weight,

    p.StandardCost,

    p.ListPrice,

    CASE 

        WHEN p.ListPrice > 0 THEN ((p.ListPrice - p.StandardCost) / p.ListPrice) * 100 

        ELSE NULL 

    END AS ProfitMarginPct,                       -- Derived profit %

    CASE 

        WHEN p.SellEndDate IS NULL OR p.SellEndDate > GETDATE() THEN 1 

        ELSE 0 

    END AS IsCurrentlyAvailable,                 -- Active product flag

    p.ModifiedDate,

    1 AS SourceSystemID

FROM SalesLT.Product AS p

-- Join to get product category name

LEFT JOIN SalesLT.ProductCategory AS pc 

       ON p.ProductCategoryID = pc.ProductCategoryID

-- Join to get parent category name

LEFT JOIN SalesLT.ProductCategory AS pcp 

       ON pc.ParentProductCategoryID = pcp.ProductCategoryID



LEFT JOIN SalesLT.ProductModel AS pm 

       ON p.ProductModelID = pm.ProductModelID



OUTER APPLY (

    SELECT TOP 1 pd.Description

    FROM SalesLT.ProductModelProductDescription AS pmpd

    JOIN SalesLT.ProductDescription AS pd

       ON pmpd.ProductDescriptionID = pd.ProductDescriptionID

    WHERE pmpd.ProductModelID = p.ProductModelID

    ORDER BY pd.ModifiedDate DESC

) AS d;

GO



PRINT 'SalesLT_Silver.ProductMaster populated successfully.';



-- 3. Sales Fact

IF OBJECT_ID('SalesLT_Silver.SalesFact', 'U') IS NOT NULL

    DROP TABLE SalesLT_Silver.SalesFact;

GO



CREATE TABLE SalesLT_Silver.SalesFact (

    SalesFactKey       INT IDENTITY(1,1) PRIMARY KEY,

    SalesOrderID       INT NOT NULL,

    SalesOrderDetailID INT NOT NULL,

    SalesOrderNumber   NVARCHAR(25) NOT NULL,

    CustomerID         INT NOT NULL,

    ProductID          INT NOT NULL,

    OrderDate          DATE NOT NULL,

    ShipDate           DATE NULL,

    OrderYear          INT NOT NULL,

    OrderMonth         INT NOT NULL,

    OrderQuarter       INT NOT NULL,

    DaysToShip         INT NULL,

    OrderQty           INT NOT NULL,

    UnitPrice          DECIMAL(19,4) NOT NULL,

    UnitPriceDiscount  DECIMAL(19,4) NOT NULL,

    LineTotal          DECIMAL(19,4) NOT NULL,

    DiscountPct        DECIMAL(5,2) NULL,

    TotalDue           DECIMAL(19,4) NOT NULL,

    TaxAmt             DECIMAL(19,4) NOT NULL,

    Freight            DECIMAL(19,4) NOT NULL,

    LoadDate           DATETIME NOT NULL DEFAULT GETDATE(),

    ModifiedDate       DATETIME NOT NULL,

    SourceSystemID     INT NOT NULL,

    CONSTRAINT UQ_Silver_SalesFact UNIQUE (SalesOrderID, SalesOrderDetailID)

);

GO



INSERT INTO SalesLT_Silver.SalesFact (

    SalesOrderID, SalesOrderDetailID, SalesOrderNumber, CustomerID, ProductID,

    OrderDate, ShipDate, OrderYear, OrderMonth, OrderQuarter, DaysToShip,

    OrderQty, UnitPrice, UnitPriceDiscount, LineTotal, DiscountPct,

    TotalDue, TaxAmt, Freight, ModifiedDate, SourceSystemID

)

SELECT

    soh.SalesOrderID,

    sod.SalesOrderDetailID,

    soh.SalesOrderNumber,

    soh.CustomerID,

    sod.ProductID,

    soh.OrderDate,

    soh.ShipDate,

    YEAR(soh.OrderDate) AS OrderYear,

    MONTH(soh.OrderDate) AS OrderMonth,

    DATEPART(QUARTER, soh.OrderDate) AS OrderQuarter,

    DATEDIFF(DAY, soh.OrderDate, soh.ShipDate) AS DaysToShip,

    sod.OrderQty,

    sod.UnitPrice,

    sod.UnitPriceDiscount,

    sod.LineTotal,

    CASE WHEN sod.UnitPrice > 0 THEN (sod.UnitPriceDiscount / sod.UnitPrice) * 100 ELSE NULL END AS DiscountPct,

    soh.TotalDue,

    soh.TaxAmt,

    soh.Freight,

    sod.ModifiedDate,

    1 AS SourceSystemID

FROM SalesLT.SalesOrderHeader AS soh

JOIN SalesLT.SalesOrderDetail AS sod

  ON soh.SalesOrderID = sod.SalesOrderID;

GO

