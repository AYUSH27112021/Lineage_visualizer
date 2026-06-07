"""
Example Test Script for Metadata-Based T-SQL Lineage Analyzer
Demonstrates how to use the system with database connection instead of SQL files.

This example shows:
1. How to use the MetadataLineageOrchestrator with a database connection
2. How to use pre-extracted metadata from a JSON file
3. How to interpret the output
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime

# Support running as script or module
try:
    from .metadata_lineage_main import MetadataLineageOrchestrator
except ImportError:
    # Add parent to path for direct script execution
    sys.path.insert(0, str(Path(__file__).parent))
    from metadata_lineage_main import MetadataLineageOrchestrator


# Sample metadata structure (simulates what enhanced_metadata_extractor produces)
SAMPLE_METADATA = {
    "database": "SampleDB",
    "server": "localhost",
    "tables": [
        {
            "schema": "dbo",
            "name": "customers",
            "columns": [
                {"name": "customer_id", "data_type": "int", "is_nullable": False},
                {"name": "customer_name", "data_type": "varchar", "is_nullable": True},
                {"name": "email", "data_type": "varchar", "is_nullable": True},
                {"name": "created_date", "data_type": "date", "is_nullable": True}
            ]
        },
        {
            "schema": "dbo",
            "name": "orders",
            "columns": [
                {"name": "order_id", "data_type": "int", "is_nullable": False},
                {"name": "customer_id", "data_type": "int", "is_nullable": False},
                {"name": "order_date", "data_type": "date", "is_nullable": True},
                {"name": "total_amount", "data_type": "decimal", "is_nullable": True},
                {"name": "status", "data_type": "varchar", "is_nullable": True}
            ]
        },
        {
            "schema": "dbo",
            "name": "order_items",
            "columns": [
                {"name": "item_id", "data_type": "int", "is_nullable": False},
                {"name": "order_id", "data_type": "int", "is_nullable": False},
                {"name": "product_id", "data_type": "int", "is_nullable": False},
                {"name": "quantity", "data_type": "int", "is_nullable": True},
                {"name": "unit_price", "data_type": "decimal", "is_nullable": True}
            ]
        },
        {
            "schema": "dbo",
            "name": "customer_summary",
            "columns": [
                {"name": "customer_id", "data_type": "int", "is_nullable": False},
                {"name": "total_value", "data_type": "decimal", "is_nullable": True},
                {"name": "tier", "data_type": "varchar", "is_nullable": True},
                {"name": "total_orders", "data_type": "int", "is_nullable": True},
                {"name": "total_spent", "data_type": "decimal", "is_nullable": True},
                {"name": "last_processed", "data_type": "datetime", "is_nullable": True}
            ]
        }
    ],
    "views": [
        {
            "schema_name": "dbo",
            "view_name": "vw_customer_orders",
            "definition": """
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
FROM dbo.customers c
INNER JOIN dbo.orders o ON c.customer_id = o.customer_id
""",
            "create_date": "2024-01-15",
            "modify_date": "2024-06-20"
        },
        {
            "schema_name": "dbo",
            "view_name": "vw_order_details",
            "definition": """
CREATE VIEW vw_order_details AS
SELECT 
    o.order_id,
    o.order_date,
    SUM(oi.quantity * oi.unit_price) as calculated_total,
    COUNT(oi.item_id) as item_count
FROM dbo.orders o
LEFT JOIN dbo.order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id, o.order_date
""",
            "create_date": "2024-02-10",
            "modify_date": "2024-02-10"
        }
    ],
    "procedures": [
        {
            "schema_name": "dbo",
            "procedure_name": "usp_GetCustomerStats",
            "definition": """
