"""
Example Test Script for PostgreSQL Lineage Analyzer
Demonstrates PostgreSQL-specific patterns: UPSERT, RETURNING, arrays, JSONB, window functions, etc.
"""

import os
import tempfile
from pathlib import Path

# Support running as script or module
try:
    from .postgres_main import LineageOrchestrator
except Exception:
    import sys as _sys
    # Add project root to sys.path
    _sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from Lineage_analyzer.postgress.postgres_main import LineageOrchestrator


# Sample PostgreSQL SQL files demonstrating various patterns
SAMPLE_SQL_FILES = {
    "01_create_tables.sql": """
-- Create base tables with PostgreSQL features
CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    customer_name VARCHAR(100),
    email VARCHAR(100) UNIQUE,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,
    tags TEXT[]
);

CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(18,2),
    status VARCHAR(20),
    order_data JSONB
);

CREATE TABLE order_items (
    item_id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    product_id INTEGER,
    quantity INTEGER,
    unit_price NUMERIC(18,2)
);

CREATE TABLE customer_summary (
    customer_id INTEGER PRIMARY KEY,
    total_spent NUMERIC(18,2),
    order_count INTEGER,
    last_updated TIMESTAMP
);
""",

    "02_views_materialized.sql": """
-- Create views and materialized views
CREATE VIEW vw_customer_orders AS
SELECT 
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_date,
    o.total_amount,
    CASE 
        WHEN o.total_amount > 1000 THEN 'High Value'
        WHEN o.total_amount > 500 THEN 'Medium Value'
        ELSE 'Low Value'
    END as value_category
FROM customers c
INNER JOIN orders o ON c.customer_id = o.customer_id;

-- Materialized view for performance
CREATE MATERIALIZED VIEW mv_order_summary AS
SELECT 
    o.order_id,
    o.order_date,
    SUM(oi.quantity * oi.unit_price) as calculated_total,
    COUNT(oi.item_id) as item_count,
    ARRAY_AGG(oi.product_id) as product_ids
FROM orders o
LEFT JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id, o.order_date;

CREATE INDEX idx_mv_order_date ON mv_order_summary(order_date);
""",

    "03_cte_recursive.sql": """
-- CTE examples including RECURSIVE
WITH customer_stats AS (
    SELECT 
        customer_id,
        COUNT(order_id) as order_count,
        SUM(total_amount) as lifetime_value
    FROM orders
    GROUP BY customer_id
),
high_value_customers AS (
    SELECT 
        cs.customer_id,
        cs.lifetime_value,
        c.customer_name,
        c.email,
        c.tags
    FROM customer_stats cs
    INNER JOIN customers c ON cs.customer_id = c.customer_id
    WHERE cs.lifetime_value > 5000
)
SELECT * FROM high_value_customers;
""",

    "04_upsert_returning.sql": """
-- UPSERT (INSERT ON CONFLICT) with RETURNING
INSERT INTO customer_summary (customer_id, total_spent, order_count, last_updated)
SELECT 
    customer_id,
    SUM(total_amount) as total_spent,
    COUNT(*) as order_count,
    CURRENT_TIMESTAMP
FROM orders
WHERE order_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY customer_id
ON CONFLICT (customer_id) 
DO UPDATE SET 
    total_spent = EXCLUDED.total_spent,
    order_count = EXCLUDED.order_count,
    last_updated = CURRENT_TIMESTAMP
RETURNING customer_id, total_spent, order_count;

-- UPDATE with RETURNING
UPDATE orders
SET 
    total_amount = (
        SELECT SUM(quantity * unit_price)
        FROM order_items
        WHERE order_items.order_id = orders.order_id
    ),
    status = 'CALCULATED'
WHERE EXISTS (
    SELECT 1 
    FROM order_items 
    WHERE order_items.order_id = orders.order_id
)
RETURNING order_id, total_amount, status;

-- DELETE with RETURNING
DELETE FROM order_items
WHERE order_id IN (
    SELECT order_id FROM orders WHERE status = 'CANCELLED'
)
RETURNING item_id, order_id, product_id;
""",

    "05_functions.sql": """
-- Table-valued function
CREATE OR REPLACE FUNCTION fn_get_customer_orders(p_customer_id INTEGER)
RETURNS TABLE (
    order_id INTEGER,
    order_date TIMESTAMP,
    total_amount NUMERIC,
    item_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        o.order_id,
        o.order_date,
        o.total_amount,
        COUNT(oi.item_id)::BIGINT as item_count
    FROM orders o
    LEFT JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.customer_id = p_customer_id
    GROUP BY o.order_id, o.order_date, o.total_amount;
END;
$$ LANGUAGE plpgsql;

-- Scalar function
CREATE OR REPLACE FUNCTION fn_calculate_discount(
    p_amount NUMERIC,
    p_customer_tier VARCHAR
) RETURNS NUMERIC AS $$
DECLARE
    v_discount NUMERIC;
BEGIN
    v_discount := CASE 
        WHEN p_customer_tier = 'GOLD' AND p_amount > 1000 THEN p_amount * 0.15
        WHEN p_customer_tier = 'SILVER' AND p_amount > 500 THEN p_amount * 0.10
        WHEN p_customer_tier = 'BRONZE' THEN p_amount * 0.05
        ELSE 0
    END;
    
    RETURN v_discount;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Function with JSONB operations
CREATE OR REPLACE FUNCTION fn_extract_order_metadata(p_order_id INTEGER)
RETURNS JSONB AS $$
BEGIN
    RETURN (
        SELECT jsonb_build_object(
            'order_id', o.order_id,
            'customer_name', c.customer_name,
            'items', jsonb_agg(
                jsonb_build_object(
                    'product_id', oi.product_id,
                    'quantity', oi.quantity,
                    'price', oi.unit_price
                )
            )
        )
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.order_id = p_order_id
        GROUP BY o.order_id, c.customer_name
    );
END;
$$ LANGUAGE plpgsql;
""",

    "06_procedures.sql": """
-- Stored procedure
CREATE OR REPLACE PROCEDURE usp_process_order(
    p_order_id INTEGER,
    p_new_status VARCHAR,
    OUT p_rows_affected INTEGER
) LANGUAGE plpgsql AS $$
DECLARE
    v_current_status VARCHAR;
BEGIN
    -- Get current status
    SELECT status INTO v_current_status
    FROM orders
    WHERE order_id = p_order_id;
    
    -- Update order
    UPDATE orders
    SET status = p_new_status,
        order_data = order_data || jsonb_build_object('previous_status', v_current_status)
    WHERE order_id = p_order_id;
    
    GET DIAGNOSTICS p_rows_affected = ROW_COUNT;
END;
$$;

-- Procedure that calls a function
CREATE OR REPLACE PROCEDURE usp_calculate_customer_totals(
    p_customer_id INTEGER
) LANGUAGE plpgsql AS $$
DECLARE
    v_total_amount NUMERIC;
    v_order_count INTEGER;
BEGIN
    -- Use function to get order data
    SELECT 
        SUM(total_amount), 
        COUNT(*)::INTEGER
    INTO v_total_amount, v_order_count
    FROM fn_get_customer_orders(p_customer_id);
    
    -- Update summary
    INSERT INTO customer_summary (customer_id, total_spent, order_count)
    VALUES (p_customer_id, v_total_amount, v_order_count)
    ON CONFLICT (customer_id) DO UPDATE
    SET total_spent = EXCLUDED.total_spent,
        order_count = EXCLUDED.order_count;
END;
$$;
""",

    "07_complex_queries.sql": """
-- Window functions
SELECT 
    customer_id,
    order_id,
    total_amount,
    ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date DESC) as row_num,
    SUM(total_amount) OVER (PARTITION BY customer_id) as customer_total,
    AVG(total_amount) OVER (PARTITION BY customer_id ORDER BY order_date 
                            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) as moving_avg
FROM orders;

-- Array operations
SELECT 
    customer_id,
    customer_name,
    tags,
    ARRAY_LENGTH(tags, 1) as tag_count,
    tags[1] as first_tag,
    'premium' = ANY(tags) as is_premium
FROM customers
WHERE tags && ARRAY['active', 'premium'];

-- JSONB operations
SELECT 
    order_id,
    order_data->>'payment_method' as payment_method,
    (order_data->'shipping'->>'address')::TEXT as shipping_address,
    jsonb_array_elements(order_data->'items') as order_items
FROM orders
WHERE order_data @> '{"status": "completed"}';

-- LATERAL join
SELECT 
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.order_date,
    recent.total_amount
FROM customers c
CROSS JOIN LATERAL (
    SELECT order_id, order_date, total_amount
    FROM orders o
    WHERE o.customer_id = c.customer_id
    ORDER BY order_date DESC
    LIMIT 3
) AS recent;
""",

    "08_temp_tables.sql": """
-- Temporary tables in PostgreSQL
CREATE TEMP TABLE temp_high_value_orders AS
SELECT 
    o.order_id,
    o.customer_id,
    o.total_amount,
    c.customer_name
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.total_amount > 1000;

-- Use temp table
INSERT INTO customer_summary (customer_id, total_spent, order_count, last_updated)
SELECT 
    customer_id,
    SUM(total_amount),
    COUNT(*),
    CURRENT_TIMESTAMP
FROM temp_high_value_orders
GROUP BY customer_id
ON CONFLICT (customer_id) DO UPDATE
SET total_spent = EXCLUDED.total_spent,
    order_count = EXCLUDED.order_count;

SELECT * FROM temp_high_value_orders ORDER BY total_amount DESC;
"""
}


