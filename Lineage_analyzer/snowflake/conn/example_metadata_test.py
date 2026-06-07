"""
Example Test Script for Metadata-Based Snowflake Lineage Analyzer
Demonstrates how to use the system with database connection instead of SQL files.

This example shows:
1. How to use the MetadataLineageOrchestrator with a Snowflake connection
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
    "database": "SNOWFLAKE_SAMPLE_DATA",
    "account": "XBXMLZX-MIA01615",
    "tables": [
        {
            "schema": "PUBLIC",
            "name": "customers",
            "columns": [
                {"name": "customer_id", "data_type": "NUMBER", "is_nullable": False},
                {"name": "customer_name", "data_type": "VARCHAR", "is_nullable": True},
                {"name": "email", "data_type": "VARCHAR", "is_nullable": True},
                {"name": "created_date", "data_type": "DATE", "is_nullable": True},
                {"name": "customer_data", "data_type": "VARIANT", "is_nullable": True}
            ]
        },
        {
            "schema": "PUBLIC",
            "name": "orders",
            "columns": [
                {"name": "order_id", "data_type": "NUMBER", "is_nullable": False},
                {"name": "customer_id", "data_type": "NUMBER", "is_nullable": False},
                {"name": "order_date", "data_type": "DATE", "is_nullable": True},
                {"name": "total_amount", "data_type": "NUMBER", "is_nullable": True},
                {"name": "status", "data_type": "VARCHAR", "is_nullable": True},
                {"name": "order_details", "data_type": "VARIANT", "is_nullable": True}
            ]
        },
        {
            "schema": "PUBLIC",
            "name": "order_items",
            "columns": [
                {"name": "item_id", "data_type": "NUMBER", "is_nullable": False},
                {"name": "order_id", "data_type": "NUMBER", "is_nullable": False},
                {"name": "product_id", "data_type": "NUMBER", "is_nullable": False},
                {"name": "quantity", "data_type": "NUMBER", "is_nullable": True},
                {"name": "unit_price", "data_type": "NUMBER", "is_nullable": True}
            ]
        },
        {
            "schema": "PUBLIC",
            "name": "customer_summary",
            "columns": [
                {"name": "customer_id", "data_type": "NUMBER", "is_nullable": False},
                {"name": "total_value", "data_type": "NUMBER", "is_nullable": True},
                {"name": "tier", "data_type": "VARCHAR", "is_nullable": True},
                {"name": "total_orders", "data_type": "NUMBER", "is_nullable": True},
                {"name": "total_spent", "data_type": "NUMBER", "is_nullable": True},
                {"name": "last_processed", "data_type": "TIMESTAMP_NTZ", "is_nullable": True}
            ]
        },
        {
            "schema": "PUBLIC",
            "name": "json_events",
            "columns": [
                {"name": "event_id", "data_type": "NUMBER", "is_nullable": False},
                {"name": "event_data", "data_type": "VARIANT", "is_nullable": True},
                {"name": "created_at", "data_type": "TIMESTAMP_NTZ", "is_nullable": True}
            ]
        }
    ],
    "views": [
        {
            "schema_name": "PUBLIC",
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
FROM PUBLIC.customers c
INNER JOIN PUBLIC.orders o ON c.customer_id = o.customer_id
""",
            "create_date": "2024-01-15",
            "modify_date": "2024-06-20"
        },
        {
            "schema_name": "PUBLIC",
            "view_name": "vw_order_details",
            "definition": """
CREATE VIEW vw_order_details AS
SELECT
    o.order_id,
    o.order_date,
    SUM(oi.quantity * oi.unit_price) as calculated_total,
    COUNT(oi.item_id) as item_count
FROM PUBLIC.orders o
LEFT JOIN PUBLIC.order_items oi ON o.order_id = oi.order_id
GROUP BY o.order_id, o.order_date
""",
            "create_date": "2024-02-10",
            "modify_date": "2024-02-10"
        },
        {
            "schema_name": "PUBLIC",
            "view_name": "vw_flattened_events",
            "definition": """
CREATE VIEW vw_flattened_events AS
SELECT
    e.event_id,
    e.event_data:event_type::STRING as event_type,
    e.event_data:user_id::NUMBER as user_id,
    f.value:item_id::NUMBER as item_id,
    f.value:quantity::NUMBER as quantity
FROM PUBLIC.json_events e,
LATERAL FLATTEN(input => e.event_data:items) f
""",
            "create_date": "2024-03-01",
            "modify_date": "2024-03-01"
        }
    ],
    "procedures": [
        {
            "schema_name": "PUBLIC",
            "procedure_name": "usp_GetCustomerStats",
            "language": "SQL",
            "definition": """
CREATE OR REPLACE PROCEDURE usp_GetCustomerStats(CUSTOMER_ID NUMBER)
RETURNS TABLE (total_orders NUMBER, total_spent NUMBER)
LANGUAGE SQL
AS
$$
DECLARE
    result RESULTSET;
BEGIN
    result := (
        SELECT
            COUNT(*) as total_orders,
            SUM(total_amount) as total_spent
        FROM PUBLIC.orders
        WHERE customer_id = :CUSTOMER_ID
    );
    RETURN TABLE(result);
END;
$$
""",
            "create_date": "2024-01-20",
            "modify_date": "2024-05-15"
        },
        {
            "schema_name": "PUBLIC",
            "procedure_name": "usp_ProcessCustomerReport",
            "language": "SQL",
            "definition": """
CREATE OR REPLACE PROCEDURE usp_ProcessCustomerReport(CUSTOMER_ID NUMBER)
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    MERGE INTO PUBLIC.customer_summary cs
    USING (
        SELECT
            :CUSTOMER_ID as customer_id,
            COUNT(*) as total_orders,
            SUM(total_amount) as total_spent
        FROM PUBLIC.orders
        WHERE customer_id = :CUSTOMER_ID
    ) src
    ON cs.customer_id = src.customer_id
    WHEN MATCHED THEN UPDATE SET
        total_orders = src.total_orders,
        total_spent = src.total_spent,
        last_processed = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (customer_id, total_orders, total_spent, last_processed)
    VALUES (src.customer_id, src.total_orders, src.total_spent, CURRENT_TIMESTAMP());

    RETURN 'Success';
END;
$$
""",
            "create_date": "2024-02-01",
            "modify_date": "2024-06-01"
        },
        {
            "schema_name": "PUBLIC",
            "procedure_name": "usp_ProcessJsonEvents",
            "language": "JAVASCRIPT",
            "definition": """
CREATE OR REPLACE PROCEDURE usp_ProcessJsonEvents()
RETURNS STRING
LANGUAGE JAVASCRIPT
AS
$$
    var result = snowflake.execute({
        sqlText: `
            INSERT INTO PUBLIC.customer_summary (customer_id, total_value)
            SELECT
                event_data:user_id::NUMBER as customer_id,
                SUM(f.value:amount::NUMBER) as total_value
            FROM PUBLIC.json_events e,
            LATERAL FLATTEN(input => e.event_data:transactions) f
            GROUP BY event_data:user_id::NUMBER
        `
    });
    return 'Processed ' + result.getRowCount() + ' rows';
$$
""",
            "create_date": "2024-03-15",
            "modify_date": "2024-03-15"
        }
    ],
    "functions": [
        {
            "schema_name": "PUBLIC",
            "function_name": "fn_GetCustomerOrders",
            "function_type": "SQL_TABLE_VALUED_FUNCTION",
            "definition": """
CREATE OR REPLACE FUNCTION fn_GetCustomerOrders(CUSTOMER_ID NUMBER)
RETURNS TABLE (order_id NUMBER, order_date DATE, total_amount NUMBER, item_count NUMBER)
AS
$$
    SELECT
        o.order_id,
        o.order_date,
        o.total_amount,
        COUNT(oi.item_id) as item_count
    FROM PUBLIC.orders o
    LEFT JOIN PUBLIC.order_items oi ON o.order_id = oi.order_id
    WHERE o.customer_id = CUSTOMER_ID
    GROUP BY o.order_id, o.order_date, o.total_amount
$$
""",
            "create_date": "2024-03-01",
            "modify_date": "2024-03-01"
        },
        {
            "schema_name": "PUBLIC",
            "function_name": "fn_CalculateDiscount",
            "function_type": "SQL_SCALAR_FUNCTION",
            "definition": """
CREATE OR REPLACE FUNCTION fn_CalculateDiscount(AMOUNT NUMBER, CUSTOMER_TIER VARCHAR)
RETURNS NUMBER
AS
$$
    CASE
        WHEN CUSTOMER_TIER = 'GOLD' AND AMOUNT > 1000 THEN AMOUNT * 0.15
        WHEN CUSTOMER_TIER = 'SILVER' AND AMOUNT > 500 THEN AMOUNT * 0.10
        WHEN CUSTOMER_TIER = 'BRONZE' THEN AMOUNT * 0.05
        ELSE 0
    END
$$
""",
            "create_date": "2024-03-15",
            "modify_date": "2024-03-15"
        }
    ],
    "streams": [
        {
            "schema_name": "PUBLIC",
            "stream_name": "orders_stream",
            "source_type": "TABLE",
            "source_name": "PUBLIC.orders",
            "mode": "DEFAULT",
            "stale": False,
            "create_date": "2024-04-01"
        }
    ],
    "tasks": [
        {
            "schema_name": "PUBLIC",
            "task_name": "process_orders_task",
            "warehouse": "COMPUTE_WH",
            "schedule": "1 MINUTE",
            "predecessor": None,
            "definition": """
CREATE OR REPLACE TASK process_orders_task
    WAREHOUSE = COMPUTE_WH
    SCHEDULE = '1 MINUTE'
WHEN
    SYSTEM$STREAM_HAS_DATA('orders_stream')
AS
    MERGE INTO PUBLIC.customer_summary cs
    USING (
        SELECT customer_id, COUNT(*) as cnt, SUM(total_amount) as amt
        FROM orders_stream
        GROUP BY customer_id
    ) src
    ON cs.customer_id = src.customer_id
    WHEN MATCHED THEN UPDATE SET
        total_orders = cs.total_orders + src.cnt,
        total_spent = cs.total_spent + src.amt
""",
            "state": "SUSPENDED",
            "create_date": "2024-04-01"
        }
    ],
    "query_history": [
        {
            "query_id": "01b12345-0001-1234-0000-00012345abcd",
            "query_text": """
SELECT
    c.customer_name,
    COUNT(o.order_id) as order_count,
    SUM(o.total_amount) as total_spent
FROM PUBLIC.customers c
LEFT JOIN PUBLIC.orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_name
ORDER BY total_spent DESC
""",
            "execution_count": 1250,
            "avg_duration_ms": 45.5,
            "avg_partitions_scanned": 12,
            "last_execution_time": "2024-06-20T14:30:00Z"
        },
        {
            "query_id": "01b12345-0002-1234-0000-00012345abcd",
            "query_text": """
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    o.order_details:shipping_address:city::STRING as shipping_city,
    oi.product_id,
    oi.quantity,
    oi.unit_price,
    oi.quantity * oi.unit_price as line_total
FROM PUBLIC.orders o
INNER JOIN PUBLIC.customers c ON o.customer_id = c.customer_id
INNER JOIN PUBLIC.order_items oi ON o.order_id = oi.order_id
WHERE o.order_date >= DATEADD(month, -3, CURRENT_DATE())
""",
            "execution_count": 850,
            "avg_duration_ms": 120.8,
            "avg_partitions_scanned": 24,
            "last_execution_time": "2024-06-20T15:45:00Z"
        }
    ],
    "stages": [],
    "sequences": [],
    "summary": {
        "database": "SNOWFLAKE_SAMPLE_DATA",
        "account": "XBXMLZX-MIA01615",
        "extraction_timestamp": datetime.now().isoformat(),
        "table_count": 5,
        "view_count": 3,
        "procedure_count": 3,
        "function_count": 2,
        "stream_count": 1,
        "task_count": 1,
        "column_count": 28,
        "query_history_count": 2
    },
    "parser_support": {
        "table_disambiguation": {
            "unique_tables": {
                "customers": "PUBLIC.customers",
                "orders": "PUBLIC.orders",
                "order_items": "PUBLIC.order_items",
                "customer_summary": "PUBLIC.customer_summary",
                "json_events": "PUBLIC.json_events"
            },
            "ambiguous_tables": {},
            "schema_tables": {
                "PUBLIC": ["customers", "orders", "order_items", "customer_summary", "json_events"]
            }
        },
        "database_name": "SNOWFLAKE_SAMPLE_DATA",
        "schemas": ["PUBLIC"]
    }
}