CREATE PROCEDURE usp_GetCustomerStats
    @CustomerID INT,
    @TotalOrders INT OUTPUT,
    @TotalSpent DECIMAL(18,2) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @temp_orders TABLE (
        order_id INT,
        amount DECIMAL(18,2)
    );
    
    INSERT INTO @temp_orders
    SELECT order_id, total_amount
    FROM dbo.orders
    WHERE customer_id = @CustomerID;
    
    SELECT 
        @TotalOrders = COUNT(*),
        @TotalSpent = SUM(amount)
    FROM @temp_orders;
    
    SELECT 
        o.order_id,
        o.amount,
        c.customer_name
    FROM @temp_orders o
    INNER JOIN dbo.customers c ON c.customer_id = @CustomerID;
END
""",
            "create_date": "2024-01-20",
            "modify_date": "2024-05-15"
        },
        {
            "schema_name": "dbo",
            "procedure_name": "usp_ProcessCustomerReport",
            "definition": """
CREATE PROCEDURE usp_ProcessCustomerReport
    @CustomerID INT
AS
BEGIN
    DECLARE @orders INT;
    DECLARE @spent DECIMAL(18,2);
    
    EXEC usp_GetCustomerStats @CustomerID, @orders OUTPUT, @spent OUTPUT;
    
    UPDATE dbo.customer_summary
    SET 
        total_orders = @orders,
        total_spent = @spent,
        last_processed = GETDATE()
    WHERE customer_id = @CustomerID;
END
""",
            "create_date": "2024-02-01",
            "modify_date": "2024-06-01"
        }
    ],
    "functions": [
        {
            "schema_name": "dbo",
            "function_name": "fn_GetCustomerOrders",
            "function_type": "SQL_TABLE_VALUED_FUNCTION",
            "definition": """
CREATE FUNCTION fn_GetCustomerOrders(@CustomerID INT)
RETURNS TABLE
AS
RETURN (
    SELECT 
        o.order_id,
        o.order_date,
        o.total_amount,
        COUNT(oi.item_id) as item_count
    FROM dbo.orders o
    LEFT JOIN dbo.order_items oi ON o.order_id = oi.order_id
    WHERE o.customer_id = @CustomerID
    GROUP BY o.order_id, o.order_date, o.total_amount
)
""",
            "create_date": "2024-03-01",
            "modify_date": "2024-03-01"
        },
        {
            "schema_name": "dbo",
            "function_name": "fn_CalculateDiscount",
            "function_type": "SQL_SCALAR_FUNCTION",
            "definition": """
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
""",
            "create_date": "2024-03-15",
            "modify_date": "2024-03-15"
        }
    ],
    "triggers": [
        {
            "schema_name": "dbo",
            "trigger_name": "trg_OrderInsert",
            "table_name": "orders",
            "trigger_event": "INSERT",
            "definition": """
CREATE TRIGGER trg_OrderInsert
ON dbo.orders
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;
    
    UPDATE cs
    SET 
        cs.total_orders = cs.total_orders + 1,
        cs.total_spent = cs.total_spent + i.total_amount
    FROM dbo.customer_summary cs
    INNER JOIN inserted i ON cs.customer_id = i.customer_id;
END
""",
            "is_disabled": False,
            "create_date": "2024-04-01",
            "modify_date": "2024-04-01"
        }
    ],
    "query_history": [
        {
            "query_text_id": 1001,
            "query_sql_text": """
SELECT 
    c.customer_name,
    COUNT(o.order_id) as order_count,
    SUM(o.total_amount) as total_spent
FROM dbo.customers c
LEFT JOIN dbo.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_name
ORDER BY total_spent DESC
""",
            "count_executions": 1250,
            "avg_duration_ms": 45.5,
            "avg_cpu_time_ms": 12.3,
            "last_execution_time": "2024-06-20T14:30:00Z"
        },
        {
            "query_text_id": 1002,
            "query_sql_text": """
SELECT 
    o.order_id,
    o.order_date,
    c.customer_name,
    oi.product_id,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price as line_total
