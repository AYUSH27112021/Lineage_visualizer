"""
Enhanced PostgreSQL Statement Analyzer
Handles all PostgreSQL patterns including CTEs, UPSERT, RETURNING, arrays, JSONB, etc.
"""

import sqlglot
from sqlglot import exp, parse_one
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import re


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
class StatementLineage:
    """Lineage for a single statement"""
    file_path: str
    statement_type: str
    target_table: Optional[str] = None
    source_tables: List[str] = field(default_factory=list)
    column_lineage: List[ColumnLineage] = field(default_factory=list)
    cte_definitions: Dict[str, Any] = field(default_factory=dict)
    temp_tables: List[str] = field(default_factory=list)
    is_dynamic: bool = False
    parse_error: Optional[str] = None
    statement_subtype: Optional[str] = None
    returning_columns: List[str] = field(default_factory=list)


class PostgreSQLAnalyzer:
    """Analyze PostgreSQL statements and extract comprehensive lineage"""
    
    def __init__(self, dialect: str = "postgres", debug: bool = False):
        self.dialect = dialect
        self.debug = debug
        self.stats = defaultdict(int)
        
        # Track CTEs and temp tables across batches
        self.cte_registry: Dict[str, Dict] = {}
        self.temp_table_registry: Dict[str, Dict] = {}
        
        # Compile patterns
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for special detection"""
        self.temp_table_pattern = re.compile(r'pg_temp\.\w+', re.IGNORECASE)
        self.array_operation = re.compile(r'ARRAY\[|array_agg|unnest', re.IGNORECASE)
        self.jsonb_operation = re.compile(r'jsonb_|json_|->|->>', re.IGNORECASE)
        self.window_function = re.compile(r'OVER\s*\(', re.IGNORECASE)
    
    def analyze_file(self, file_path: str, statements: List[str]) -> Dict[str, Any]:
        """Analyze all statements in a file"""
        file_lineages = []
        
        # Reset temp table registry for new file
        self.temp_table_registry.clear()
        
        for idx, stmt in enumerate(statements):
            try:
                lineage = self._analyze_statement(stmt, file_path)
                if lineage:
                    file_lineages.append(lineage)
                    self.stats['successful_parses'] += 1
                    
                    # Track temp tables for subsequent statements
                    if lineage.temp_tables:
                        for temp_table in lineage.temp_tables:
                            self.temp_table_registry[temp_table] = {
                                'statement_index': idx,
                                'columns': [c.target_column for c in lineage.column_lineage]
                            }
                            
            except Exception as e:
                if self.debug:
                    print(f"      Warning: Parse error in statement {idx}: {str(e)[:100]}")
                self.stats['parse_errors'] += 1
                
                file_lineages.append(StatementLineage(
                    file_path=file_path,
                    statement_type="ERROR",
                    parse_error=str(e)
                ))
        
        return {
            'file_path': file_path,
            'statement_count': len(statements),
            'lineages': file_lineages,
            'temp_tables': list(self.temp_table_registry.keys()),
            'stats': dict(self.stats)
        }
    
    def _analyze_statement(self, sql: str, file_path: str) -> Optional[StatementLineage]:
        """Analyze a single PostgreSQL statement"""
        try:
            # Parse with lenient error handling
            tree = parse_one(sql, dialect=self.dialect, error_level='ignore')
            if not tree:
                return None
            
            stmt_type = self._get_statement_type(tree)
            stmt_subtype = self._get_statement_subtype(tree, sql)
            
            # Extract CTEs first
            cte_definitions = self._extract_ctes(tree)
            
            # Extract lineage based on statement type
            if isinstance(tree, exp.Insert):
                return self._analyze_insert(tree, file_path, cte_definitions, sql)
            
            elif isinstance(tree, exp.Update):
                return self._analyze_update(tree, file_path, cte_definitions, sql)
            
            elif isinstance(tree, exp.Delete):
                return self._analyze_delete(tree, file_path, cte_definitions, sql)
            
            elif isinstance(tree, exp.Merge):
                return self._analyze_merge(tree, file_path, cte_definitions)
            
            elif isinstance(tree, exp.Create):
                return self._analyze_create(tree, file_path, cte_definitions)
            
            elif isinstance(tree, exp.Select):
                return self._analyze_select(tree, file_path, cte_definitions, stmt_subtype)
            
            else:
                # Generic handling
                target_table = self._extract_target_table(tree)
                source_tables = self._extract_source_tables(tree)
                column_lineage = self._extract_column_lineage(tree, target_table)
                
                return StatementLineage(
                    file_path=file_path,
                    statement_type=stmt_type,
                    statement_subtype=stmt_subtype,
                    target_table=target_table,
                    source_tables=source_tables,
                    column_lineage=column_lineage,
                    cte_definitions=cte_definitions,
                    is_dynamic=self._is_dynamic_sql(sql)
                )
                
        except Exception as e:
            raise e
    
    def _analyze_insert(self, tree: exp.Insert, file_path: str, cte_definitions: Dict, sql: str) -> StatementLineage:
        """Analyze INSERT statement (including INSERT...SELECT, UPSERT with ON CONFLICT)"""
        target_table = self._extract_target_table(tree)
        source_tables = []
        column_lineage = []
        returning_columns = []
        
        # Get target columns
        target_cols = []
        if tree.this:
            for col in tree.this.expressions:
                if isinstance(col, exp.Column):
                    target_cols.append(col.name)
        
        # Check for INSERT...SELECT
        select = tree.expression
        if select and isinstance(select, exp.Select):
            source_tables = self._extract_source_tables(select)
            alias_map = self._build_alias_map(select)
            
            # Map columns from SELECT to INSERT
            select_cols = select.expressions
            
            for i, projection in enumerate(select_cols):
                if i < len(target_cols):
                    target_col = target_cols[i]
                else:
                    target_col = projection.alias_or_name or f"column_{i}"
                
                source_cols = self._find_source_columns(projection, cte_definitions, alias_map)
                transform_type = self._classify_transform(projection)
                
                column_lineage.append(ColumnLineage(
                    target_column=target_col,
                    target_table=target_table or "unknown",
                    source_columns=source_cols,
                    transform_type=transform_type,
                    expression=projection.sql()[:200],
                    is_aggregate=self._is_aggregate(projection),
                    is_calculated=self._is_calculated(projection),
                    is_array_operation=bool(self.array_operation.search(projection.sql())),
                    is_jsonb_operation=bool(self.jsonb_operation.search(projection.sql()))
                ))
        
        # Check for ON CONFLICT (UPSERT)
        stmt_subtype = "INSERT_SELECT" if source_tables else "INSERT_VALUES"
        if "ON CONFLICT" in sql.upper():
            stmt_subtype = "UPSERT"
        
        # Check for RETURNING clause
        if "RETURNING" in sql.upper():
            # Extract RETURNING columns
            returning_match = re.search(r'RETURNING\s+(.+?)(?:;|$)', sql, re.IGNORECASE | re.DOTALL)
            if returning_match:
                ret_clause = returning_match.group(1).strip()
                returning_columns = [c.strip() for c in ret_clause.split(',')]
        
        return StatementLineage(
            file_path=file_path,
            statement_type="INSERT",
            statement_subtype=stmt_subtype,
            target_table=target_table,
            source_tables=source_tables,
            column_lineage=column_lineage,
            cte_definitions=cte_definitions,
            temp_tables=self._extract_temp_table_names(target_table),
            returning_columns=returning_columns
        )
    
    def _analyze_update(self, tree: exp.Update, file_path: str, cte_definitions: Dict, sql: str) -> StatementLineage:
        """Analyze UPDATE statement with FROM clause and RETURNING"""
        target_table = self._extract_target_table(tree)
        source_tables = []
        column_lineage = []
        returning_columns = []
        
        # Extract source tables
        source_tables.extend(self._extract_source_tables(tree))
        
        # Resolve aliases
        alias_map = self._build_alias_map(tree)

        # Get SET clauses
        for set_expr in tree.find_all(exp.Set):
            target_col = set_expr.this.name if isinstance(set_expr.this, exp.Column) else str(set_expr.this)
            
            if set_expr.expression:
                source_cols = self._find_source_columns(set_expr.expression, cte_definitions, alias_map)
                transform_type = self._classify_transform(set_expr.expression)
                
                # Check for subqueries
                subqueries = list(set_expr.expression.find_all(exp.Subquery))
                if subqueries:
                    for subq in subqueries:
                        source_tables.extend(self._extract_source_tables(subq))
                
                column_lineage.append(ColumnLineage(
                    target_column=target_col,
                    target_table=target_table or "unknown",
                    source_columns=source_cols,
                    transform_type=transform_type,
                    expression=set_expr.expression.sql()[:200],
                    is_aggregate=self._is_aggregate(set_expr.expression),
                    is_calculated=self._is_calculated(set_expr.expression),
                    is_array_operation=bool(self.array_operation.search(set_expr.expression.sql())),
                    is_jsonb_operation=bool(self.jsonb_operation.search(set_expr.expression.sql()))
                ))
        
        # Check for RETURNING clause
        if "RETURNING" in sql.upper():
            returning_match = re.search(r'RETURNING\s+(.+?)(?:;|$)', sql, re.IGNORECASE | re.DOTALL)
            if returning_match:
                ret_clause = returning_match.group(1).strip()
                returning_columns = [c.strip() for c in ret_clause.split(',')]
        
        return StatementLineage(
            file_path=file_path,
            statement_type="UPDATE",
            target_table=target_table,
            source_tables=list(set(source_tables)),
            column_lineage=column_lineage,
            cte_definitions=cte_definitions,
            returning_columns=returning_columns
        )
    
    def _analyze_delete(self, tree: exp.Delete, file_path: str, cte_definitions: Dict, sql: str) -> StatementLineage:
        """Analyze DELETE statement with USING clause and RETURNING"""
        target_table = self._extract_target_table(tree)
        source_tables = self._extract_source_tables(tree)
        returning_columns = []
        
        # Check for RETURNING clause
        if "RETURNING" in sql.upper():
            returning_match = re.search(r'RETURNING\s+(.+?)(?:;|$)', sql, re.IGNORECASE | re.DOTALL)
            if returning_match:
                ret_clause = returning_match.group(1).strip()
                returning_columns = [c.strip() for c in ret_clause.split(',')]
        
        return StatementLineage(
            file_path=file_path,
            statement_type="DELETE",
            target_table=target_table,
            source_tables=source_tables,
            column_lineage=[],
            cte_definitions=cte_definitions,
            returning_columns=returning_columns
        )
    
    def _analyze_merge(self, tree: exp.Merge, file_path: str, cte_definitions: Dict) -> StatementLineage:
        """Analyze MERGE statement (PostgreSQL 15+)"""
        target_table = self._extract_target_table(tree)
        source_tables = []
        column_lineage = []
        
        # Get source table from USING clause
        for table in tree.find_all(exp.Table):
            table_name = self._get_full_table_name(table)
            if table_name != target_table:
                source_tables.append(table_name)
        
        # Extract from all subqueries
        for subq in tree.find_all(exp.Subquery):
            source_tables.extend(self._extract_source_tables(subq))
        
        alias_map = self._build_alias_map(tree)

        # Process WHEN MATCHED UPDATE
        for when in tree.find_all(exp.When):
            for set_expr in when.find_all(exp.Set):
                target_col = set_expr.this.name if isinstance(set_expr.this, exp.Column) else str(set_expr.this)
                source_cols = self._find_source_columns(set_expr.expression, cte_definitions, alias_map)
                
                column_lineage.append(ColumnLineage(
                    target_column=target_col,
                    target_table=target_table or "unknown",
                    source_columns=source_cols,
                    transform_type="merge_update",
                    expression=set_expr.expression.sql()[:200] if set_expr.expression else ""
                ))
        
        return StatementLineage(
            file_path=file_path,
            statement_type="MERGE",
            target_table=target_table,
            source_tables=list(set(source_tables)),
            column_lineage=column_lineage,
            cte_definitions=cte_definitions
        )
    
    def _analyze_create(self, tree: exp.Create, file_path: str, cte_definitions: Dict) -> StatementLineage:
        """Analyze CREATE TABLE/VIEW/MATERIALIZED VIEW"""
        target_table = self._extract_target_table(tree)
        source_tables = []
        column_lineage = []
        
        # Check for CREATE TABLE AS or CREATE VIEW AS
        select = tree.find(exp.Select)
        
        if select:
            source_tables = self._extract_source_tables(select)
            alias_map = self._build_alias_map(select)
            
            # Get column mappings
            for projection in select.expressions:
                output_col = projection.alias_or_name
                source_cols = self._find_source_columns(projection, cte_definitions, alias_map)
                transform_type = self._classify_transform(projection)
                
                column_lineage.append(ColumnLineage(
                    target_column=output_col,
                    target_table=target_table or "unknown",
                    source_columns=source_cols,
                    transform_type=transform_type,
                    expression=projection.sql()[:200],
                    is_aggregate=self._is_aggregate(projection),
                    is_calculated=self._is_calculated(projection),
                    is_array_operation=bool(self.array_operation.search(projection.sql())),
                    is_jsonb_operation=bool(self.jsonb_operation.search(projection.sql()))
                ))
        
        # Determine if this is a temp table
        temp_tables = []
        sql_str = tree.sql().upper()
        if target_table and ('PG_TEMP' in target_table.upper() or 'TEMP' in sql_str[:100] or 'TEMPORARY' in sql_str[:100]):
            temp_tables = [target_table]
        
        return StatementLineage(
            file_path=file_path,
            statement_type="CREATE",
            target_table=target_table,
            source_tables=source_tables,
            column_lineage=column_lineage,
            cte_definitions=cte_definitions,
            temp_tables=temp_tables
        )
    
    def _analyze_select(self, tree: exp.Select, file_path: str, cte_definitions: Dict, stmt_subtype: Optional[str]) -> StatementLineage:
        """Analyze SELECT statement"""
        target_table = None
        source_tables = self._extract_source_tables(tree)
        alias_map = self._build_alias_map(tree)
        column_lineage = []
        
        # Extract column lineage for SELECT projections
        for projection in tree.expressions:
            output_col = projection.alias_or_name
            source_cols = self._find_source_columns(projection, cte_definitions, alias_map)
            transform_type = self._classify_transform(projection)
            
            column_lineage.append(ColumnLineage(
                target_column=output_col,
                target_table="result_set",
                source_columns=source_cols,
                transform_type=transform_type,
                expression=projection.sql()[:200],
                is_aggregate=self._is_aggregate(projection),
                is_calculated=self._is_calculated(projection),
                is_array_operation=bool(self.array_operation.search(projection.sql())),
                is_jsonb_operation=bool(self.jsonb_operation.search(projection.sql()))
            ))
        
        return StatementLineage(
            file_path=file_path,
            statement_type="SELECT",
            statement_subtype=stmt_subtype,
            target_table=target_table,
            source_tables=source_tables,
            column_lineage=column_lineage,
            cte_definitions=cte_definitions
        )
    
    # Helper methods
    def _get_statement_type(self, tree: exp.Expression) -> str:
        """Get statement type from parse tree"""
        return tree.__class__.__name__.upper()
    
    def _get_statement_subtype(self, tree: exp.Expression, sql: str) -> Optional[str]:
        """Determine statement subtype"""
        sql_upper = sql.upper()
        
        if "ON CONFLICT" in sql_upper:
            return "UPSERT"
        if "RETURNING" in sql_upper:
            return "WITH_RETURNING"
        if "RECURSIVE" in sql_upper and "WITH" in sql_upper:
            return "RECURSIVE_CTE"
        
        return None
    
    def _extract_ctes(self, tree: exp.Expression) -> Dict[str, Any]:
        """Extract CTE definitions"""
        ctes = {}
        for cte in tree.find_all(exp.CTE):
            cte_name = cte.alias_or_name
            cte_select = cte.this
            ctes[cte_name] = {
                'query': cte_select,
                'columns': [col.alias_or_name for col in cte_select.expressions] if isinstance(cte_select, exp.Select) else []
            }
        return ctes
    
    def _extract_target_table(self, tree: exp.Expression) -> Optional[str]:
        """Extract target table name"""
        if hasattr(tree, 'this') and isinstance(tree.this, exp.Table):
            return self._get_full_table_name(tree.this)
        
        for table in tree.find_all(exp.Table):
            return self._get_full_table_name(table)
        
        return None
    
    def _extract_source_tables(self, tree: exp.Expression) -> List[str]:
        """Extract all source table names"""
        tables = []
        
        for table in tree.find_all(exp.Table):
            table_name = self._get_full_table_name(table)
            if table_name:
                tables.append(table_name)
        
        return list(set(tables))
    
    def _get_full_table_name(self, table: exp.Table) -> str:
        """Get full table name with schema"""
        parts = []
        if table.catalog:
            parts.append(table.catalog)
        if table.db:
            parts.append(table.db)
        parts.append(table.name)
        return '.'.join(parts)
    
    def _build_alias_map(self, tree: exp.Expression) -> Dict[str, str]:
        """Build mapping of aliases to table names"""
        alias_map = {}
        
        for table in tree.find_all(exp.Table):
            if table.alias:
                alias_map[table.alias] = self._get_full_table_name(table)
        
        for subq in tree.find_all(exp.Subquery):
            if subq.alias:
                alias_map[subq.alias] = "subquery"
        
        return alias_map
    
    def _find_source_columns(self, expression: exp.Expression, cte_definitions: Dict, alias_map: Dict) -> List[Dict[str, str]]:
        """Find source columns from an expression"""
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
        """Classify the type of transformation"""
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
        if self.window_function.search(sql):
            return "window_function"
        if any(op in sql for op in ['+', '-', '*', '/', '||']):
            return "calculation"
        if isinstance(expression, exp.Column):
            return "direct"
        
        return "expression"
    
    def _is_aggregate(self, expression: exp.Expression) -> bool:
        """Check if expression contains aggregates"""
        agg_functions = {'SUM', 'COUNT', 'AVG', 'MIN', 'MAX', 'ARRAY_AGG', 'STRING_AGG', 'JSONB_AGG'}
        sql_upper = expression.sql().upper()
        return any(func in sql_upper for func in agg_functions)
    
    def _is_calculated(self, expression: exp.Expression) -> bool:
        """Check if expression is calculated"""
        return any(isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod)) for node in expression.walk())
    
    def _extract_column_lineage(self, tree: exp.Expression, target_table: Optional[str]) -> List[ColumnLineage]:
        """Generic column lineage extraction"""
        lineage = []
        return lineage
    
    def _is_dynamic_sql(self, sql: str) -> bool:
        """Check if SQL is dynamic"""
        return 'EXECUTE' in sql.upper() and ('$' in sql or 'quote_' in sql.lower())
    
    def _extract_temp_table_names(self, table_name: Optional[str]) -> List[str]:
        """Extract temp table names"""
        if table_name and ('pg_temp' in table_name.lower() or table_name.startswith('temp_')):
            return [table_name]
        return []
