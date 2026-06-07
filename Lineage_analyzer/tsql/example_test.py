"""
Example Test Script for T-SQL Lineage Analyzer
Demonstrates how to use the system and what types of patterns it can handle
"""

import os
import tempfile
from pathlib import Path

# Support running as script or module
try:
    from .tsql_main import LineageOrchestrator
except Exception:
    import sys as _sys
    # Add project root to sys.path
    _sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from Lineage_analyzer.tsql.tsql_main import LineageOrchestrator


# Sample SQL files demonstrating various patterns
SAMPLE_SQL_FILES = {
    "01_create_tables.sql": """
-- Create base tables
CREATE TABLE customers (
    customer_id INT PRIMARY KEY,
    customer_name VARCHAR(100),
    email VARCHAR(100),
    created_date DATE
);
GO

CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    customer_id INT,
    order_date DATE,
    total_amount DECIMAL(18,2),
    status VARCHAR(20)
);
GO

CREATE TABLE order_items (
    item_id INT PRIMARY KEY,
    order_id INT,
    product_id INT,
    quantity INT,
    unit_price DECIMAL(18,2)
);
GO
""",

    "02_views.sql": """
-- Create views with transformations
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
GO

CREATE VIEW vw_order_details AS
SELECT 
    o.order_id,
    o.order_date,
    SUM(oi.quantity * oi.unit_price) as calculated_total,
    COUNT(oi.item_id) as item_count
FROM orders o
LEFT JOIN order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id, o.order_date;
GO
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
SELECT * INTO #high_value_customers FROM high_value_customers;
GO

-- Use temp table
INSERT INTO customer_summary (customer_id, total_value, tier)
SELECT 
    customer_id,
    lifetime_value,
    'GOLD' as tier
FROM #high_value_customers;
GO
""",

    "04_merge_example.sql": """
-- MERGE statement
MERGE INTO customer_summary AS target
USING (
    SELECT 
        customer_id,
        SUM(total_amount) as total_spent,
        COUNT(*) as order_count
    FROM orders
    WHERE order_date >= DATEADD(MONTH, -12, GETDATE())
    GROUP BY customer_id
) AS source
ON target.customer_id = source.customer_id
WHEN MATCHED THEN
    UPDATE SET 
        target.total_spent = source.total_spent,
        target.order_count = source.order_count,
        target.last_updated = GETDATE()
WHEN NOT MATCHED THEN
    INSERT (customer_id, total_spent, order_count, last_updated)
    VALUES (source.customer_id, source.total_spent, source.order_count, GETDATE());
GO
""",

    "05_stored_procedures.sql": """
-- Stored procedure with output parameter
CREATE PROCEDURE usp_GetCustomerStats
    @CustomerID INT,
    @TotalOrders INT OUTPUT,
    @TotalSpent DECIMAL(18,2) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    
    -- Create temp table
    DECLARE @temp_orders TABLE (
        order_id INT,
        amount DECIMAL(18,2)
    );
    
    -- Populate temp table
    INSERT INTO @temp_orders
    SELECT order_id, total_amount
    FROM orders
    WHERE customer_id = @CustomerID;
    
    -- Calculate stats
    SELECT 
        @TotalOrders = COUNT(*),
        @TotalSpent = SUM(amount)
    FROM @temp_orders;
    
    -- Return details
    SELECT 
        o.order_id,
        o.amount,
        c.customer_name
    FROM @temp_orders o
    INNER JOIN customers c ON c.customer_id = @CustomerID;
END
GO

-- Procedure that calls another procedure
CREATE PROCEDURE usp_ProcessCustomerReport
    @CustomerID INT
AS
BEGIN
    DECLARE @orders INT;
    DECLARE @spent DECIMAL(18,2);
    
    -- Call other procedure
    EXEC usp_GetCustomerStats @CustomerID, @orders OUTPUT, @spent OUTPUT;
    
    -- Update summary table
    UPDATE customer_summary
    SET 
        total_orders = @orders,
        total_spent = @spent,
        last_processed = GETDATE()
    WHERE customer_id = @CustomerID;
END
GO
""",

    "06_functions.sql": """
-- Table-valued function
CREATE FUNCTION fn_GetCustomerOrders(@CustomerID INT)
RETURNS TABLE
AS
RETURN (
    SELECT 
        o.order_id,
        o.order_date,
        o.total_amount,
        COUNT(oi.item_id) as item_count
    FROM orders o
    LEFT JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.customer_id = @CustomerID
    GROUP BY o.order_id, o.order_date, o.total_amount
);
GO

-- Scalar function
CREATE FUNCTION fn_CalculateDiscount(@Amount DECIMAL(18,2), @CustomerTier VARCHAR(20))
RETURNS DECIMAL(18,2)
AS
BEGIN
    DECLARE @Discount DECIMAL(18,2);
    
    SET @Discount = CASE 
        WHEN @CustomerTier = 'GOLD' AND @Amount > 1000 THEN @Amount * 0.15
        WHEN @CustomerTier = 'SILVER' AND @Amount > 500 THEN @Amount * 0.10
        WHEN @CustomerTier = 'BRONZE' THEN @Amount * 0.05
        ELSE 0
    END;
    
    RETURN @Discount;
END
GO
""",

    "07_complex_updates.sql": """
-- UPDATE with subquery
UPDATE orders
SET total_amount = (
    SELECT SUM(quantity * unit_price)
    FROM order_items
    WHERE order_items.order_id = orders.order_id
)
WHERE EXISTS (
    SELECT 1 
    FROM order_items 
    WHERE order_items.order_id = orders.order_id
);
GO

-- UPDATE with JOIN
UPDATE o
SET o.customer_name_cache = c.customer_name
FROM orders o
INNER JOIN customers c ON o.customer_id = c.customer_id;
GO
""",

    "08_set_operations.sql": """
-- UNION example
SELECT customer_id, 'Active' as status, order_date
FROM orders
WHERE order_date >= DATEADD(MONTH, -6, GETDATE())
UNION
SELECT customer_id, 'Inactive' as status, MAX(order_date)
FROM orders
WHERE order_date < DATEADD(MONTH, -6, GETDATE())
GROUP BY customer_id;
GO

-- INSERT with UNION
INSERT INTO customer_activity_log (customer_id, activity_type, activity_date)
SELECT customer_id, 'ORDER', order_date FROM orders
UNION ALL
SELECT customer_id, 'REGISTRATION', created_date FROM customers;
GO
"""
}


def create_test_environment():
    """Create temporary directory with sample SQL files"""
    temp_dir = tempfile.mkdtemp(prefix="tsql_lineage_test_")
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
    print("T-SQL LINEAGE ANALYZER - EXAMPLE RUN")
    print("="*70 + "\n")
    
    print("Setting up test environment...")
    test_dir = create_test_environment()
    output_dir = Path(tempfile.gettempdir()) / "tsql_lineage_output"
    
    # Run analysis
    print("\nStarting analysis...\n")
    orchestrator = LineageOrchestrator(
        sql_directory=test_dir,
        output_directory=str(output_dir),
        dialect="tsql",
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
            print(f"   - Triggers: {llm_details.get('triggers_analyzed', 0)}")
        
        if overall_stats:
            print(f"\nOverall Statistics:")
            print(f"   - Files analyzed: {overall_stats.get('total_files', 0)}")
            print(f"   - Statement files: {overall_stats.get('total_statements', 0)}")
            print(f"   - Procedures (successful): {overall_stats.get('total_procedures', 0)}")
            print(f"   - Functions (successful): {overall_stats.get('total_functions', 0)}")
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