FROM dbo.orders o
INNER JOIN dbo.customers c ON o.customer_id = c.customer_id
INNER JOIN dbo.order_items oi ON o.order_id = oi.order_id
WHERE o.order_date >= DATEADD(month, -3, GETDATE())
""",
            "count_executions": 850,
            "avg_duration_ms": 120.8,
            "avg_cpu_time_ms": 35.2,
            "last_execution_time": "2024-06-20T15:45:00Z"
        }
    ],
    "dependencies": [],
    "summary": {
        "database": "SampleDB",
        "server": "localhost",
        "extraction_timestamp": datetime.now().isoformat(),
        "table_count": 4,
        "view_count": 2,
        "procedure_count": 2,
        "function_count": 2,
        "trigger_count": 1,
        "column_count": 22,
        "index_count": 0,
        "foreign_key_count": 0,
        "query_history_count": 2
    },
    "parser_support": {
        "table_disambiguation": {
            "unique_tables": {
                "customers": "dbo.customers",
                "orders": "dbo.orders",
                "order_items": "dbo.order_items",
                "customer_summary": "dbo.customer_summary"
            },
            "ambiguous_tables": {},
            "schema_tables": {
                "dbo": ["customers", "orders", "order_items", "customer_summary"]
            }
        },
        "database_name": "SampleDB",
        "schemas": ["dbo"]
    }
}


def create_sample_metadata_file():
    """Create a temporary metadata file for testing."""
    temp_dir = tempfile.mkdtemp(prefix="metadata_lineage_test_")
    metadata_path = Path(temp_dir) / "sample_metadata.json"
    
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(SAMPLE_METADATA, f, indent=2, default=str)
    
    print(f"Created sample metadata file: {metadata_path}")
    return temp_dir, metadata_path


def run_example_with_preloaded_metadata():
    """
    Run example analysis using pre-loaded metadata.
    
    This demonstrates how to use the analyzer when you already have
    metadata in memory (e.g., from a previous extraction or API call).
    """
    print("\n" + "="*70)
    print("METADATA-BASED LINEAGE ANALYZER - PRELOADED METADATA EXAMPLE")
    print("="*70 + "\n")
    
    output_dir = Path(tempfile.gettempdir()) / "metadata_lineage_output"
    
    # Create orchestrator with preloaded metadata
    orchestrator = MetadataLineageOrchestrator(
        # Database connection params (not used when preloaded_metadata is provided)
        server="localhost",
        database="SampleDB",
        username="",
        password="",
        # Output configuration
        output_directory=str(output_dir),
        dialect="tsql",
        debug=True,
        # LLM configuration (using Ollama by default)
        ollama_url="http://localhost:11434",
        ollama_model="qwen2.5-coder:14b",
        # Pass preloaded metadata
        preloaded_metadata=SAMPLE_METADATA
    )
    
    print("Orchestrator initialized with preloaded metadata:")
    print(f"  Tables: {len(SAMPLE_METADATA['tables'])}")
    print(f"  Views: {len(SAMPLE_METADATA['views'])}")
    print(f"  Procedures: {len(SAMPLE_METADATA['procedures'])}")
    print(f"  Functions: {len(SAMPLE_METADATA['functions'])}")
    print(f"  Triggers: {len(SAMPLE_METADATA['triggers'])}")
    print(f"  Query History: {len(SAMPLE_METADATA['query_history'])}")
    
    print("\n✓ Orchestrator ready for analysis")
    print("  To run full analysis, ensure Ollama is running with the specified model")
    print("  Or provide an OpenAI API key via openai_api_key parameter")
    
    return orchestrator


def run_example_with_metadata_file():
    """
    Run example analysis using metadata from a JSON file.
    
    This demonstrates how to use the analyzer when metadata has been
    pre-extracted and saved to disk.
    """
    print("\n" + "="*70)
    print("METADATA-BASED LINEAGE ANALYZER - METADATA FILE EXAMPLE")
    print("="*70 + "\n")
    
    # Create sample metadata file
    temp_dir, metadata_path = create_sample_metadata_file()
    output_dir = Path(tempfile.gettempdir()) / "metadata_lineage_output_file"
    
    try:
        # Create orchestrator with metadata file path
        orchestrator = MetadataLineageOrchestrator(
            server="localhost",
            database="SampleDB",
            username="",
            password="",
            output_directory=str(output_dir),
            dialect="tsql",
            debug=True,
            # Load metadata from file
            metadata_file_path=str(metadata_path)
        )
        
        print(f"Metadata loaded from: {metadata_path}")
        print(f"Output directory: {output_dir}")
        
        # Verify metadata was loaded
        if orchestrator.metadata:
            summary = orchestrator.metadata.get('summary', {})
            print(f"\nLoaded metadata summary:")
            print(f"  Tables: {summary.get('table_count', 0)}")
            print(f"  Views: {summary.get('view_count', 0)}")
            print(f"  Procedures: {summary.get('procedure_count', 0)}")
            print(f"  Functions: {summary.get('function_count', 0)}")
            print(f"  Triggers: {summary.get('trigger_count', 0)}")
        
        print("\n✓ Orchestrator ready for analysis")
        
        return orchestrator
        
    finally:
        # Cleanup
        import shutil
        print(f"\nCleaning up temp directory: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)


def demonstrate_tabular_analysis():
    """
    Demonstrate analysis of tabular SQL (views and query history).
    
    This runs the view/query analysis without requiring LLM.
    """
    print("\n" + "="*70)
    print("TABULAR SQL ANALYSIS DEMONSTRATION")
    print("="*70 + "\n")
    
    # Import the view analyzer directly
    from metadata_view_analyzer import MetadataViewAnalyzer
    
    # Create analyzer with metadata context
    analyzer = MetadataViewAnalyzer(
        dialect="tsql",
        metadata=SAMPLE_METADATA,
        debug=True
    )
    
    print("Analyzing views...")
    
    for view in SAMPLE_METADATA['views']:
        view_name = f"{view['schema_name']}.{view['view_name']}"
        print(f"\n  Analyzing: {view_name}")
        
        result = analyzer.analyze_sql(
            sql=view['definition'],
            name=view_name,
            sql_type="VIEW"
        )
        
        if result.get('parse_error'):
            print(f"    ✗ Parse error: {result['parse_error']}")
        else:
            print(f"    ✓ Source tables: {result.get('source_tables', [])}")
            print(f"    ✓ Columns: {len(result.get('column_lineage', []))}")
            
            # Show column lineage
            for col in result.get('column_lineage', [])[:3]:
                sources = [f"{s['table']}.{s['column']}" for s in col.get('source_columns', [])]
                print(f"      - {col['target_column']}: {col['transform_type']} <- {sources}")
    
    print("\n\nAnalyzing query history...")
    
    for query in SAMPLE_METADATA['query_history'][:2]:
        query_name = f"query_{query['query_text_id']}"
        print(f"\n  Analyzing: {query_name}")
        
        result = analyzer.analyze_sql(
            sql=query['query_sql_text'],
            name=query_name,
            sql_type="QUERY_HISTORY"
        )
        
        if result.get('parse_error'):
            print(f"    ✗ Parse error: {result['parse_error']}")
        else:
            print(f"    ✓ Source tables: {result.get('source_tables', [])}")
            print(f"    ✓ Columns: {len(result.get('column_lineage', []))}")
    
    print(f"\n\nAnalyzer statistics:")
    print(f"  Total analyzed: {analyzer.stats['total_analyzed']}")
    print(f"  Successful: {analyzer.stats['successful_parses']}")
    print(f"  Errors: {analyzer.stats['parse_errors']}")


def print_usage_examples():
    """Print usage examples for the metadata-based lineage analyzer."""
    
    print("\n" + "="*70)
    print("USAGE EXAMPLES")
    print("="*70)
    
    print("""
