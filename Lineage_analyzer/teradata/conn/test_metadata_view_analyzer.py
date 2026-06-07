"""
Test script for MetadataViewAnalyzer

This script tests the Teradata Metadata View Analyzer with various SQL patterns.
Run this after ensuring sqlglot is installed: pip install sqlglot
"""

# Conditional import to avoid errors if sqlglot is not installed
try:
    from metadata_view_analyzer import MetadataViewAnalyzer
    import json
    SQLGLOT_AVAILABLE = True
except ImportError as e:
    print(f"Warning: {e}")
    print("Please install sqlglot: pip install sqlglot")
    SQLGLOT_AVAILABLE = False


def test_basic_view():
    """Test basic view analysis"""
    print("\n" + "=" * 60)
    print("Test 1: Basic View with JOIN")
    print("=" * 60)

    analyzer = MetadataViewAnalyzer(debug=False)

    sql = """
    CREATE VIEW vw_customer_orders AS
    SELECT
        c.customer_id,
        c.customer_name,
        COUNT(o.order_id) as order_count,
        SUM(o.total_amount) as total_spent
    FROM customers c
    LEFT JOIN orders o ON c.customer_id = o.customer_id
    GROUP BY c.customer_id, c.customer_name
    """

    result = analyzer.analyze_sql(sql, "vw_customer_orders", "VIEW")

    print(f"View Name: {result['name']}")
    print(f"Parse Success: {result['analysis_success']}")
    print(f"Source Tables: {result['source_tables']}")
    print(f"Number of Columns: {len(result['column_lineage'])}")

    for col in result['column_lineage']:
        print(f"  - {col['target_column']}: {col['transform_type']}")


def test_teradata_features():
    """Test Teradata-specific features"""
    print("\n" + "=" * 60)
    print("Test 2: Teradata-Specific Features")
    print("=" * 60)

    analyzer = MetadataViewAnalyzer(debug=False)

    sql = """
    CREATE VIEW vw_recent_customers AS
    SELECT TOP 100
        c.customer_id,
        TRIM(c.customer_name) as customer_name,
        ZEROIFNULL(c.total_purchases) as total_purchases,
        ROW_NUMBER() OVER (PARTITION BY c.region ORDER BY c.signup_date DESC) as rn
    FROM customers c, regions r
    WHERE c.region_id = r.region_id(+)
    AND c.active_flag = 'Y'
    QUALIFY rn <= 10
    SAMPLE 1000
    """

    result = analyzer.analyze_sql(sql, "vw_recent_customers", "VIEW")

    print(f"View Name: {result['name']}")
    print(f"Parse Success: {result['analysis_success']}")
    print(f"Source Tables: {result['source_tables']}")
    print(f"\nTeradata Features: {result['teradata_features']}")
    print(f"Has QUALIFY: {result.get('has_qualify', False)}")
    print(f"Has SAMPLE: {result.get('has_sample', False)}")
    print(f"Has TD Outer Join: {result.get('has_td_outer_join', False)}")
    print(f"Has TD Functions: {result.get('has_td_functions', False)}")
    print(f"Has TOP N: {result.get('has_top_n', False)}")


def test_cte():
    """Test CTE extraction"""
    print("\n" + "=" * 60)
    print("Test 3: Common Table Expressions (CTE)")
    print("=" * 60)

    analyzer = MetadataViewAnalyzer(debug=False)

    sql = """
    CREATE VIEW vw_customer_summary AS
    WITH recent_orders AS (
        SELECT
            customer_id,
            order_id,
            order_date,
            total_amount
        FROM orders
        WHERE order_date >= CURRENT_DATE - 30
    ),
    customer_totals AS (
        SELECT
            customer_id,
            COUNT(*) as order_count,
            SUM(total_amount) as total_spent
        FROM recent_orders
        GROUP BY customer_id
    )
    SELECT
        c.customer_id,
        c.customer_name,
        ct.order_count,
        ct.total_spent
    FROM customers c
    INNER JOIN customer_totals ct ON c.customer_id = ct.customer_id
    """

    result = analyzer.analyze_sql(sql, "vw_customer_summary", "VIEW")

    print(f"View Name: {result['name']}")
    print(f"Parse Success: {result['analysis_success']}")
    print(f"Source Tables: {result['source_tables']}")
    print(f"\nCTE Definitions:")
    for cte_name, cte_info in result['cte_definitions'].items():
        print(f"  - {cte_name}:")
        print(f"    Columns: {cte_info['columns']}")
        print(f"    Sources: {cte_info['source_tables']}")


