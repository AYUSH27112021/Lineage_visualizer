-- ==========================================================
-- STEP 3: GOLD LAYER (Aggregated / Business Logic)
-- ==========================================================
DATABASE datalake_catalog_gold;

CREATE VIEW gold_sales_summary AS
SELECT
    c.city,
    p.category,
    SUM(s.sale_amount) AS total_sales,
    COUNT(DISTINCT s.customer_id) AS total_customers,
    COUNT(DISTINCT s.product_id) AS total_products
FROM datalake_catalog_silver.silver_sales_enriched s
JOIN datalake_catalog_silver.silver_customer_clean c ON s.customer_id = c.customer_id
JOIN datalake_catalog_silver.silver_product_clean p ON s.product_id = p.product_id
GROUP BY c.city, p.category;

CREATE VIEW gold_top_city_sales AS
SELECT 
    city,
    SUM(total_sales) AS city_sales
FROM gold_sales_summary
GROUP BY city
HAVING SUM(total_sales) > 500000
ORDER BY city_sales DESC;
