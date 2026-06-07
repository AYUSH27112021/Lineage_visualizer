"""
Metadata View Analyzer for PostgreSQL
Analyzes views and query history SQL using traditional parsing (sqlglot).

This module provides analysis capabilities for views and queries
using database metadata for enhanced schema context.
"""

import re
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict

import sqlglot
from sqlglot import exp, parse_one


@dataclass
class ColumnLineage:
    """Column lineage information"""
    target_column: str
    target_table: str
    source_columns: List[Dict[str, str]] = field(default_factory=list)
    transform_type: str = "direct"
    expression: str = ""
    is_aggregate: bool = False
    is_calculated: bool = False
    cte_dependency: Optional[str] = None
    is_array_operation: bool = False
    is_jsonb_operation: bool = False


@dataclass
class ViewLineage:
    """Lineage for a view or query"""
    name: str
    sql_type: str
    target_table: Optional[str] = None
    source_tables: List[str] = field(default_factory=list)
    column_lineage: List[ColumnLineage] = field(default_factory=list)
    cte_definitions: Dict[str, Any] = field(default_factory=dict)
    temp_tables: List[str] = field(default_factory=list)
    is_dynamic: bool = False
    parse_error: Optional[str] = None
    statement_subtype: Optional[str] = None
    returning_columns: List[str] = field(default_factory=list)


