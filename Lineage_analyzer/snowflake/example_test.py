"""
Example Test Script for Snowflake Lineage Analyzer
Demonstrates how to use the system and what types of patterns it can handle
"""

import os
import tempfile
from pathlib import Path

# Support running as script or module
try:
    from .snowflake_main import LineageOrchestrator
except Exception:
    import sys as _sys
    # Add project root to sys.path
    _sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from Lineage_analyzer.snowflake.snowflake_main import LineageOrchestrator


# Sample SQL files demonstrating various Snowflake patterns
SAMPLE_SQL_FILES = {
    "01_create_tables.sql": """
-- Create base tables
CREATE OR REPLACE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR(100),
    email VARCHAR(100),
    created_date DATE,
    metadata VARIANT
);

CREATE OR REPLACE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER,
    order_date DATE,
    total_amount NUMBER(18,2),
    status VARCHAR(20),
    order_details VARIANT
);

CREATE OR REPLACE TABLE order_items (
    item_id NUMBER PRIMARY KEY,
    order_id NUMBER,
    product_id NUMBER,
    quantity NUMBER,
    unit_price NUMBER(18,2)
);
""",

    "02_views.sql": """
-- Create views with transformations
CREATE OR REPLACE VIEW vw_customer_orders AS
SELECT
    c.customer_id,
    c.customer_name,
    c.metadata:tier::STRING as customer_tier,
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

-- Materialized view
CREATE OR REPLACE MATERIALIZED VIEW vw_order_details AS
SELECT
    o.order_id,
    o.order_date,
    SUM(oi.quantity * oi.unit_price) as calculated_total,
    COUNT(oi.item_id) as item_count,
    ARRAY_AGG(oi.product_id) as product_list
FROM orders o
LEFT JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id, o.order_date;

-- Secure view
CREATE OR REPLACE SECURE VIEW vw_customer_pii AS
SELECT
    customer_id,
    customer_name,
    SUBSTR(email, 1, 3) || '***' as masked_email,
    created_date
FROM customers;
""",

    "03_cte_examples.sql": """
-- CTE examples
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
        c.email
    FROM customer_stats cs
    INNER JOIN customers c ON cs.customer_id = c.customer_id
    WHERE cs.lifetime_value > 5000
)
CREATE OR REPLACE TEMPORARY TABLE high_value_customers AS
SELECT * FROM high_value_customers;

-- Use temp table
INSERT INTO customer_summary (customer_id, total_value, tier)
SELECT
    customer_id,
    lifetime_value,
    'GOLD' as tier
FROM high_value_customers;
""",

    "04_merge_example.sql": """
-- MERGE statement with Snowflake syntax
MERGE INTO customer_summary AS target
USING (
    SELECT
        customer_id,
        SUM(total_amount) as total_spent,
        COUNT(*) as order_count
    FROM orders
    WHERE order_date >= DATEADD(MONTH, -12, CURRENT_DATE())
    GROUP BY customer_id
) AS source
ON target.customer_id = source.customer_id
WHEN MATCHED THEN
    UPDATE SET
        target.total_spent = source.total_spent,
        target.order_count = source.order_count,
        target.last_updated = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
    INSERT (customer_id, total_spent, order_count, last_updated)
    VALUES (source.customer_id, source.total_spent, source.order_count, CURRENT_TIMESTAMP());
""",

    "05_stored_procedures.sql": """
-- Stored procedure with Snowflake JavaScript
CREATE OR REPLACE PROCEDURE sp_get_customer_stats(customer_id NUMBER)
RETURNS TABLE(order_id NUMBER, amount NUMBER, customer_name VARCHAR)
LANGUAGE SQL
AS
$$
BEGIN
    -- Create temp table
    CREATE OR REPLACE TEMPORARY TABLE temp_orders AS
    SELECT order_id, total_amount as amount
    FROM orders
    WHERE customer_id = :customer_id;

    -- Return results with join
    RETURN TABLE(
        SELECT
            t.order_id,
            t.amount,
            c.customer_name
        FROM temp_orders t
        CROSS JOIN customers c
        WHERE c.customer_id = :customer_id
    );
END;
$$;

-- SQL procedure that processes data
CREATE OR REPLACE PROCEDURE sp_process_customer_report(customer_id NUMBER)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    order_count NUMBER;
    total_spent NUMBER;
BEGIN
    -- Calculate stats
    SELECT
        COUNT(*),
        COALESCE(SUM(total_amount), 0)
    INTO :order_count, :total_spent
    FROM orders
    WHERE customer_id = :customer_id;

    -- Update summary table
    UPDATE customer_summary
    SET
        total_orders = :order_count,
        total_spent = :total_spent,
        last_processed = CURRENT_TIMESTAMP()
    WHERE customer_id = :customer_id;

    RETURN 'Processed customer ' || :customer_id;
END;
$$;
""",

    "06_functions.sql": """
-- Table-valued function (UDF)
CREATE OR REPLACE FUNCTION fn_get_customer_orders(customer_id NUMBER)
RETURNS TABLE(order_id NUMBER, order_date DATE, total_amount NUMBER, item_count NUMBER)
AS
$$
    SELECT
        o.order_id,
        o.order_date,
        o.total_amount,
        COUNT(oi.item_id) as item_count
    FROM orders o
    LEFT JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.customer_id = customer_id
    GROUP BY o.order_id, o.order_date, o.total_amount
$$;

-- Scalar function
CREATE OR REPLACE FUNCTION fn_calculate_discount(amount NUMBER, customer_tier VARCHAR)
RETURNS NUMBER
AS
$$
    CASE
        WHEN customer_tier = 'GOLD' AND amount > 1000 THEN amount * 0.15
        WHEN customer_tier = 'SILVER' AND amount > 500 THEN amount * 0.10
        WHEN customer_tier = 'BRONZE' THEN amount * 0.05
        ELSE 0
    END
$$;

-- JavaScript UDF
CREATE OR REPLACE FUNCTION fn_parse_email_domain(email VARCHAR)
RETURNS VARCHAR
LANGUAGE JAVASCRIPT
AS
$$
    if (!EMAIL) return null;
    var parts = EMAIL.split('@');
    return parts.length > 1 ? parts[1] : null;
$$;
""",

    "07_semi_structured.sql": """
-- Working with VARIANT data
SELECT
    customer_id,
    metadata:tier::STRING as tier,
    metadata:preferences.notifications::BOOLEAN as notify_enabled,
    metadata:tags[0]::STRING as primary_tag
FROM customers;

-- LATERAL FLATTEN for arrays
SELECT
    o.order_id,
    o.order_date,
    f.value::NUMBER as product_id
FROM orders o,
LATERAL FLATTEN(input => o.order_details:products) f;

-- OBJECT_CONSTRUCT
INSERT INTO customer_events
SELECT
    customer_id,
    OBJECT_CONSTRUCT(
        'event_type', 'order_placed',
        'order_id', order_id,
        'amount', total_amount,
        'timestamp', order_date
    ) as event_data
FROM orders;

-- PARSE_JSON
CREATE OR REPLACE TABLE parsed_logs AS
SELECT
    log_id,
    PARSE_JSON(log_text) as log_data,
    log_data:severity::STRING as severity,
    log_data:message::STRING as message
FROM raw_logs;
""",

    "08_time_travel.sql": """
-- Time travel queries
SELECT *
FROM orders
AT(TIMESTAMP => '2024-01-01 00:00:00'::TIMESTAMP);

-- Before statement
SELECT *
FROM customer_summary
BEFORE(STATEMENT => '01a7e1f2-3000-1234-0000-0000abcd1234');

-- Changes clause for CDC
SELECT *
FROM orders
CHANGES(INFORMATION => DEFAULT)
AT(TIMESTAMP => DATEADD(DAY, -7, CURRENT_TIMESTAMP()))
END(TIMESTAMP => CURRENT_TIMESTAMP());
""",

    "09_tasks_and_streams.sql": """
-- Create stream for CDC
CREATE OR REPLACE STREAM orders_stream ON TABLE orders;

-- Create task
CREATE OR REPLACE TASK update_customer_stats
    WAREHOUSE = COMPUTE_WH
    SCHEDULE = '5 MINUTE'
WHEN
    SYSTEM$STREAM_HAS_DATA('orders_stream')
AS
    MERGE INTO customer_summary cs
    USING (
        SELECT
            customer_id,
            SUM(total_amount) as new_total,
            COUNT(*) as new_count
        FROM orders_stream
        WHERE METADATA$ACTION = 'INSERT'
        GROUP BY customer_id
    ) src
    ON cs.customer_id = src.customer_id
    WHEN MATCHED THEN
        UPDATE SET
            cs.total_spent = cs.total_spent + src.new_total,
            cs.order_count = cs.order_count + src.new_count;

-- Task with dependencies
CREATE OR REPLACE TASK cleanup_old_data
    WAREHOUSE = COMPUTE_WH
    AFTER update_customer_stats
AS
    DELETE FROM orders_stream WHERE METADATA$ACTION = 'DELETE';
""",

    "10_window_qualify.sql": """
-- QUALIFY clause (Snowflake-specific)
SELECT
    customer_id,
    order_id,
    order_date,
    total_amount,
    ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date DESC) as rn
FROM orders
QUALIFY rn <= 3;

-- Complex window functions
SELECT
    customer_id,
    order_date,
    total_amount,
    SUM(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY order_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) as running_total,
    AVG(total_amount) OVER (
        PARTITION BY customer_id
        ORDER BY order_date
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) as moving_avg
FROM orders;
"""
}