def create_sample_metadata_file():
    """Create a temporary metadata file for testing."""
    temp_dir = tempfile.mkdtemp(prefix="snowflake_lineage_test_")
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
    print("SNOWFLAKE LINEAGE ANALYZER - PRELOADED METADATA EXAMPLE")
    print("="*70 + "\n")

    output_dir = Path(tempfile.gettempdir()) / "snowflake_lineage_output"

    # Create orchestrator with preloaded metadata
    orchestrator = MetadataLineageOrchestrator(
        # Snowflake connection params (not used when preloaded_metadata is provided)
        account="XBXMLZX-MIA01615",
        database="SNOWFLAKE_SAMPLE_DATA",
        username="VAMSI1",
        password="",
        # Output configuration
        output_directory=str(output_dir),
        dialect="snowflake",
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
    print(f"  Streams: {len(SAMPLE_METADATA['streams'])}")
    print(f"  Tasks: {len(SAMPLE_METADATA['tasks'])}")
    print(f"  Query History: {len(SAMPLE_METADATA['query_history'])}")

    print("\n   Orchestrator ready for analysis")
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
    print("SNOWFLAKE LINEAGE ANALYZER - METADATA FILE EXAMPLE")
    print("="*70 + "\n")

    # Create sample metadata file
    temp_dir, metadata_path = create_sample_metadata_file()
    output_dir = Path(tempfile.gettempdir()) / "snowflake_lineage_output_file"

    try:
        # Create orchestrator with metadata file path
        orchestrator = MetadataLineageOrchestrator(
            account="XBXMLZX-MIA01615",
            database="SNOWFLAKE_SAMPLE_DATA",
            username="",
            password="",
            output_directory=str(output_dir),
            dialect="snowflake",
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
            print(f"  Streams: {summary.get('stream_count', 0)}")
            print(f"  Tasks: {summary.get('task_count', 0)}")

        print("\n   Orchestrator ready for analysis")

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
    print("SNOWFLAKE TABULAR SQL ANALYSIS DEMONSTRATION")
    print("="*70 + "\n")

    # Import the view analyzer directly
    from metadata_view_analyzer import MetadataViewAnalyzer

    # Create analyzer with metadata context
    analyzer = MetadataViewAnalyzer(
        dialect="snowflake",
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
            print(f"      Parse error: {result['parse_error']}")
        else:
            print(f"      Source tables: {result.get('source_tables', [])}")
            print(f"      Columns: {len(result.get('column_lineage', []))}")

            # Check for Snowflake-specific features
            if result.get('has_lateral_flatten'):
                print(f"      LATERAL FLATTEN detected")
            if result.get('has_variant_access'):
                print(f"      Variant/JSON access detected")

            # Show column lineage
            for col in result.get('column_lineage', [])[:3]:
                sources = [f"{s['table']}.{s['column']}" for s in col.get('source_columns', [])]
                print(f"      - {col['target_column']}: {col['transform_type']} <- {sources}")

    print("\n\nAnalyzing query history...")

    for query in SAMPLE_METADATA['query_history'][:2]:
        query_name = f"query_{query['query_id'][:8]}"
        print(f"\n  Analyzing: {query_name}")

        result = analyzer.analyze_sql(
            sql=query['query_text'],
            name=query_name,
            sql_type="QUERY_HISTORY"
        )

        if result.get('parse_error'):
            print(f"      Parse error: {result['parse_error']}")
        else:
            print(f"      Source tables: {result.get('source_tables', [])}")
            print(f"      Columns: {len(result.get('column_lineage', []))}")

    print(f"\n\nAnalyzer statistics:")
    print(f"  Total analyzed: {analyzer.stats['total_analyzed']}")
    print(f"  Successful: {analyzer.stats['successful_parses']}")
    print(f"  Errors: {analyzer.stats['parse_errors']}")


def print_usage_examples():
    """Print usage examples for the Snowflake lineage analyzer."""

    print("\n" + "="*70)
    print("USAGE EXAMPLES")
    print("="*70)

    print("""
1. USING SNOWFLAKE CONNECTION (Full Analysis with LLM):
------------------------------------------------------
from metadata_lineage_main import MetadataLineageOrchestrator

orchestrator = MetadataLineageOrchestrator(
    account="your-account.snowflakecomputing.com",
    database="YOUR_DATABASE",
    username="your_username",
    password="your_password",
    warehouse="COMPUTE_WH",
    role="SYSADMIN",
    authenticator="externalbrowser",  # For SSO
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
    account="your-account",
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
    account="your-account",
    database="MyDB",
    username="",
    password="",
    metadata_file_path="./metadata_cache/enhanced_metadata_MyDB.json",
    output_directory="./lineage_output",
)

results = orchestrator.run_full_analysis()


4. COMMAND LINE USAGE:
----------------------
# With Snowflake connection:
python metadata_lineage_main.py \\
    --account your-account.snowflakecomputing.com \\
    --database YOUR_DATABASE \\
    --username your_username \\
    --password your_password \\
    --warehouse COMPUTE_WH \\
    --output ./lineage_output \\
    --ollama-model qwen2.5-coder:14b

# With external browser auth (SSO):
python metadata_lineage_main.py \\
    --account your-account.snowflakecomputing.com \\
    --database YOUR_DATABASE \\
    --username your_username \\
    --authenticator externalbrowser \\
    --output ./lineage_output

# With pre-extracted metadata file:
python metadata_lineage_main.py \\
    --account your-account \\
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


6. SNOWFLAKE-SPECIFIC FEATURES:
-------------------------------
The analyzer handles Snowflake-specific SQL patterns:

- Variant/JSON access: column:path::TYPE
- LATERAL FLATTEN for arrays
- Time Travel queries (AT/BEFORE)
- Streams and Tasks
- Multi-language procedures (SQL, JavaScript, Python)
- External browser authentication (SSO)
""")


def main():
    """Main entry point for the example script."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Example Test Script for Snowflake Lineage Analyzer'
    )
    parser.add_argument(
        '--mode',
        choices=['preloaded', 'file', 'tabular', 'usage', 'all'],
        default='all',
        help='Which example to run'
    )

    args = parser.parse_args()

    print("\n" + "="*70)
    print("SNOWFLAKE LINEAGE ANALYZER - EXAMPLES")
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