class MetadataViewAnalyzer:
    """
    Analyze views and query history SQL extracted from PostgreSQL database metadata.

    Uses sqlglot for traditional parsing with full schema context from metadata.
    """

    def __init__(
        self,
        dialect: str = "postgres",
        metadata: Optional[Dict] = None,
        debug: bool = False
    ):
        """
        Initialize the analyzer.

        Args:
            dialect: SQL dialect (default: postgres)
            metadata: Database metadata for schema context
            debug: Enable debug output
        """
        self.dialect = dialect
        self.metadata = metadata or {}
        self.debug = debug

        # Build table and column lookup from metadata
        self.table_lookup = self._build_table_lookup()
        self.column_lookup = self._build_column_lookup()

        # Statistics
        self.stats = defaultdict(int)

        # Compile patterns
        self._compile_patterns()

    def _build_table_lookup(self) -> Dict[str, Dict]:
        """Build lookup dictionary for table names."""
        lookup = {}

        for table in self.metadata.get('tables', []):
            schema = table.get('schema', 'public')
            name = table.get('name')

            if name:
                # Store with multiple key variations for flexible matching
                qualified_name = f"{schema}.{name}"
                lookup[name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name}
                lookup[qualified_name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name}

        # Also include views in lookup
        for view in self.metadata.get('views', []):
            schema = view.get('schema_name', 'public')
            name = view.get('view_name')

            if name:
                qualified_name = f"{schema}.{name}"
                lookup[name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name, 'is_view': True}
                lookup[qualified_name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name, 'is_view': True}

        # Include materialized views
        for matview in self.metadata.get('materialized_views', []):
            schema = matview.get('schema_name', 'public')
            name = matview.get('matview_name')

            if name:
                qualified_name = f"{schema}.{name}"
                lookup[name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name, 'is_matview': True}
                lookup[qualified_name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name, 'is_matview': True}

        return lookup

    def _build_column_lookup(self) -> Dict[str, Set[str]]:
        """Build lookup of columns per table."""
        lookup = defaultdict(set)

        for table in self.metadata.get('tables', []):
            schema = table.get('schema', 'public')
            name = table.get('name')
            qualified_name = f"{schema}.{name}"

            for col in table.get('columns', []):
                col_name = col.get('name') or col.get('column_name')
                if col_name:
                    lookup[qualified_name.lower()].add(col_name.lower())
                    lookup[name.lower()].add(col_name.lower())

        return dict(lookup)

    def _compile_patterns(self):
        """Compile regex patterns for special detection."""
        # PostgreSQL temp tables
        self.temp_table_pattern = re.compile(r'pg_temp\.\w+', re.IGNORECASE)
        self.array_operation = re.compile(r'ARRAY\[|array_agg|unnest', re.IGNORECASE)
        self.jsonb_operation = re.compile(r'jsonb_|json_|->|->>', re.IGNORECASE)
        self.exec_dynamic = re.compile(r'EXECUTE\s+', re.IGNORECASE)

    def analyze_sql(
        self,
        sql: str,
        name: str,
        sql_type: str = "VIEW"
    ) -> Dict[str, Any]:
        """
        Analyze a SQL statement and extract lineage.

        Args:
            sql: SQL statement text
            name: Name of the view/query
            sql_type: Type of SQL (VIEW, QUERY_HISTORY, etc.)

        Returns:
            Analysis result dictionary
        """
        self.stats['total_analyzed'] += 1

        try:
            lineage = self._analyze_statement(sql, name, sql_type)

            if lineage.parse_error:
                self.stats['parse_errors'] += 1
            else:
                self.stats['successful_parses'] += 1

            return self._lineage_to_dict(lineage)

        except Exception as e:
            self.stats['parse_errors'] += 1

            return {
                'name': name,
                'type': sql_type,
                'parse_error': str(e),
                'source_tables': [],
                'column_lineage': [],
                'cte_definitions': {},
                'temp_tables': [],
                'is_dynamic': self._is_dynamic_sql(sql),
                'analysis_success': False
            }

    def _analyze_statement(
        self,
        sql: str,
        name: str,
        sql_type: str
    ) -> ViewLineage:
        """Analyze a single SQL statement."""
        try:
            # Parse with lenient error handling
            tree = parse_one(sql, dialect=self.dialect, error_level='ignore')

            if not tree:
                return ViewLineage(
                    name=name,
                    sql_type=sql_type,
                    parse_error="Failed to parse SQL"
                )

            # Determine statement type and subtype
            stmt_type = self._get_statement_type(tree)
            stmt_subtype = self._get_statement_subtype(tree, sql)

            # Extract CTEs first
            cte_definitions = self._extract_ctes(tree)

            # Extract target table (for views, this is the view name)
            if sql_type in ["VIEW", "MATERIALIZED_VIEW"]:
                target_table = name
            else:
                target_table = self._extract_target_table(tree)

            # Extract source tables
            source_tables = self._extract_source_tables(tree)

            # Build alias map for column resolution
            alias_map = self._build_alias_map(tree)

            # Extract column lineage
            column_lineage = self._extract_column_lineage(
                tree, target_table, cte_definitions, alias_map
            )

            # Extract temp tables
            temp_tables = self._extract_temp_tables(sql)

            # Check for RETURNING clause
            returning_columns = []
            if "RETURNING" in sql.upper():
                returning_match = re.search(r'RETURNING\s+(.+?)(?:;|$)', sql, re.IGNORECASE | re.DOTALL)
                if returning_match:
                    ret_clause = returning_match.group(1).strip()
                    returning_columns = [c.strip() for c in ret_clause.split(',')]

            return ViewLineage(
                name=name,
                sql_type=sql_type,
                target_table=target_table,
                source_tables=source_tables,
                column_lineage=column_lineage,
                cte_definitions=cte_definitions,
                temp_tables=temp_tables,
                is_dynamic=self._is_dynamic_sql(sql),
                statement_subtype=stmt_subtype,
                returning_columns=returning_columns
            )

        except Exception as e:
            return ViewLineage(
                name=name,
                sql_type=sql_type,
                parse_error=str(e)
            )

    def _get_statement_type(self, tree: exp.Expression) -> str:
        """Get statement type."""
        type_map = {
            exp.Create: "CREATE",
            exp.Insert: "INSERT",
            exp.Update: "UPDATE",
            exp.Delete: "DELETE",
            exp.Select: "SELECT",
            exp.Merge: "MERGE",
            exp.Drop: "DROP",
            exp.Alter: "ALTER",
        }

        for exp_type, name in type_map.items():
            if isinstance(tree, exp_type):
                return name

        return "UNKNOWN"

    def _get_statement_subtype(self, tree: exp.Expression, sql: str) -> Optional[str]:
        """Get statement subtype."""
        sql_upper = sql.upper()

        if 'ON CONFLICT' in sql_upper:
            return "UPSERT"

        if 'RETURNING' in sql_upper:
            return "WITH_RETURNING"

        if isinstance(tree, exp.Insert) and tree.expression and isinstance(tree.expression, exp.Select):
            return "INSERT_SELECT"

        if 'UNION' in sql_upper:
            return "UNION"

        if 'INTERSECT' in sql_upper:
            return "INTERSECT"

        if 'EXCEPT' in sql_upper:
            return "EXCEPT"

        if 'RECURSIVE' in sql_upper and 'WITH' in sql_upper:
            return "RECURSIVE_CTE"

        return None

    def _extract_ctes(self, tree: exp.Expression) -> Dict[str, Dict]:
        """Extract CTE definitions."""
        cte_definitions = {}

        for cte in tree.find_all(exp.CTE):
            cte_name = cte.alias_or_name
            cte_query = cte.this

            if not cte_name:
                continue

            # Extract columns from CTE
            columns = []
            if isinstance(cte_query, exp.Select):
                for projection in cte_query.expressions:
                    columns.append(projection.alias_or_name)

            # Extract source tables
            source_tables = self._extract_source_tables(cte_query)

            cte_definitions[cte_name] = {
                'columns': columns,
                'source_tables': source_tables,
                'query': cte_query.sql()[:500] if cte_query else ''
            }

        return cte_definitions

    def _extract_target_table(self, tree: exp.Expression) -> Optional[str]:
        """Extract target table name."""
        if isinstance(tree, (exp.Create, exp.Insert, exp.Update, exp.Delete, exp.Merge)):
            table_node = tree.find(exp.Table)
            if table_node:
                return self._get_full_table_name(table_node)

        return None

    def _extract_source_tables(self, tree: exp.Expression) -> List[str]:
        """Extract all source table names."""
        tables = []

        for table in tree.find_all(exp.Table):
            table_name = self._get_full_table_name(table)
            if table_name and table_name not in tables:
                tables.append(table_name)

        return tables

    def _get_full_table_name(self, table: exp.Table) -> str:
        """Get fully qualified table name."""
        parts = []
        if table.catalog:
            parts.append(str(table.catalog))
        if table.db:
            parts.append(str(table.db))
        parts.append(table.name)
        return '.'.join(parts)

    def _build_alias_map(self, tree: exp.Expression) -> Dict[str, str]:
        """Build mapping of aliases to table names."""
        alias_map = {}

        for table in tree.find_all(exp.Table):
            if table.alias:
                alias_map[table.alias] = self._get_full_table_name(table)

        for subq in tree.find_all(exp.Subquery):
            if subq.alias:
                alias_map[subq.alias] = "subquery"

        return alias_map

    def _extract_column_lineage(
        self,
        tree: exp.Expression,
        target_table: Optional[str],
        cte_definitions: Dict,
        alias_map: Dict
    ) -> List[ColumnLineage]:
        """Extract column lineage from the parse tree."""
        column_lineage = []

        # Find SELECT expressions
        select = tree.find(exp.Select)
        if not select:
            return column_lineage

        for projection in select.expressions:
            output_col = projection.alias_or_name
            source_cols = self._find_source_columns(projection, cte_definitions, alias_map)
            transform_type = self._classify_transform(projection)

            column_lineage.append(ColumnLineage(
                target_column=output_col,
                target_table=target_table or "result_set",
                source_columns=source_cols,
                transform_type=transform_type,
                expression=projection.sql()[:200],
                is_aggregate=self._is_aggregate(projection),
                is_calculated=self._is_calculated(projection),
                is_array_operation=bool(self.array_operation.search(projection.sql())),
                is_jsonb_operation=bool(self.jsonb_operation.search(projection.sql()))
            ))

        return column_lineage

    def _find_source_columns(
        self,
        expression: exp.Expression,
        cte_definitions: Dict,
        alias_map: Dict
    ) -> List[Dict[str, str]]:
        """Find source columns from an expression."""
        source_cols = []

        for col in expression.find_all(exp.Column):
            table_ref = col.table or "unknown"

            # Resolve alias
            if table_ref in alias_map:
                table_ref = alias_map[table_ref]

            # Check if it's from a CTE
            cte_name = None
            if table_ref in cte_definitions:
                cte_name = table_ref

            source_cols.append({
                'table': table_ref,
                'column': col.name,
                'cte': cte_name
            })

        return source_cols

    def _classify_transform(self, expression: exp.Expression) -> str:
        """Classify the type of transformation."""
        sql = expression.sql()

        if self._is_aggregate(expression):
            return "aggregate"
        if "CASE" in sql.upper():
            return "case_statement"
        if "::" in sql or "CAST(" in sql.upper():
            return "cast"
        if self.array_operation.search(sql):
            return "array_operation"
        if self.jsonb_operation.search(sql):
            return "jsonb_operation"
        if "OVER" in sql.upper():
            return "window_function"
        if any(op in sql for op in ['+', '-', '*', '/', '||']):
            return "calculation"
        if isinstance(expression, exp.Column):
            return "direct"

        return "expression"

    def _is_aggregate(self, expression: exp.Expression) -> bool:
        """Check if expression contains aggregates."""
        agg_functions = {'SUM', 'COUNT', 'AVG', 'MIN', 'MAX', 'ARRAY_AGG', 'STRING_AGG', 'JSONB_AGG'}
        sql_upper = expression.sql().upper()
        return any(func in sql_upper for func in agg_functions)

    def _is_calculated(self, expression: exp.Expression) -> bool:
        """Check if expression is calculated."""
        return any(isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod))
                  for node in expression.walk())

    def _extract_temp_tables(self, sql: str) -> List[str]:
        """Extract temporary table names from SQL."""
        temp_tables = []

        # PostgreSQL temp tables (pg_temp schema)
        for match in self.temp_table_pattern.finditer(sql):
            table_name = match.group(0)
            if table_name not in temp_tables:
                temp_tables.append(table_name)

        return temp_tables

    def _is_dynamic_sql(self, sql: str) -> bool:
        """Check if SQL is dynamic."""
        return bool(self.exec_dynamic.search(sql))

    def _lineage_to_dict(self, lineage: ViewLineage) -> Dict[str, Any]:
        """Convert ViewLineage to dictionary format."""
        return {
            'name': lineage.name,
            'type': lineage.sql_type,
            'target_table': lineage.target_table,
            'source_tables': lineage.source_tables,
            'column_lineage': [
                {
                    'target_column': cl.target_column,
                    'target_table': cl.target_table,
                    'source_columns': cl.source_columns,
                    'transform_type': cl.transform_type,
                    'expression': cl.expression,
                    'is_aggregate': cl.is_aggregate,
                    'is_calculated': cl.is_calculated,
                    'is_array_operation': cl.is_array_operation,
                    'is_jsonb_operation': cl.is_jsonb_operation,
                    'cte_dependency': cl.cte_dependency
                }
                for cl in lineage.column_lineage
            ],
            'cte_definitions': lineage.cte_definitions,
            'temp_tables': lineage.temp_tables,
            'is_dynamic': lineage.is_dynamic,
            'parse_error': lineage.parse_error,
            'statement_subtype': lineage.statement_subtype,
            'returning_columns': lineage.returning_columns,
            'analysis_success': lineage.parse_error is None
        }

    def get_statistics(self) -> Dict[str, int]:
        """Get analysis statistics."""
        return dict(self.stats)

    def print_statistics(self):
        """Print analysis statistics."""
        print("\nMetadata View Analyzer Statistics:")
        print(f"  Total analyzed: {self.stats['total_analyzed']}")
        print(f"  Successful parses: {self.stats['successful_parses']}")
        print(f"  Parse errors: {self.stats['parse_errors']}")
        if self.stats['total_analyzed'] > 0:
            success_rate = (self.stats['successful_parses'] / self.stats['total_analyzed']) * 100
            print(f"  Success rate: {success_rate:.1f}%")


__all__ = ['MetadataViewAnalyzer', 'ViewLineage', 'ColumnLineage']