def create_test_environment():
    """Create temporary directory with sample SQL files"""
    temp_dir = tempfile.mkdtemp(prefix="snowflake_lineage_test_")
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
    print("SNOWFLAKE LINEAGE ANALYZER - EXAMPLE RUN")
    print("="*70 + "\n")

    print("Setting up test environment...")
    test_dir = create_test_environment()
    output_dir = Path(tempfile.gettempdir()) / "snowflake_lineage_output"

    # Run analysis
    print("\nStarting analysis...\n")
    orchestrator = LineageOrchestrator(
        sql_directory=test_dir,
        output_directory=str(output_dir),
        dialect="snowflake",
        debug=False  # Set to True for verbose output
    )

    try:
        results = orchestrator.run_full_analysis()

        # Print key findings
        print("\n" + "="*70)
        print("KEY FINDINGS")
        print("="*70)

        stmt_report = results.get('statement_report') or {}
        combined_summary = results.get('combined_summary') or {}
        procedure_summary = combined_summary.get('procedure_lineage') or {}
        llm_details = combined_summary.get('llm_analysis_details') or {}
        overall_stats = results.get('statistics') or {}

        print(f"\nStatement Lineage:")
        stmt_summary = stmt_report.get('summary') or {}
        print(f"   - Tables: {stmt_summary.get('total_tables', 0)}")
        print(f"   - Columns: {stmt_summary.get('total_columns', 0)}")
        print(f"   - Dependencies: {stmt_summary.get('total_dependencies', 0)}")
        print(f"   - CTEs: {stmt_summary.get('ctes', 0)}")
        print(f"   - Temp Tables: {stmt_summary.get('temp_tables', 0)}")

        print(f"\nProcedure Lineage:")
        print(f"   - Procedures analyzed: {procedure_summary.get('total_analyzed', 0)}")
        print(f"   - Successful analyses: {procedure_summary.get('successful_analyses', 0)}")
        print(f"   - Failed analyses: {procedure_summary.get('failed_analyses', 0)}")
        print(f"   - LLM success rate: {procedure_summary.get('llm_success_rate', 'N/A')}")
        print(f"   - Output files generated: {procedure_summary.get('output_files', 0)}")

        if llm_details:
            print(f"\nLLM Analysis Details:")
            print(f"   - Procedures: {llm_details.get('procedures_analyzed', 0)}")
            print(f"   - Functions: {llm_details.get('functions_analyzed', 0)}")
            print(f"   - Tasks: {llm_details.get('tasks_analyzed', 0)}")

        if overall_stats:
            print(f"\nOverall Statistics:")
            print(f"   - Files analyzed: {overall_stats.get('total_files', 0)}")
            print(f"   - Statement files: {overall_stats.get('total_statements', 0)}")
            print(f"   - Procedures (successful): {overall_stats.get('total_procedures', 0)}")
            print(f"   - Functions (successful): {overall_stats.get('total_functions', 0)}")
            print(f"   - Tasks (successful): {overall_stats.get('total_tasks', 0)}")
            print(f"   - LLM success rate: {overall_stats.get('llm_success_rate', 'N/A')}")

        output_files = results.get('output_files') or {}
        print(f"\nOutput Files:")
        if output_files:
            for label, path in output_files.items():
                print(f"   - {label}: {path}")
        else:
            print("   No output files reported.")

        # Show sample column lineage
        print(f"\nSample Column Lineage:")
        col_count = 0
        for col_key, col_info in (stmt_report.get('columns') or {}).items():
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
        raise

    finally:
        # Cleanup (optional - comment out to inspect files)
        import shutil
        print(f"\nCleaning up test directory: {test_dir}")
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    run_example_analysis()
