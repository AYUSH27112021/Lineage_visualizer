-- ==========================================================
-- STEP 2: SILVER LAYER (Cleaned Data)
-- ==========================================================
DATABASE datalake_catalog_silver;

CREATE VIEW silver_customer_clean AS
SELECT 
    customer_id,
    TRIM(UPPER(first_name)) AS first_name,
    TRIM(UPPER(last_name)) AS last_name,
    LOWER(email) AS email,
    INITCAP(city) AS city,
    created_at
FROM datalake_catalog_bronze.bronze_customer_raw
WHERE email IS NOT NULL;

CREATE VIEW silver_sales_enriched AS
SELECT
    s.sale_id,
    s.customer_id,
    s.product_id,
    s.sale_amount,
    s.sale_date,
    s.region,
    c.city AS customer_city
FROM datalake_catalog_bronze.bronze_sales_raw s
LEFT JOIN silver_customer_clean c
ON s.customer_id = c.customer_id
WHERE s.sale_amount > 0;

CREATE VIEW silver_product_clean AS
SELECT 
    product_id,
    TRIM(product_name) AS product_name,
    TRIM(category) AS category,
    price
FROM datalake_catalog_bronze.bronze_product_raw
WHERE price > 0;