1. USING DATABASE CONNECTION (Full Analysis with LLM):
------------------------------------------------------
from metadata_lineage_main import MetadataLineageOrchestrator

orchestrator = MetadataLineageOrchestrator(
    server="your-server.database.windows.net",
    database="YourDatabase",
    username="your_username",
    password="your_password",
    driver="{ODBC Driver 18 for SQL Server}",
    output_directory="./lineage_output",
    # LLM configuration
    ollama_url="http://localhost:11434",
    ollama_model="qwen2.5-coder:14b",
    # Or use OpenAI:
    # openai_api_key="your-openai-key",
    # openai_model="gpt-4o-mini",
)

results = orchestrator.run_full_analysis()


2. USING PRE-EXTRACTED METADATA:
--------------------------------
# If you already extracted metadata using enhanced_metadata_extractor

orchestrator = MetadataLineageOrchestrator(
    server="localhost",  # Not used when metadata is preloaded
    database="MyDB",
    username="",
    password="",
    preloaded_metadata=my_metadata_dict,  # Pass metadata dictionary
    output_directory="./lineage_output",
)

results = orchestrator.run_full_analysis()


3. USING METADATA FROM FILE:
----------------------------
orchestrator = MetadataLineageOrchestrator(
    server="localhost",
    database="MyDB",
    username="",
    password="",
    metadata_file_path="./metadata_cache/enhanced_metadata_MyDB.json",
    output_directory="./lineage_output",
)

