"""
Enhanced Oracle-Specific SQL Statement Analyzer
Handles Oracle dialect patterns including PL/SQL, hierarchical queries (CONNECT BY),
PIVOT/UNPIVOT, MODEL clause, flashback queries, MERGE statements, and Oracle-specific functions.
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
    has_connect_by: bool = False  # Oracle CONNECT BY
    has_pivot: bool = False  # Oracle PIVOT/UNPIVOT
    has_model: bool = False  # Oracle MODEL clause


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
    global_temp_tables: List[str] = field(default_factory=list)
    is_dynamic: bool = False
    parse_error: Optional[str] = None
    statement_subtype: Optional[str] = None
    oracle_features: List[str] = field(default_factory=list)  # Track Oracle-specific features used


class EnhancedSQLAnalyzer:
    """Analyze Oracle SQL statements and extract comprehensive lineage"""

    def __init__(self, dialect: str = "oracle", debug: bool = False):
        self.dialect = dialect
        self.debug = debug
        self.stats = defaultdict(int)

        # Track CTEs and temp tables across batches
        self.cte_registry: Dict[str, Dict] = {}
        self.temp_table_registry: Dict[str, Dict] = {}
        self.global_temp_table_registry: Dict[str, Dict] = {}

        # Compile Oracle-specific patterns
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for Oracle-specific detection"""
        # Oracle temporary tables
        self.global_temp_pattern = re.compile(
            r'CREATE\s+GLOBAL\s+TEMPORARY\s+TABLE\s+([\w\.\"]+)',
            re.IGNORECASE
        )

        # Oracle hierarchical queries
        self.connect_by_pattern = re.compile(r'\bCONNECT\s+BY\b', re.IGNORECASE)
        self.start_with_pattern = re.compile(r'\bSTART\s+WITH\b', re.IGNORECASE)
        self.prior_pattern = re.compile(r'\bPRIOR\b', re.IGNORECASE)
        self.level_pattern = re.compile(r'\bLEVEL\b', re.IGNORECASE)
        self.sys_connect_by_path_pattern = re.compile(r'\bSYS_CONNECT_BY_PATH\b', re.IGNORECASE)

        # PIVOT/UNPIVOT
        self.pivot_pattern = re.compile(r'\bPIVOT\b', re.IGNORECASE)
        self.unpivot_pattern = re.compile(r'\bUNPIVOT\b', re.IGNORECASE)

        # MODEL clause
        self.model_pattern = re.compile(r'\bMODEL\b', re.IGNORECASE)

        # Flashback queries
        self.flashback_pattern = re.compile(r'\bAS\s+OF\s+(?:SCN|TIMESTAMP)\b', re.IGNORECASE)
        self.versions_between_pattern = re.compile(r'\bVERSIONS\s+BETWEEN\b', re.IGNORECASE)

        # MERGE statement
        self.merge_pattern = re.compile(r'\bMERGE\s+INTO\b', re.IGNORECASE)

        # Oracle analytic functions
        self.keep_pattern = re.compile(r'\bKEEP\s*\(', re.IGNORECASE)
        self.within_group_pattern = re.compile(r'\bWITHIN\s+GROUP\b', re.IGNORECASE)

        # Oracle-specific functions
        self.decode_pattern = re.compile(r'\bDECODE\s*\(', re.IGNORECASE)
        self.nvl_pattern = re.compile(r'\bNVL\s*\(', re.IGNORECASE)
        self.nvl2_pattern = re.compile(r'\bNVL2\s*\(', re.IGNORECASE)

        # Database link references
        self.db_link_pattern = re.compile(r'@[\w\.\-]+', re.IGNORECASE)

        # Dual table (Oracle system table)
        self.dual_pattern = re.compile(r'\bFROM\s+DUAL\b', re.IGNORECASE)

        # Oracle outer join syntax (old style)
        self.oracle_outer_join_pattern = re.compile(r'\(\+\)', re.IGNORECASE)

        # PL/SQL blocks
        self.plsql_block_pattern = re.compile(r'\b(?:DECLARE|BEGIN)\b', re.IGNORECASE)

        # Oracle package calls
        self.package_call_pattern = re.compile(r'([\w\.]+)\.([\w]+)\s*\(', re.IGNORECASE)

    def analyze_file(self, file_path: str, statements: List[str]) -> Dict[str, Any]:
        """Analyze all statements in a file"""
        file_lineages = []

        # Reset registries for new file
        self.temp_table_registry.clear()
        self.global_temp_table_registry.clear()

        for idx, stmt in enumerate(statements):
            try:
                lineage = self._analyze_statement(stmt, file_path)
                if lineage:
                    file_lineages.append(lineage)
                    self.stats['successful_parses'] += 1

                    # Track global temp tables for subsequent statements
                    if lineage.global_temp_tables:
                        for temp_table in lineage.global_temp_tables:
                            self.global_temp_table_registry[temp_table] = {
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
            'global_temp_tables': list(self.global_temp_table_registry.keys()),
            'stats': dict(self.stats)
        }

    def _analyze_statement(self, sql: str, file_path: str) -> Optional[StatementLineage]:
        """Analyze a single SQL statement"""
        sql = sql.strip()
        if not sql or len(sql) < 5:
            return None

        # Detect Oracle-specific features
        oracle_features = self._detect_oracle_features(sql)

        try:
            # Parse with sqlglot (with lenient error handling)
            parsed = None
            try:
                parsed = parse_one(sql, dialect=self.dialect, error_level='ignore')
            except Exception as parse_err:
                if self.debug:
                    print(f"      Sqlglot parse failed, using regex fallback: {str(parse_err)[:50]}")
                # Fall back to regex-based parsing
                return self._analyze_with_regex(sql, file_path, oracle_features)

            if not parsed:
                # Sqlglot returned None, use regex fallback
                return self._analyze_with_regex(sql, file_path, oracle_features)

            # Determine statement type
            stmt_type = self._get_statement_type(parsed)

            lineage = StatementLineage(
                file_path=file_path,
                statement_type=stmt_type,
                oracle_features=oracle_features
            )

            # Handle different statement types
            if isinstance(parsed, exp.Select):
                self._analyze_select(parsed, lineage, sql)
            elif isinstance(parsed, exp.Insert):
                self._analyze_insert(parsed, lineage, sql)
            elif isinstance(parsed, exp.Update):
                self._analyze_update(parsed, lineage, sql)
            elif isinstance(parsed, exp.Delete):
                self._analyze_delete(parsed, lineage, sql)
            elif isinstance(parsed, exp.Merge):
                self._analyze_merge(parsed, lineage, sql)
            elif isinstance(parsed, exp.Create):
                self._analyze_create(parsed, lineage, sql)
            elif isinstance(parsed, exp.Drop):
                self._analyze_drop(parsed, lineage, sql)
            elif isinstance(parsed, exp.Command):
                # PL/SQL or other commands
                lineage.is_dynamic = True
                lineage.statement_subtype = "PLSQL_BLOCK"

            return lineage

        except Exception as e:
            if self.debug:
                print(f"        Error parsing statement: {str(e)[:100]}")
            # Try regex fallback before giving up
            try:
                return self._analyze_with_regex(sql, file_path, oracle_features)
            except:
                return StatementLineage(
                    file_path=file_path,
                    statement_type="UNKNOWN",
                    parse_error=str(e),
                    oracle_features=oracle_features
                )

    def _detect_oracle_features(self, sql: str) -> List[str]:
        """Detect Oracle-specific features in SQL"""
        features = []

        if self.connect_by_pattern.search(sql):
            features.append("CONNECT_BY")
        if self.pivot_pattern.search(sql):
            features.append("PIVOT")
        if self.unpivot_pattern.search(sql):
            features.append("UNPIVOT")
        if self.model_pattern.search(sql):
            features.append("MODEL")
        if self.flashback_pattern.search(sql):
            features.append("FLASHBACK")
        if self.versions_between_pattern.search(sql):
            features.append("VERSIONS_BETWEEN")
        if self.merge_pattern.search(sql):
            features.append("MERGE")
        if self.db_link_pattern.search(sql):
            features.append("DATABASE_LINK")
        if self.oracle_outer_join_pattern.search(sql):
            features.append("ORACLE_OUTER_JOIN")
        if self.dual_pattern.search(sql):
            features.append("DUAL_TABLE")
        if self.decode_pattern.search(sql):
            features.append("DECODE")
        if self.keep_pattern.search(sql):
            features.append("KEEP")
        if self.within_group_pattern.search(sql):
            features.append("WITHIN_GROUP")
        if self.plsql_block_pattern.search(sql):
            features.append("PLSQL_BLOCK")

        return features

    def _get_statement_type(self, parsed: exp.Expression) -> str:
        """Get statement type from parsed expression"""
        type_map = {
            exp.Select: "SELECT",
            exp.Insert: "INSERT",
            exp.Update: "UPDATE",
            exp.Delete: "DELETE",
            exp.Merge: "MERGE",
            exp.Create: "CREATE",
            exp.Drop: "DROP",
            exp.Alter: "ALTER",
            exp.Command: "COMMAND",
        }

        for exp_type, name in type_map.items():
            if isinstance(parsed, exp_type):
                return name

        return "UNKNOWN"

    def _analyze_select(self, parsed: exp.Select, lineage: StatementLineage, sql: str):
        """Analyze SELECT statement"""
        # Extract CTEs
        if parsed.args.get('with'):
            self._extract_ctes(parsed.args['with'], lineage)

        # Extract source tables
        source_tables = self._extract_tables(parsed)
        lineage.source_tables = source_tables

        # Extract column lineage
        lineage.column_lineage = self._extract_column_lineage(parsed, None, sql)

    def _analyze_insert(self, parsed: exp.Insert, lineage: StatementLineage, sql: str):
        """Analyze INSERT statement"""
        # Get target table
        if parsed.this:
            lineage.target_table = self._get_table_name(parsed.this)

        # Get source from SELECT
        select_expr = parsed.expression
        if select_expr and isinstance(select_expr, exp.Select):
            lineage.source_tables = self._extract_tables(select_expr)
            lineage.column_lineage = self._extract_column_lineage(select_expr, lineage.target_table, sql)

    def _analyze_update(self, parsed: exp.Update, lineage: StatementLineage, sql: str):
        """Analyze UPDATE statement"""
        # Get target table
        if parsed.this:
            lineage.target_table = self._get_table_name(parsed.this)

        # Get source tables (from joins or subqueries in SET or WHERE)
        lineage.source_tables = self._extract_tables(parsed)

        # Extract column lineage from SET clauses
        lineage.column_lineage = self._extract_update_column_lineage(parsed, sql)

    def _analyze_delete(self, parsed: exp.Delete, lineage: StatementLineage, sql: str):
        """Analyze DELETE statement"""
        # Get target table
        if parsed.this:
            lineage.target_table = self._get_table_name(parsed.this)

        # Get source tables (from joins or subqueries in WHERE)
        lineage.source_tables = self._extract_tables(parsed)

    def _analyze_merge(self, parsed: exp.Merge, lineage: StatementLineage, sql: str):
        """Analyze MERGE statement"""
        lineage.statement_subtype = "MERGE"

        # Get target table
        if parsed.this:
            lineage.target_table = self._get_table_name(parsed.this)

        # Get source tables
        lineage.source_tables = self._extract_tables(parsed)

        # Extract column lineage from WHEN MATCHED/NOT MATCHED clauses
        lineage.column_lineage = self._extract_merge_column_lineage(parsed, sql)

    def _analyze_create(self, parsed: exp.Create, lineage: StatementLineage, sql: str):
        """Analyze CREATE statement"""
        kind = parsed.kind if hasattr(parsed, 'kind') else None

        if kind:
            lineage.statement_subtype = f"CREATE_{kind.upper()}"

        # Get target object
        if parsed.this:
            lineage.target_table = self._get_table_name(parsed.this)

        # Check if CREATE TABLE AS SELECT or CREATE VIEW
        if parsed.expression and isinstance(parsed.expression, exp.Select):
            lineage.source_tables = self._extract_tables(parsed.expression)
            lineage.column_lineage = self._extract_column_lineage(parsed.expression, lineage.target_table, sql)
        else:
            # For regular CREATE TABLE statements, extract column definitions
            lineage.column_lineage = self._extract_create_table_columns(parsed, lineage.target_table)

        # Check for GLOBAL TEMPORARY TABLE
        if self.global_temp_pattern.search(sql):
            lineage.global_temp_tables.append(lineage.target_table)

    def _analyze_drop(self, parsed: exp.Drop, lineage: StatementLineage, sql: str):
        """Analyze DROP statement"""
        if parsed.this:
            lineage.target_table = self._get_table_name(parsed.this)

    def _extract_ctes(self, with_expr: exp.With, lineage: StatementLineage):
        """Extract CTE definitions"""
        for cte in with_expr.expressions:
            if isinstance(cte, exp.CTE):
                cte_name = cte.alias
                cte_query = cte.this

                cte_info = {
                    'name': cte_name,
                    'source_tables': self._extract_tables(cte_query),
                    'columns': []
                }

                # Try to get column names
                if hasattr(cte, 'args') and 'columns' in cte.args:
                    cte_info['columns'] = [col.name for col in cte.args['columns'].expressions]

                lineage.cte_definitions[cte_name] = cte_info
                self.cte_registry[cte_name] = cte_info

    def _extract_tables(self, expr: exp.Expression) -> List[str]:
        """Extract all table references from expression"""
        tables = set()

        for table in expr.find_all(exp.Table):
            table_name = self._get_table_name(table)
            if table_name and table_name.upper() != 'DUAL':  # Exclude Oracle DUAL
                tables.add(table_name)

        return sorted(list(tables))

    def _get_table_name(self, table: exp.Table) -> str:
        """Get fully qualified table name"""
        parts = []

        if hasattr(table, 'catalog') and table.catalog:
            parts.append(str(table.catalog))
        if hasattr(table, 'db') and table.db:
            parts.append(str(table.db))
        if hasattr(table, 'name') and table.name:
            parts.append(str(table.name))

        return '.'.join(parts) if parts else str(table)

    def _extract_column_lineage(
        self,
        select_expr: exp.Select,
        target_table: Optional[str],
        sql: str
    ) -> List[ColumnLineage]:
        """Extract column-level lineage from SELECT"""
        lineages = []

        if not select_expr or not hasattr(select_expr, 'expressions'):
            return lineages

        for projection in select_expr.expressions:
            col_lineage = self._analyze_projection(projection, target_table, sql)
            if col_lineage:
                lineages.append(col_lineage)

        return lineages

    def _analyze_projection(
        self,
        projection: exp.Expression,
        target_table: Optional[str],
        sql: str
    ) -> Optional[ColumnLineage]:
        """Analyze a single projection/column"""
        # Get column alias or name
        if isinstance(projection, exp.Alias):
            col_name = projection.alias
            col_expr = projection.this
        elif isinstance(projection, exp.Column):
            col_name = projection.name
            col_expr = projection
        else:
            col_name = str(projection)
            col_expr = projection

        # Create lineage object
        lineage = ColumnLineage(
            target_column=col_name,
            target_table=target_table or "UNKNOWN",
            expression=str(col_expr)
        )

        # Check for Oracle-specific features
        lineage.has_connect_by = bool(self.connect_by_pattern.search(str(col_expr)))
        lineage.has_pivot = bool(self.pivot_pattern.search(sql))
        lineage.has_model = bool(self.model_pattern.search(sql))

        # Detect column type
        if self._is_aggregate(col_expr):
            lineage.is_aggregate = True
            lineage.transform_type = "aggregate"
        elif self._is_calculated(col_expr):
            lineage.is_calculated = True
            lineage.transform_type = "calculated"

        # Extract source columns
        lineage.source_columns = self._extract_source_columns(col_expr)

        return lineage

    def _extract_source_columns(self, expr: exp.Expression) -> List[Dict[str, str]]:
        """Extract source columns from expression"""
        sources = []

        for col in expr.find_all(exp.Column):
            source = {
                'column': col.name,
                'table': col.table if hasattr(col, 'table') and col.table else 'UNKNOWN'
            }
            sources.append(source)

        return sources

    def _is_aggregate(self, expr: exp.Expression) -> bool:
        """Check if expression contains aggregate functions"""
        agg_functions = {
            exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max,
            exp.StddevPop, exp.StddevSamp, exp.VariancePop, exp.VarianceSamp
        }

        for func_type in agg_functions:
            if list(expr.find_all(func_type)):
                return True

        return False

    def _is_calculated(self, expr: exp.Expression) -> bool:
        """Check if expression is a calculation"""
        calc_types = {
            exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod,
            exp.Case, exp.If, exp.Coalesce
        }

        for calc_type in calc_types:
            if list(expr.find_all(calc_type)):
                return True

        return False

    def _extract_update_column_lineage(self, parsed: exp.Update, sql: str) -> List[ColumnLineage]:
        """Extract column lineage from UPDATE SET clauses"""
        lineages = []

        target_table = self._get_table_name(parsed.this) if parsed.this else "UNKNOWN"

        if parsed.expressions:
            for set_expr in parsed.expressions:
                if isinstance(set_expr, exp.EQ):  # SET col = value
                    target_col = set_expr.this
                    source_expr = set_expr.expression

                    col_name = target_col.name if isinstance(target_col, exp.Column) else str(target_col)

                    lineage = ColumnLineage(
                        target_column=col_name,
                        target_table=target_table,
                        expression=str(source_expr),
                        source_columns=self._extract_source_columns(source_expr)
                    )

                    if self._is_aggregate(source_expr):
                        lineage.is_aggregate = True
                        lineage.transform_type = "aggregate"
                    elif self._is_calculated(source_expr):
                        lineage.is_calculated = True
                        lineage.transform_type = "calculated"

                    lineages.append(lineage)

        return lineages

    def _extract_merge_column_lineage(self, parsed: exp.Merge, sql: str) -> List[ColumnLineage]:
        """Extract column lineage from MERGE statement"""
        lineages = []

        target_table = self._get_table_name(parsed.this) if parsed.this else "UNKNOWN"

        # Extract from WHEN MATCHED UPDATE SET
        # Extract from WHEN NOT MATCHED INSERT VALUES
        # For now, use regex to find SET clauses in MERGE
        set_pattern = re.compile(r'SET\s+([\w\.]+)\s*=\s*([^\s,]+)', re.IGNORECASE)
        matches = set_pattern.findall(sql)

        for col_name, source in matches:
            lineage = ColumnLineage(
                target_column=col_name,
                target_table=target_table,
                expression=source,
                transform_type="merge"
            )
            lineages.append(lineage)

        return lineages

    def _extract_create_table_columns(self, parsed: exp.Create, target_table: Optional[str]) -> List[ColumnLineage]:
        """Extract column definitions from CREATE TABLE statement"""
        lineages = []

        if not target_table:
            return lineages

        # Check if this is a table schema definition
        if not parsed.this:
            return lineages

        # Look for column definitions in the schema
        schema = parsed.this

        # Try to find ColumnDef nodes in the AST
        for column_def in schema.find_all(exp.ColumnDef):
            col_name = column_def.this.name if hasattr(column_def.this, 'name') else str(column_def.this)

            lineage = ColumnLineage(
                target_column=col_name,
                target_table=target_table,
                source_columns=[],  # No source columns for table definitions
                transform_type="direct",
                expression="",
                is_aggregate=False,
                is_calculated=False
            )
            lineages.append(lineage)

        return lineages

    def _lineage_to_dict(self, lineage: StatementLineage) -> Dict[str, Any]:
        """Convert StatementLineage to dictionary"""
        return {
            'file_path': lineage.file_path,
            'statement_type': lineage.statement_type,
            'target_table': lineage.target_table,
            'source_tables': lineage.source_tables,
            'column_lineage': [
                {
                    'target_column': col.target_column,
                    'target_table': col.target_table,
                    'source_columns': col.source_columns,
                    'transform_type': col.transform_type,
                    'expression': col.expression,
                    'is_aggregate': col.is_aggregate,
                    'is_calculated': col.is_calculated,
                    'cte_dependency': col.cte_dependency,
                    'has_connect_by': col.has_connect_by,
                    'has_pivot': col.has_pivot,
                    'has_model': col.has_model,
                }
                for col in lineage.column_lineage
            ],
            'cte_definitions': lineage.cte_definitions,
            'temp_tables': lineage.temp_tables,
            'global_temp_tables': lineage.global_temp_tables,
            'is_dynamic': lineage.is_dynamic,
            'parse_error': lineage.parse_error,
            'statement_subtype': lineage.statement_subtype,
            'oracle_features': lineage.oracle_features,
        }

    def analyze_batch(self, files_and_statements: Dict[str, List[str]]) -> Dict[str, Any]:
        """Analyze a batch of files"""
        results = []

        for file_path, statements in files_and_statements.items():
            if self.debug:
                print(f"    Analyzing: {file_path} ({len(statements)} statements)")

            file_result = self.analyze_file(file_path, statements)
            results.append(file_result)

        return {
            'files': results,
            'total_files': len(files_and_statements),
            'statistics': dict(self.stats)
        }

    def get_stats(self) -> Dict[str, int]:
        """Get analysis statistics"""
        return dict(self.stats)

    def _analyze_with_regex(self, sql: str, file_path: str, oracle_features: List[str]) -> StatementLineage:
        """
        Comprehensive regex-based fallback for Oracle SQL parsing.
        Import and use the dedicated regex analyzer module.
        """
        try:
            from . import oracle_analyzer_regex
            return oracle_analyzer_regex.analyze_with_regex(sql, file_path, oracle_features)
        except ImportError:
            # Fallback to basic regex if module not available
            return self._basic_regex_fallback(sql, file_path, oracle_features)

    def _basic_regex_fallback(self, sql: str, file_path: str, oracle_features: List[str]) -> StatementLineage:
        """Basic regex fallback (legacy)"""
        lineage = StatementLineage(
            file_path=file_path,
            statement_type="UNKNOWN",
            oracle_features=oracle_features
        )

        sql_upper = sql.upper()
        if 'CREATE' in sql_upper and 'VIEW' in sql_upper:
            lineage.statement_type = "CREATE"
            lineage.statement_subtype = "CREATE_VIEW"
            view_match = re.search(r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([\w\.]+)', sql, re.IGNORECASE)
            if view_match:
                lineage.target_table = view_match.group(1)
        elif 'CREATE' in sql_upper and 'TABLE' in sql_upper:
            lineage.statement_type = "CREATE"
            table_match = re.search(r'CREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+([\w\.]+)', sql, re.IGNORECASE)
            if table_match:
                lineage.target_table = table_match.group(1)

        from_tables = re.findall(r'(?:FROM|JOIN)\s+([\w\.]+)', sql, re.IGNORECASE)
        lineage.source_tables = list(set(from_tables))

        return lineage
