"""
Metadata View Analyzer
Analyzes views and query history SQL using traditional parsing (sqlglot).

This module provides the same analysis capabilities as EnhancedSQLAnalyzer
but optimized for working with database metadata instead of SQL files.
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


class MetadataViewAnalyzer:
    """
    Analyze views and query history SQL extracted from database metadata.
    
    Uses sqlglot for traditional parsing with full schema context from metadata.
    """
    
    def __init__(
        self,
        dialect: str = "tsql",
        metadata: Optional[Dict] = None,
        debug: bool = False
    ):
        """
        Initialize the analyzer.
        
        Args:
            dialect: SQL dialect (default: tsql)
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
            schema = table.get('schema', 'dbo')
            name = table.get('name')
            
            if name:
                # Store with multiple key variations for flexible matching
                qualified_name = f"{schema}.{name}"
                lookup[name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name}
                lookup[qualified_name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name}
                lookup[f"[{schema}].[{name}]".lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name}
        
        # Also include views in lookup
        for view in self.metadata.get('views', []):
            schema = view.get('schema_name', 'dbo')
            name = view.get('view_name')
            
            if name:
                qualified_name = f"{schema}.{name}"
                lookup[name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name, 'is_view': True}
                lookup[qualified_name.lower()] = {'schema': schema, 'name': name, 'qualified': qualified_name, 'is_view': True}
        
        return lookup
    
    def _build_column_lookup(self) -> Dict[str, Set[str]]:
        """Build lookup of columns per table."""
        lookup = defaultdict(set)
        
        for table in self.metadata.get('tables', []):
            schema = table.get('schema', 'dbo')
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
        self.temp_table_pattern = re.compile(r'#[\w]+')
        self.table_variable_pattern = re.compile(r'@[\w]+')
        self.exec_dynamic = re.compile(r'EXEC(?:UTE)?\s*\(', re.IGNORECASE)
        self.sp_executesql = re.compile(r'sp_executesql\s+', re.IGNORECASE)
    
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
                'is_dynamic': self._is_dynamic_sql(sql)
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
            if sql_type == "VIEW":
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
            
            return ViewLineage(
                name=name,
                sql_type=sql_type,
                target_table=target_table,
                source_tables=source_tables,
                column_lineage=column_lineage,
                cte_definitions=cte_definitions,
                temp_tables=temp_tables,
                is_dynamic=self._is_dynamic_sql(sql),
                statement_subtype=stmt_subtype
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
        
        if 'SELECT' in sql_upper and 'INTO' in sql_upper:
            return "SELECT_INTO"
        
        if isinstance(tree, exp.Insert) and tree.expression and isinstance(tree.expression, exp.Select):
            return "INSERT_SELECT"
        
        if 'UNION' in sql_upper:
            return "UNION"
        
        if 'INTERSECT' in sql_upper:
            return "INTERSECT"
        
        if 'EXCEPT' in sql_upper:
            return "EXCEPT"
        
        return None
    
    def _extract_ctes(self, tree: exp.Expression) -> Dict[str, Dict]:
        """Extract CTE definitions."""
        cte_definitions = {}
        
        for cte in tree.find_all(exp.CTE):
            cte_name = cte.alias
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
                'query': cte_query.sql()[:500]
            }
        
        return cte_definitions
    
    def _extract_target_table(self, tree: exp.Expression) -> Optional[str]:
        """Extract target table."""
        if isinstance(tree, (exp.Create, exp.Insert, exp.Update, exp.Delete, exp.Merge)):
            table_node = tree.find(exp.Table)
            if table_node:
                return self._get_full_table_name(table_node)
        
        return None
    
    def _get_full_table_name(self, table: exp.Table) -> str:
        """Get fully qualified table name."""
        parts = []
        if table.catalog:
            parts.append(str(table.catalog).strip('[]'))
        if table.db:
            parts.append(str(table.db).strip('[]'))
        parts.append(str(table.name).strip('[]'))
        
        raw_name = '.'.join(parts)
        
        # Try to resolve to qualified name using metadata
        resolved = self.table_lookup.get(raw_name.lower())
        if resolved:
            return resolved['qualified']
        
        return raw_name
    
    def _extract_source_tables(self, tree: exp.Expression) -> List[str]:
        """Extract all source tables."""
        tables = []
        
        for table_node in tree.find_all(exp.Table):
            table_name = self._get_full_table_name(table_node)
            
            # Skip target tables for DML statements
            if isinstance(tree, (exp.Insert, exp.Update, exp.Delete, exp.Merge)):
                target = tree.find(exp.Table)
                if target and self._get_full_table_name(target) == table_name:
                    continue
            
            if table_name not in tables:
                tables.append(table_name)
        
        # Get table-valued functions
        for func in tree.find_all(exp.TableAlias):
            if func.this and isinstance(func.this, exp.Func):
                func_name = f"FUNCTION:{func.this.name}"
                if func_name not in tables:
                    tables.append(func_name)
        
        return tables
    
    def _build_alias_map(self, tree: exp.Expression) -> Dict[str, str]:
        """Build mapping from table aliases to qualified names."""
        alias_map = {}
        
        for table_node in tree.find_all(exp.Table):
            base_name = self._get_full_table_name(table_node)
            alias_expr = table_node.args.get('alias')
            
            try:
                alias_name = alias_expr and getattr(alias_expr, 'name', None)
            except Exception:
                alias_name = None
            
            if alias_name:
                alias_map[str(alias_name)] = base_name
        
        return alias_map
    
    def _extract_column_lineage(
        self,
        tree: exp.Expression,
        target_table: Optional[str],
        cte_definitions: Dict,
        alias_map: Dict[str, str]
    ) -> List[ColumnLineage]:
        """Extract column-level lineage."""
        column_lineage = []
        
        # Find the SELECT statement(s)
        select = None
        
        if isinstance(tree, exp.Select):
            select = tree
        elif isinstance(tree, exp.Create):
            select = tree.find(exp.Select)
        elif isinstance(tree, exp.Insert):
            select = tree.expression if isinstance(tree.expression, exp.Select) else None
        
        if not select:
            return column_lineage
        
        for i, projection in enumerate(select.expressions):
            output_col = projection.alias_or_name or f"column_{i}"
            
            # Find source columns
            source_cols = self._find_source_columns(projection, cte_definitions, alias_map)
            
            # Classify transformation
            transform_type = self._classify_transform(projection)
            
            column_lineage.append(ColumnLineage(
                target_column=output_col,
                target_table=target_table or "derived",
                source_columns=source_cols,
                transform_type=transform_type,
                expression=projection.sql()[:200],
                is_aggregate=self._is_aggregate(projection),
                is_calculated=self._is_calculated(projection)
            ))
        
        return column_lineage
    
    def _find_source_columns(
        self,
        expr: exp.Expression,
        cte_definitions: Dict,
        alias_map: Dict[str, str]
    ) -> List[Dict[str, str]]:
        """Find all source columns in an expression."""
        sources = []
        
        for col in expr.find_all(exp.Column):
            table = str(col.table) if col.table else "unknown"
            column = str(col.name)
            
            # Check if table is a CTE
            cte_ref = None
            if table in cte_definitions:
                cte_ref = table
                table = f"CTE:{table}"
            elif table in alias_map:
                table = alias_map[table]
            
            sources.append({
                "table": table,
                "column": column,
                "cte_reference": cte_ref
            })
        
        return sources
    
    def _classify_transform(self, expr: exp.Expression) -> str:
        """Classify transformation type."""
        if isinstance(expr, exp.Column):
            return "direct"
        elif expr.find(exp.AggFunc):
            return "aggregate"
        elif expr.find(exp.Case):
            return "case"
        elif any(expr.find_all(t) for t in [exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod]):
            return "arithmetic"
        elif expr.find(exp.Cast):
            return "cast"
        elif expr.find(exp.Coalesce):
            return "coalesce"
        elif expr.find(exp.Concat):
            return "concat"
        elif expr.find(exp.Substring):
            return "substring"
        elif expr.find(exp.Func):
            return "function"
        elif expr.find(exp.Subquery):
            return "subquery"
        return "expression"
    
    def _is_aggregate(self, expr: exp.Expression) -> bool:
        """Check if expression contains aggregates."""
        agg_funcs = [exp.Sum, exp.Count, exp.Avg, exp.Max, exp.Min, exp.AggFunc]
        return any(expr.find(agg) for agg in agg_funcs)
    
    def _is_calculated(self, expr: exp.Expression) -> bool:
        """Check if expression is calculated."""
        return not isinstance(expr, exp.Column)
    
    def _is_dynamic_sql(self, sql: str) -> bool:
        """Check if SQL is dynamic."""
        return bool(self.exec_dynamic.search(sql) or self.sp_executesql.search(sql))
    
    def _extract_temp_tables(self, sql: str) -> List[str]:
        """Extract temp table references."""
        temp_tables = []
        
        for match in self.temp_table_pattern.finditer(sql):
            temp_tables.append(match.group(0))
        
        return list(set(temp_tables))
    
    def _lineage_to_dict(self, lineage: ViewLineage) -> Dict[str, Any]:
        """Convert ViewLineage to dictionary."""
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
                    'cte_dependency': cl.cte_dependency
                }
                for cl in lineage.column_lineage
            ],
            'cte_definitions': lineage.cte_definitions,
            'temp_tables': lineage.temp_tables,
            'is_dynamic': lineage.is_dynamic,
            'parse_error': lineage.parse_error,
            'statement_subtype': lineage.statement_subtype,
            'analysis_success': lineage.parse_error is None
        }


if __name__ == "__main__":
    analyzer = MetadataViewAnalyzer(debug=True)
    
    test_sql = """
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
    
    result = analyzer.analyze_sql(test_sql, "vw_customer_orders", "VIEW")
    
    import json
    print(json.dumps(result, indent=2))
