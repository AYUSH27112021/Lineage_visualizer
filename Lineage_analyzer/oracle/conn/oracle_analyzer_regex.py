"""
Regex-based fallback methods for Oracle analyzer
Handles Oracle-specific edge cases that sqlglot cannot parse
"""
import re
from typing import List
from .oracle_analyzer import StatementLineage, ColumnLineage


def analyze_with_regex(sql: str, file_path: str, oracle_features: List[str]) -> StatementLineage:
    """
    Comprehensive regex-based analyzer for Oracle SQL edge cases.
    Handles: INSERT ALL, MERGE, PIVOT/UNPIVOT, Materialized Views, etc.
    """
    lineage = StatementLineage(
        file_path=file_path,
        statement_type="UNKNOWN",
        oracle_features=oracle_features
    )

    sql_upper = sql.upper()

    # 1. CREATE MATERIALIZED VIEW
    if 'CREATE' in sql_upper and 'MATERIALIZED' in sql_upper and 'VIEW' in sql_upper:
        lineage.statement_type = "CREATE"
        lineage.statement_subtype = "CREATE_MATERIALIZED_VIEW"
        mview_match = re.search(r'CREATE\s+MATERIALIZED\s+VIEW\s+([\w\.]+)', sql, re.IGNORECASE)
        if mview_match:
            lineage.target_table = mview_match.group(1)
        extract_view_columns(sql, lineage)

    # 2. CREATE VIEW
    elif 'CREATE' in sql_upper and 'VIEW' in sql_upper:
        lineage.statement_type = "CREATE"
        lineage.statement_subtype = "CREATE_VIEW"
        view_match = re.search(r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([\w\.\"]+)', sql, re.IGNORECASE)
        if view_match:
            lineage.target_table = view_match.group(1).strip('"')
        extract_view_columns(sql, lineage)

    # 3. CREATE TABLE (including Global Temporary)
    elif 'CREATE' in sql_upper and 'TABLE' in sql_upper:
        lineage.statement_type = "CREATE"
        if 'GLOBAL' in sql_upper and 'TEMPORARY' in sql_upper:
            lineage.statement_subtype = "CREATE_GLOBAL_TEMP_TABLE"
            if lineage.target_table:
                lineage.global_temp_tables.append(lineage.target_table)
        else:
            lineage.statement_subtype = "CREATE_TABLE"

        table_match = re.search(r'CREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+([\w\.\"]+)', sql, re.IGNORECASE)
        if table_match:
            lineage.target_table = table_match.group(1).strip('"')

        # Check for CREATE TABLE AS SELECT (CTAS)
        if ' AS ' in sql_upper and 'SELECT' in sql_upper:
            lineage.statement_subtype = "CREATE_TABLE_AS_SELECT"
            extract_select_sources(sql, lineage)

    # 4. INSERT ALL (Multi-table insert)
    elif sql_upper.strip().startswith('INSERT') and 'ALL' in sql_upper:
        lineage.statement_type = "INSERT"
        lineage.statement_subtype = "INSERT_ALL"

        # Extract target tables from INTO clauses
        into_tables = re.findall(r'INTO\s+([\w\.]+)', sql, re.IGNORECASE)
        lineage.target_table = into_tables[0] if into_tables else None

        # Extract source tables from the SELECT at the end
        extract_select_sources(sql, lineage)

    # 5. MERGE statement
    elif sql_upper.strip().startswith('MERGE'):
        lineage.statement_type = "MERGE"

        # Extract target table
        merge_match = re.search(r'MERGE\s+INTO\s+([\w\.]+)', sql, re.IGNORECASE)
        if merge_match:
            lineage.target_table = merge_match.group(1)

        # Extract source table from USING clause
        using_match = re.search(r'USING\s+(?:\()?(?:SELECT.*?FROM\s+)?([\w\.]+)', sql, re.IGNORECASE | re.DOTALL)
        if using_match:
            lineage.source_tables.append(using_match.group(1))

        extract_select_sources(sql, lineage)

    # 6. INSERT INTO ... SELECT
    elif sql_upper.strip().startswith('INSERT'):
        lineage.statement_type = "INSERT"

        # Extract target table
        insert_match = re.search(r'INSERT\s+INTO\s+([\w\.]+)', sql, re.IGNORECASE)
        if insert_match:
            lineage.target_table = insert_match.group(1)

        # Check if it's INSERT...SELECT
        if 'SELECT' in sql_upper:
            lineage.statement_subtype = "INSERT_SELECT"
            extract_select_sources(sql, lineage)

    # 7. UPDATE statement
    elif sql_upper.strip().startswith('UPDATE'):
        lineage.statement_type = "UPDATE"

        # Extract target table
        update_match = re.search(r'UPDATE\s+([\w\.]+)', sql, re.IGNORECASE)
        if update_match:
            lineage.target_table = update_match.group(1)

        # Extract source tables from subqueries or joins
        extract_select_sources(sql, lineage)

    # 8. DELETE statement
    elif sql_upper.strip().startswith('DELETE'):
        lineage.statement_type = "DELETE"

        # Extract target table
        delete_match = re.search(r'DELETE\s+FROM\s+([\w\.]+)', sql, re.IGNORECASE)
        if delete_match:
            lineage.target_table = delete_match.group(1)

    # 9. SELECT statement
    elif sql_upper.strip().startswith('SELECT'):
        lineage.statement_type = "SELECT"
        extract_select_sources(sql, lineage)

    # Extract all source tables if not already done
    if not lineage.source_tables:
        extract_select_sources(sql, lineage)

    return lineage


def extract_view_columns(sql: str, lineage: StatementLineage):
    """Extract column lineage for CREATE VIEW statements"""
    if not lineage.target_table:
        return

    # Extract columns from SELECT clause
    select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return

    select_clause = select_match.group(1)

    # Handle DISTINCT
    select_clause = re.sub(r'^\s*DISTINCT\s+', '', select_clause, flags=re.IGNORECASE)

    columns = split_select_columns(select_clause)

    for idx, col_expr in enumerate(columns):
        col_expr = col_expr.strip()
        if not col_expr:
            continue

        # Extract alias (AS "alias" or AS alias or just alias at end)
        alias_match = re.search(r'(?:AS\s+)?(?:\"([\w]+)\"|\'([\w]+)\'|([\w]+))\s*$', col_expr, re.IGNORECASE)
        if alias_match:
            target_col = (alias_match.group(1) or alias_match.group(2) or alias_match.group(3)).strip()
            # Remove alias from expression
            col_expr_clean = re.sub(r'(?:AS\s+)?(?:\"[\w]+\"|\'[\w]+\'|[\w]+)\s*$', '', col_expr, flags=re.IGNORECASE).strip()
        else:
            # Try to extract column name from expression like "table.column"
            simple_col = re.search(r'([\w]+)\.([\w]+)$', col_expr)
            if simple_col:
                target_col = simple_col.group(2)
            else:
                target_col = f"column_{idx}"
            col_expr_clean = col_expr

        # Extract source column/table references
        source_refs = re.findall(r'([\w]+)\.([\w]+)', col_expr_clean)

        col_lineage = ColumnLineage(
            target_column=target_col,
            target_table=lineage.target_table,
            expression=col_expr.strip()
        )

        for table_ref, col_ref in source_refs:
            col_lineage.source_columns.append({
                'table': table_ref,
                'column': col_ref
            })

        # Detect transformations
        if re.search(r'\b(COUNT|SUM|AVG|MAX|MIN|STDDEV|VARIANCE)\s*\(', col_expr_clean, re.IGNORECASE):
            col_lineage.is_aggregate = True
            col_lineage.transform_type = "aggregation"
        elif any(op in col_expr_clean for op in ['+', '-', '*', '/', '||']):
            col_lineage.is_calculated = True
            col_lineage.transform_type = "calculation"
        elif re.search(r'\b(CASE|DECODE|NVL|NVL2|COALESCE)\b', col_expr_clean, re.IGNORECASE):
            col_lineage.is_calculated = True
            col_lineage.transform_type = "conditional"
        elif re.search(r'\b(CAST|TO_CHAR|TO_NUMBER|TO_DATE)\s*\(', col_expr_clean, re.IGNORECASE):
            col_lineage.transform_type = "type_conversion"
        else:
            col_lineage.transform_type = "direct"

        lineage.column_lineage.append(col_lineage)


def split_select_columns(select_clause: str) -> List[str]:
    """Split SELECT columns by comma, respecting parentheses and strings"""
    columns = []
    current = []
    paren_depth = 0
    in_string = False
    string_char = None

    for char in select_clause:
        if char in ("'", '"') and not in_string:
            in_string = True
            string_char = char
        elif in_string and char == string_char:
            in_string = False
            string_char = None

        if not in_string:
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif char == ',' and paren_depth == 0:
                columns.append(''.join(current))
                current = []
                continue

        current.append(char)

    if current:
        columns.append(''.join(current))

    return columns


def extract_select_sources(sql: str, lineage: StatementLineage):
    """Extract source tables from SELECT, FROM, JOIN clauses"""
    # Extract tables from FROM clause
    from_tables = re.findall(r'\bFROM\s+([\w\.]+)', sql, re.IGNORECASE)

    # Extract tables from JOIN clauses (all types)
    join_tables = re.findall(
        r'\b(?:INNER\s+|LEFT\s+OUTER\s+|RIGHT\s+OUTER\s+|FULL\s+OUTER\s+|LEFT\s+|RIGHT\s+|CROSS\s+)?JOIN\s+([\w\.]+)',
        sql,
        re.IGNORECASE
    )

    # Extract tables from subqueries in FROM clause
    subquery_tables = re.findall(r'\bFROM\s+\(.*?FROM\s+([\w\.]+)', sql, re.IGNORECASE | re.DOTALL)

    # Combine all sources
    all_sources = from_tables + join_tables + subquery_tables

    # Filter and deduplicate
    for table in all_sources:
        if table and table not in lineage.source_tables:
            # Skip if it looks like a simple alias
            if '.' in table or not table.isupper() or len(table) > 1:
                lineage.source_tables.append(table)