results = orchestrator.run_full_analysis()


4. COMMAND LINE USAGE:
----------------------
# With database connection:
python metadata_lineage_main.py \\
    --server your-server.database.windows.net \\
    --database YourDatabase \\
    --username your_username \\
    --password your_password \\
    --output ./lineage_output \\
    --ollama-model qwen2.5-coder:14b

# With pre-extracted metadata file:
python metadata_lineage_main.py \\
    --server localhost \\
    --database YourDatabase \\
    --username dummy \\
    --password dummy \\
    --metadata-file ./metadata_cache/enhanced_metadata_MyDB.json \\
    --output ./lineage_output


5. OUTPUT FILES GENERATED:
--------------------------
After running analysis, you'll find these files in the output directory:

- statement_lineage_*.json      - View and query history lineage
- procedure_lineage_*.json      - Legacy format for procedures/functions
- procedure_*_complete_*.json   - Complete LLM analysis results
- procedure_*_catalog_*.json    - Procedure/function catalog
- procedure_*_column_lineage_*.json - Detailed column mappings
- procedure_*_dependency_graph_*.json - For visualization
- procedure_*_tabular_components_*.json - Table usage report
- lineage_summary_*.json        - Combined summary
- enhanced_metadata_*_.json     - Cached metadata (if extracted)
""")


def main():
    """Main entry point for the example script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Example Test Script for Metadata-Based Lineage Analyzer'
    )
    parser.add_argument(
        '--mode',
        choices=['preloaded', 'file', 'tabular', 'usage', 'all'],
        default='all',
        help='Which example to run'
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("METADATA-BASED T-SQL LINEAGE ANALYZER - EXAMPLES")
    print("="*70)
    
    if args.mode in ['preloaded', 'all']:
        try:
            run_example_with_preloaded_metadata()
        except Exception as e:
            print(f"  Error: {e}")
    
    if args.mode in ['file', 'all']:
        try:
            run_example_with_metadata_file()
        except Exception as e:
            print(f"  Error: {e}")
    
    if args.mode in ['tabular', 'all']:
        try:
            demonstrate_tabular_analysis()
        except Exception as e:
            print(f"  Error: {e}")
    
    if args.mode in ['usage', 'all']:
        print_usage_examples()
    
    print("\n" + "="*70)
    print("Example execution completed!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