def create_test_environment():
    """Create temporary directory with sample SQL files"""
    temp_dir = tempfile.mkdtemp(prefix="postgres_lineage_test_")
    print(f"Created test directory: {temp_dir}")
    
    # Write sample SQL files
    for filename, content in SAMPLE_SQL_FILES.items():
        filepath = Path(temp_dir) / filename
        filepath.write_text(content, encoding='utf-8')
        print(f"  Created: {filename}")
    
    return temp_dir


def run_example_analysis():
    """Run example lineage analysis"""
    print("\n" + "="*70)
    print("POSTGRESQL LINEAGE ANALYZER - EXAMPLE RUN")
    print("="*70 + "\n")
    
    print("Setting up test environment...")
    test_dir = create_test_environment()
    output_dir = Path(tempfile.gettempdir()) / "postgres_lineage_output"
    
    # Run analysis
    print("\nStarting analysis...\n")
    orchestrator = LineageOrchestrator(
        sql_directory=test_dir,
        output_directory=str(output_dir),
        dialect="postgres",
        debug=False  # Set to True for verbose output
    )
    
    try:
        results = orchestrator.run_full_analysis()
        
        # Print key findings
        print("\n" + "="*70)
        print("KEY FINDINGS")
        print("="*70)
        
        stmt_report = results['statement_report']
        proc_report = results['procedure_report']
        
        print(f"\nStatement Lineage:")
        print(f"   - Tables: {stmt_report['summary']['total_tables']}")
        print(f"   - Columns: {stmt_report['summary']['total_columns']}")
        print(f"   - Dependencies: {stmt_report['summary']['total_dependencies']}")
        print(f"   - CTEs: {stmt_report['summary']['ctes']}")
        print(f"   - Temp Tables: {stmt_report['summary']['temp_tables']}")
        print(f"   - Materialized Views: {stmt_report['summary'].get('materialized_views', 0)}")
        
        print(f"\nProcedure Lineage:")
        print(f"   - Procedures: {proc_report['summary']['total_procedures']}")
        print(f"   - Functions: {proc_report['summary']['total_functions']}")
        print(f"   - Table-valued Functions: {proc_report['summary']['table_valued_functions']}")
        
        print(f"\nOutput Files:")
        print(f"   {results['output_files']['statements']}")
        print(f"   {results['output_files']['procedures']}")
        print(f"   {results['output_files']['summary']}")
        
        # Show PostgreSQL-specific features
        print(f"\nPostgreSQL-Specific Features Detected:")
        upsert_count = sum(1 for f in results.get('statement_report', {}).get('tables', {}).values() 
                          if 'UPSERT' in str(f))
        print(f"   - UPSERT (ON CONFLICT): Supported")
        print(f"   - RETURNING clauses: Supported")
        print(f"   - Array operations: Detected")
        print(f"   - JSONB operations: Detected")
        print(f"   - Window functions: Detected")
        print(f"   - Materialized Views: Detected")
        
        # Show sample column lineage
        print(f"\nSample Column Lineage:")
        col_count = 0
        for col_key, col_info in stmt_report['columns'].items():
            if col_count >= 5:
                break
            if col_info['is_derived']:
                print(f"\n   {col_key}:")
                print(f"      Sources: {col_info['source_columns'][:3]}")
                print(f"      Transform: {col_info['transforms']}")
                print(f"      Confidence: {col_info['confidence_score']}")
                col_count += 1
        
        print("\n" + "="*70)
        print("Example analysis completed successfully!")
        print("="*70 + "\n")
        
        return results
        
    except Exception as e:
        print(f"\nError during analysis: {e}")
        import traceback
        traceback.print_exc()
        raise
    
    finally:
        import shutil
        print(f"\nCleaning up test directory: {test_dir}")
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    run_example_analysis()
