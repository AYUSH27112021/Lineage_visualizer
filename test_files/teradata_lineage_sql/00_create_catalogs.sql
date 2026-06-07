-- ==========================================================
-- STEP 0: Create Catalog and Layered Databases
-- ==========================================================

CREATE DATABASE datalake_catalog AS PERM = 50000000;

CREATE DATABASE datalake_catalog_bronze FROM datalake_catalog AS PERM = 20000000;
CREATE DATABASE datalake_catalog_silver FROM datalake_catalog AS PERM = 20000000;
CREATE DATABASE datalake_catalog_gold   FROM datalake_catalog AS PERM = 20000000;
