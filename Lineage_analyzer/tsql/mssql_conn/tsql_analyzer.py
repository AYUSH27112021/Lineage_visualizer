"""
Enhanced T-SQL Statement Analyzer
Handles all T-SQL patterns including CTEs, MERGE, SELECT INTO, nested queries, etc.
"""

import sqlglot
from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import build_scope, Scope
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
    statement_subtype: Optional[str] = None  # INSERT_SELECT, SELECT_INTO, etc.


class EnhancedSQLAnalyzer:
    """Analyze SQL statements and extract comprehensive lineage"""
    
    def __init__(self, dialect: str = "tsql", debug: bool = False):
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
        self.temp_table_pattern = re.compile(r'#[\w]+')
        self.table_variable_pattern = re.compile(r'@[\w]+')
        self.output_param_pattern = re.compile(r'@\w+\s+OUTPUT', re.IGNORECASE)
    
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
        """Analyze a single SQL statement"""
        try:
            # Parse with lenient error handling
            tree = parse_one(sql, dialect=self.dialect, error_level='ignore')
            if not tree:
                return None
            
            stmt_type = self._get_statement_type(tree)
            stmt_subtype = self._get_statement_subtype(tree, sql)
            
            # Extract CTEs first (they affect source resolution)
            cte_definitions = self._extract_ctes(tree)
            
            # Extract lineage based on statement type
            if isinstance(tree, exp.Insert):
                return self._analyze_insert(tree, file_path, cte_definitions)
            
            elif isinstance(tree, exp.Update):
                return self._analyze_update(tree, file_path, cte_definitions)
            
            elif isinstance(tree, exp.Delete):
                return self._analyze_delete(tree, file_path, cte_definitions)
            
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
    
    def _analyze_insert(self, tree: exp.Insert, file_path: str, cte_definitions: Dict) -> StatementLineage:
        """Analyze INSERT statement (including INSERT...SELECT)"""
        target_table = self._extract_target_table(tree)
        source_tables = []
        column_lineage = []
        
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
                # Prefer explicit target list; otherwise fall back to projection alias/name
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
                    is_calculated=self._is_calculated(projection)
                ))
        
        # Check for INSERT...VALUES (no lineage, just target columns)
        elif tree.expression:
            for col in target_cols:
                column_lineage.append(ColumnLineage(
                    target_column=col,
                    target_table=target_table or "unknown",
                    source_columns=[],
                    transform_type="literal",
                    expression=""
                ))
        
        return StatementLineage(
            file_path=file_path,
            statement_type="INSERT",
            statement_subtype="INSERT_SELECT" if source_tables else "INSERT_VALUES",
            target_table=target_table,
            source_tables=source_tables,
            column_lineage=column_lineage,
            cte_definitions=cte_definitions,
            temp_tables=self._extract_temp_table_names(target_table)
        )
    
    def _analyze_update(self, tree: exp.Update, file_path: str, cte_definitions: Dict) -> StatementLineage:
        """Analyze UPDATE statement with complex expressions and subqueries"""
        target_table = self._extract_target_table(tree)
        source_tables = []
        column_lineage = []
        
        # Extract source tables from WHERE, FROM, and SET clauses
        source_tables.extend(self._extract_source_tables(tree))
        
        # Resolve aliases in this update scope
        alias_map = self._build_alias_map(tree)

        # Get SET clauses
        for set_expr in tree.find_all(exp.Set):
            target_col = set_expr.this.name if isinstance(set_expr.this, exp.Column) else str(set_expr.this)
            
            # Handle subqueries in SET
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
                    is_calculated=self._is_calculated(set_expr.expression)
                ))
        
        return StatementLineage(
            file_path=file_path,
            statement_type="UPDATE",
            target_table=target_table,
            source_tables=list(set(source_tables)),  # Deduplicate
            column_lineage=column_lineage,
            cte_definitions=cte_definitions
        )
    
    def _analyze_delete(self, tree: exp.Delete, file_path: str, cte_definitions: Dict) -> StatementLineage:
        """Analyze DELETE statement"""
        target_table = self._extract_target_table(tree)
        source_tables = self._extract_source_tables(tree)
        
        return StatementLineage(
            file_path=file_path,
            statement_type="DELETE",
            target_table=target_table,
            source_tables=source_tables,
            column_lineage=[],
            cte_definitions=cte_definitions
        )
    
    def _analyze_merge(self, tree: exp.Merge, file_path: str, cte_definitions: Dict) -> StatementLineage:
        """Analyze MERGE statement with MATCHED and NOT MATCHED clauses"""
        target_table = self._extract_target_table(tree)
        source_tables = []
        column_lineage = []
        
        # Get source table from USING clause
        using = tree.find(exp.Table)
        if using:
            source_tables.append(self._get_full_table_name(using))
        
        # Extract from all subqueries
        for subq in tree.find_all(exp.Subquery):
            source_tables.extend(self._extract_source_tables(subq))
        
        # Build alias map for the MERGE scope
        alias_map = self._build_alias_map(tree)

        # Process WHEN MATCHED UPDATE
        for when in tree.find_all(exp.When):
            # Check if it's an UPDATE action
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
            
            # Check for INSERT action (WHEN NOT MATCHED)
            insert_cols = []
            for col in when.find_all(exp.Column):
                if col.table == target_table or not col.table:
                    insert_cols.append(col.name)
        
        return StatementLineage(
            file_path=file_path,
            statement_type="MERGE",
            target_table=target_table,
            source_tables=list(set(source_tables)),
            column_lineage=column_lineage,
            cte_definitions=cte_definitions
        )
    
    def _analyze_create(self, tree: exp.Create, file_path: str, cte_definitions: Dict) -> StatementLineage:
        """Analyze CREATE TABLE/VIEW/INDEX"""
        target_table = self._extract_target_table(tree)
        source_tables = []
        column_lineage = []
        
        # Check for CREATE TABLE AS SELECT or CREATE VIEW AS SELECT
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
                    is_calculated=self._is_calculated(projection)
                ))
        else:
            # CREATE TABLE with column definitions
            schema = tree.find(exp.Schema)
            if schema:
                for col_def in schema.expressions:
                    if isinstance(col_def, exp.ColumnDef):
                        column_lineage.append(ColumnLineage(
                            target_column=col_def.name,
                            target_table=target_table or "unknown",
                            source_columns=[],
                            transform_type="definition",
                            expression=""
                        ))
        
        # Determine if this is a temp table
        temp_tables = []
        if target_table and ('#' in target_table or target_table.startswith('@')):
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
        """Analyze SELECT statement (including SELECT INTO)"""
        target_table = None
        source_tables = self._extract_source_tables(tree)
        alias_map = self._build_alias_map(tree)
        column_lineage = []
        
        # Check for SELECT INTO
        into = tree.args.get('into')
        if into:
            target_table = self._get_full_table_name(into) if isinstance(into, exp.Table) else str(into)
            stmt_subtype = "SELECT_INTO"
        
        # Extract column lineage
        for projection in tree.expressions:
            output_col = projection.alias_or_name
            source_cols = self._find_source_columns(projection, cte_definitions, alias_map)
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
        
        # Handle UNION/INTERSECT/EXCEPT
        if tree.args.get('union') or tree.args.get('intersect') or tree.args.get('except'):
            stmt_subtype = "SET_OPERATION"
        
        temp_tables = []
        if target_table and '#' in target_table:
            temp_tables = [target_table]
        
        return StatementLineage(
            file_path=file_path,
            statement_type="SELECT",
            statement_subtype=stmt_subtype,
            target_table=target_table,
            source_tables=source_tables,
            column_lineage=column_lineage,
            cte_definitions=cte_definitions,
            temp_tables=temp_tables
        )
    
    def _extract_ctes(self, tree: exp.Expression) -> Dict[str, Dict]:
        """Extract CTE definitions"""
        cte_definitions = {}
        
        for cte in tree.find_all(exp.CTE):
            cte_name = cte.alias
            cte_query = cte.this
            
            # Extract columns from CTE
            columns = []
            for projection in cte_query.expressions if isinstance(cte_query, exp.Select) else []:
                columns.append(projection.alias_or_name)
            
            # Extract source tables
            source_tables = self._extract_source_tables(cte_query)
            
            cte_definitions[cte_name] = {
                'columns': columns,
                'source_tables': source_tables,
                'query': cte_query.sql()[:500]
            }
        
        return cte_definitions
    
    def _get_statement_type(self, tree: exp.Expression) -> str:
        """Get statement type"""
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
        """Get statement subtype"""
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
    
    def _extract_target_table(self, tree: exp.Expression) -> Optional[str]:
        """Extract target table"""
        if isinstance(tree, (exp.Create, exp.Insert, exp.Update, exp.Delete, exp.Merge)):
            table_node = tree.find(exp.Table)
            if table_node:
                return self._get_full_table_name(table_node)
        
        return None
    
    def _get_full_table_name(self, table: exp.Table) -> str:
        """Get fully qualified table name"""
        parts = []
        if table.catalog:
            parts.append(str(table.catalog).strip('[]'))
        if table.db:
            parts.append(str(table.db).strip('[]'))
        parts.append(str(table.name).strip('[]'))
        return '.'.join(parts)
    
    def _extract_source_tables(self, tree: exp.Expression) -> List[str]:
        """Extract all source tables including derived tables and table functions"""
        tables = []
        
        # Get all table references
        for table_node in tree.find_all(exp.Table):
            table_name = self._get_full_table_name(table_node)
            
            # Skip target tables
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
    
    def _find_source_columns(self, expr: exp.Expression, cte_definitions: Dict, alias_map: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
        """Find all source columns in an expression, resolving CTEs and table aliases"""
        sources = []
        
        for col in expr.find_all(exp.Column):
            table = str(col.table) if col.table else "unknown"
            column = str(col.name)
            
            # Check if table is a CTE
            cte_ref = None
            if table in cte_definitions:
                cte_ref = table
                table = f"CTE:{table}"
            elif alias_map and table in alias_map:
                # Resolve alias to its base table name
                table = alias_map.get(table, table)
            
            sources.append({
                "table": table,
                "column": column,
                "cte_reference": cte_ref
            })
        
        return sources

    def _build_alias_map(self, tree: exp.Expression) -> Dict[str, str]:
        """Build a mapping from table aliases to fully qualified base table names."""
        alias_map: Dict[str, str] = {}
        for table_node in tree.find_all(exp.Table):
            base_name = self._get_full_table_name(table_node)
            alias_expr = table_node.args.get('alias')
            # alias_expr may be an exp.TableAlias with .name
            try:
                alias_name = alias_expr and getattr(alias_expr, 'name', None)
            except Exception:
                alias_name = None
            if alias_name:
                alias_map[str(alias_name)] = base_name
        return alias_map
    
    def _classify_transform(self, expr: exp.Expression) -> str:
        """Classify transformation type"""
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
        """Check if expression contains aggregates"""
        agg_funcs = [exp.Sum, exp.Count, exp.Avg, exp.Max, exp.Min, exp.AggFunc]
        return any(expr.find(agg) for agg in agg_funcs)
    
    def _is_calculated(self, expr: exp.Expression) -> bool:
        """Check if expression is calculated (not direct column reference)"""
        return not isinstance(expr, exp.Column)
    
    def _is_dynamic_sql(self, sql: str) -> bool:
        """Check if SQL is dynamic"""
        dynamic_keywords = ['EXEC(', 'EXECUTE(', 'sp_executesql', 'EXECUTE IMMEDIATE']
        return any(kw in sql.upper() for kw in dynamic_keywords)
    
    def _extract_temp_table_names(self, table_name: Optional[str]) -> List[str]:
        """Extract temp table names"""
        if not table_name:
            return []
        
        if '#' in table_name or table_name.startswith('@'):
            return [table_name]
        
        return []


if __name__ == "__main__":
    analyzer = EnhancedSQLAnalyzer(debug=True)
    
    test_sql = """
    WITH cte_sales AS (
        SELECT customer_id, SUM(amount) as total
        FROM sales
        GROUP BY customer_id
    )
    INSERT INTO customer_totals (customer_id, total_sales)
    SELECT customer_id, total
    FROM cte_sales
    WHERE total > 1000;
    """
    
    result = analyzer.analyze_file("test.sql", [test_sql])
    print(result)