def test_volatile_table():
    """Test volatile table detection"""
    print("\n" + "=" * 60)
    print("Test 4: Volatile Table Detection")
    print("=" * 60)

    analyzer = MetadataViewAnalyzer(debug=False)

    sql = """
    CREATE VOLATILE TABLE temp_calc AS (
        SELECT
            customer_id,
            SUM(order_amount) as total
        FROM orders
        GROUP BY customer_id
    ) WITH DATA ON COMMIT PRESERVE ROWS;

    SELECT
        c.customer_name,
        t.total
    FROM customers c
    INNER JOIN temp_calc t ON c.customer_id = t.customer_id
    """

    result = analyzer.analyze_sql(sql, "customer_with_calc", "QUERY")

    print(f"Query Name: {result['name']}")
    print(f"Parse Success: {result['analysis_success']}")
    print(f"Volatile Tables: {result['volatile_tables']}")


def test_multiple_views():
    """Test multiple view analysis with dependency graph"""
    print("\n" + "=" * 60)
    print("Test 5: Multiple Views with Dependencies")
    print("=" * 60)

    analyzer = MetadataViewAnalyzer(debug=False)

    views = [
        {
            'view_name': 'vw_base_customers',
            'view_definition': """
                CREATE VIEW vw_base_customers AS
                SELECT customer_id, customer_name, region_id
                FROM customers
                WHERE active_flag = 'Y'
            """
        },
        {
            'view_name': 'vw_customer_regions',
            'view_definition': """
                CREATE VIEW vw_customer_regions AS
                SELECT
                    c.customer_id,
                    c.customer_name,
                    r.region_name
                FROM vw_base_customers c
                INNER JOIN regions r ON c.region_id = r.region_id
            """
        },
        {
            'view_name': 'vw_customer_orders',
            'view_definition': """
                CREATE VIEW vw_customer_orders AS
                SELECT
                    cr.customer_id,
                    cr.customer_name,
                    cr.region_name,
                    COUNT(o.order_id) as order_count
                FROM vw_customer_regions cr
                LEFT JOIN orders o ON cr.customer_id = o.customer_id
                GROUP BY cr.customer_id, cr.customer_name, cr.region_name
            """
        }
    ]

    results = analyzer.analyze_views(views)

    print(f"Total Views Analyzed: {results['statistics']['total_analyzed']}")
    print(f"Successful Parses: {results['statistics']['successful_parses']}")

    print("\nDependency Graph:")
    dep_graph = results['dependency_graph']
    print(f"Total Views: {dep_graph['total_views']}")
    print(f"Max Dependency Level: {dep_graph['max_level']}")
    print(f"Has Cycles: {dep_graph['has_cycle']}")
    print(f"View Order: {dep_graph['sorted_views']}")

    print("\nView Details:")
    for view_name in dep_graph['sorted_views']:
        view_node = dep_graph['graph'][view_name]
        print(f"  {view_name}:")
        print(f"    Level: {view_node['level']}")
        print(f"    Dependencies: {view_node['dependencies']}")
        print(f"    Dependents: {view_node['dependents']}")


def test_statistics():
    """Test statistics gathering"""
    print("\n" + "=" * 60)
    print("Test 6: Statistics")
    print("=" * 60)

    analyzer = MetadataViewAnalyzer(debug=False)

    # Analyze multiple queries
    test_queries = [
        ("view1", "SELECT * FROM customers"),
        ("view2", "SELECT * FROM orders WHERE 1=1"),
        ("view3", "SELECT c.*, o.* FROM customers c JOIN orders o ON c.id = o.customer_id"),
    ]

    for name, sql in test_queries:
        analyzer.analyze_sql(sql, name, "VIEW")

    stats = analyzer.get_statistics()

    print("Analysis Statistics:")
    print(f"  Total Analyzed: {stats['total_analyzed']}")
    print(f"  Successful Parses: {stats['successful_parses']}")
    print(f"  Parse Errors: {stats['parse_errors']}")
    print(f"  Success Rate: {stats['success_rate']:.2%}")
    print(f"  Volatile Tables Found: {stats['volatile_tables_found']}")
    print(f"  Temp Tables Found: {stats['temp_tables_found']}")


def run_all_tests():
    """Run all tests"""
    if not SQLGLOT_AVAILABLE:
        print("\nCannot run tests without sqlglot installed.")
        print("Install it with: pip install sqlglot")
        return

    print("\n" + "=" * 60)
    print("TERADATA METADATA VIEW ANALYZER - TEST SUITE")
    print("=" * 60)

    try:
        test_basic_view()
        test_teradata_features()
        test_cte()
        test_volatile_table()
        test_multiple_views()
        test_statistics()

        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 60)

    except Exception as e:
        print(f"\n\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    run_all_tests()
