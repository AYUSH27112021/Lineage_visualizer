-- ==========================================================
-- STEP 4: STORED PROCEDURE (Refresh Workflow)
-- ==========================================================
DATABASE datalake_catalog_gold;

REPLACE PROCEDURE sp_refresh_gold_layer()
BEGIN
    -- 1. Refresh intermediate silver layer
    DELETE FROM volatile_table_silver_cache; -- Hypothetical cache
    INSERT INTO volatile_table_silver_cache
    SELECT * FROM datalake_catalog_silver.silver_sales_enriched;

    -- 2. Recreate gold summary views
    CALL DBC.SysExecSQL('REPLACE VIEW datalake_catalog_gold.gold_sales_summary AS
        SELECT c.city, p.category, SUM(s.sale_amount) AS total_sales
        FROM datalake_catalog_silver.silver_sales_enriched s
        JOIN datalake_catalog_silver.silver_customer_clean c ON s.customer_id = c.customer_id
        JOIN datalake_catalog_silver.silver_product_clean p ON s.product_id = p.product_id
        GROUP BY c.city, p.category');

    -- 3. Log the refresh status
    INSERT INTO etl_audit_log
    VALUES (CURRENT_TIMESTAMP, 'sp_refresh_gold_layer', 'SUCCESS');
END;
