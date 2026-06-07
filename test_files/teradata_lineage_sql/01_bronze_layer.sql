-- ==========================================================
-- STEP 1: BRONZE LAYER (Raw Data)
-- ==========================================================
DATABASE datalake_catalog_bronze;

CREATE MULTISET TABLE bronze_customer_raw
(
    customer_id INTEGER,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email VARCHAR(200),
    city VARCHAR(100),
    created_at TIMESTAMP(6)
)
PRIMARY INDEX (customer_id);

CREATE MULTISET TABLE bronze_sales_raw
(
    sale_id INTEGER,
    customer_id INTEGER,
    product_id INTEGER,
    sale_amount DECIMAL(12,2),
    sale_date DATE,
    region VARCHAR(50)
)
PRIMARY INDEX (sale_id);

CREATE MULTISET TABLE bronze_product_raw
(
    product_id INTEGER,
    product_name VARCHAR(150),
    category VARCHAR(100),
    price DECIMAL(10,2)
)
PRIMARY INDEX (product_id);
