"""
Enhanced Snowflake Statement Analyzer
Handles Snowflake-specific SQL patterns including CTEs, MERGE, CREATE TABLE AS SELECT,
Variant columns, Time Travel, and other Snowflake-specific features.
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
    statement_subtype: Optional[str] = None  # INSERT_SELECT, CTAS, etc.


class EnhancedSQLAnalyzer:
    """Analyze Snowflake SQL statements and extract comprehensive lineage"""

    def __init__(self, dialect: str = "snowflake", debug: bool = False):
        self.dialect = dialect
        self.debug = debug
        self.stats = defaultdict(int)

        # Track CTEs and temp tables across batches
        self.cte_registry: Dict[str, Dict] = {}
        self.temp_table_registry: Dict[str, Dict] = {}

        # Compile Snowflake-specific patterns
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for Snowflake-specific detection"""
        # Snowflake temp tables use TEMPORARY keyword
        self.temp_table_pattern = re.compile(r'TEMPORARY\s+TABLE\s+(\w+)', re.IGNORECASE)
        self.transient_table_pattern = re.compile(r'TRANSIENT\s+TABLE\s+(\w+)', re.IGNORECASE)

        # Variant/JSON access patterns - comprehensive
        self.variant_access = re.compile(r'(\w+):([\w\[\]\.:\'"]+)')
        self.variant_cast = re.compile(r'::(STRING|NUMBER|INTEGER|FLOAT|BOOLEAN|DATE|TIMESTAMP|VARIANT|OBJECT|ARRAY)', re.IGNORECASE)
        self.lateral_flatten = re.compile(r'LATERAL\s+FLATTEN\s*\(', re.IGNORECASE)
        self.parse_json = re.compile(r'PARSE_JSON\s*\(', re.IGNORECASE)
        self.to_variant = re.compile(r'TO_VARIANT\s*\(', re.IGNORECASE)
        self.object_construct = re.compile(r'OBJECT_CONSTRUCT\s*\(', re.IGNORECASE)
        self.array_construct = re.compile(r'ARRAY_CONSTRUCT\s*\(', re.IGNORECASE)
        self.array_agg = re.compile(r'ARRAY_AGG\s*\(', re.IGNORECASE)
        self.object_agg = re.compile(r'OBJECT_AGG\s*\(', re.IGNORECASE)

        # Time travel patterns
        self.time_travel_at = re.compile(r'AT\s*\(\s*(TIMESTAMP|OFFSET|STATEMENT)\s*=>', re.IGNORECASE)
        self.time_travel_before = re.compile(r'BEFORE\s*\(\s*(TIMESTAMP|OFFSET|STATEMENT)\s*=>', re.IGNORECASE)
        self.changes_clause = re.compile(r'CHANGES\s*\(\s*INFORMATION\s*=>', re.IGNORECASE)

        # Stream patterns
        self.stream_pattern = re.compile(r'STREAM\s+(\w+)', re.IGNORECASE)
        self.stream_has_data = re.compile(r'SYSTEM\$STREAM_HAS_DATA\s*\(', re.IGNORECASE)

        # Dynamic SQL patterns
        self.execute_immediate = re.compile(r'EXECUTE\s+IMMEDIATE', re.IGNORECASE)
        self.identifier_func = re.compile(r'IDENTIFIER\s*\(', re.IGNORECASE)

        # Result scan pattern
        self.result_scan = re.compile(r'RESULT_SCAN\s*\(', re.IGNORECASE)
        self.last_query_id = re.compile(r'LAST_QUERY_ID\s*\(', re.IGNORECASE)

        # Window functions and analytics
        self.qualify_clause = re.compile(r'\bQUALIFY\b', re.IGNORECASE)
        self.window_frame = re.compile(r'(ROWS|RANGE)\s+BETWEEN', re.IGNORECASE)
        self.match_recognize = re.compile(r'MATCH_RECOGNIZE\s*\(', re.IGNORECASE)

        # Generator and sequence
        self.generator = re.compile(r'GENERATOR\s*\(', re.IGNORECASE)
        self.seq_nextval = re.compile(r'(\w+)\.NEXTVAL', re.IGNORECASE)

        # Geospatial functions
        self.geo_functions = re.compile(r'(ST_\w+|TO_GEOGRAPHY|TO_GEOMETRY)\s*\(', re.IGNORECASE)

        # Data sharing
        self.share_pattern = re.compile(r'(CREATE|ALTER|DROP)\s+SHARE', re.IGNORECASE)
        self.secure_view = re.compile(r'SECURE\s+VIEW', re.IGNORECASE)

        # External tables and stages
        self.external_table = re.compile(r'EXTERNAL\s+TABLE', re.IGNORECASE)
        self.stage_pattern = re.compile(r'@[\w\.\/]+', re.IGNORECASE)
        self.copy_into = re.compile(r'COPY\s+INTO', re.IGNORECASE)
        self.file_format = re.compile(r'FILE_FORMAT\s*=', re.IGNORECASE)

        # Clustering and search optimization
        self.cluster_by = re.compile(r'CLUSTER\s+BY', re.IGNORECASE)
        self.search_optimization = re.compile(r'SEARCH\s+OPTIMIZATION', re.IGNORECASE)

        # Materialized views
        self.materialized_view = re.compile(r'MATERIALIZED\s+VIEW', re.IGNORECASE)

        # Data masking and row access policies
        self.masking_policy = re.compile(r'MASKING\s+POLICY', re.IGNORECASE)
        self.row_access_policy = re.compile(r'ROW\s+ACCESS\s+POLICY', re.IGNORECASE)

        # Tags
        self.tag_pattern = re.compile(r'TAG\s*\(', re.IGNORECASE)

        # Stored procedure language
        self.javascript_body = re.compile(r'\$\$.*?\$\$', re.DOTALL)
        self.python_handler = re.compile(r'HANDLER\s*=\s*[\'"]\w+[\'"]', re.IGNORECASE)
        self.java_handler = re.compile(r'LANGUAGE\s+JAVA', re.IGNORECASE)

        # Sampling
        self.sample_clause = re.compile(r'SAMPLE\s*\(', re.IGNORECASE)
        self.tablesample = re.compile(r'TABLESAMPLE\s*\(', re.IGNORECASE)

        # Pivot/Unpivot
        self.pivot_clause = re.compile(r'\bPIVOT\s*\(', re.IGNORECASE)
        self.unpivot_clause = re.compile(r'\bUNPIVOT\s*\(', re.IGNORECASE)

        # Connect by (hierarchical queries)
        self.connect_by = re.compile(r'CONNECT\s+BY', re.IGNORECASE)

        # IFF and other Snowflake functions
        self.iff_function = re.compile(r'\bIFF\s*\(', re.IGNORECASE)
        self.nullif_function = re.compile(r'\bNULLIF\s*\(', re.IGNORECASE)
        self.zeroifnull = re.compile(r'\bZEROIFNULL\s*\(', re.IGNORECASE)
        self.nvl_function = re.compile(r'\bNVL\s*\(', re.IGNORECASE)
        self.nvl2_function = re.compile(r'\bNVL2\s*\(', re.IGNORECASE)
        self.decode_function = re.compile(r'\bDECODE\s*\(', re.IGNORECASE)

        # Date/Time functions specific to Snowflake
        self.dateadd = re.compile(r'\bDATEADD\s*\(', re.IGNORECASE)
        self.datediff = re.compile(r'\bDATEDIFF\s*\(', re.IGNORECASE)
        self.date_trunc = re.compile(r'\bDATE_TRUNC\s*\(', re.IGNORECASE)
        self.time_slice = re.compile(r'\bTIME_SLICE\s*\(', re.IGNORECASE)
        self.convert_timezone = re.compile(r'\bCONVERT_TIMEZONE\s*\(', re.IGNORECASE)

        # String functions
        self.split_part = re.compile(r'\bSPLIT_PART\s*\(', re.IGNORECASE)
        self.strtok = re.compile(r'\bSTRTOK\s*\(', re.IGNORECASE)
        self.regexp_replace = re.compile(r'\bREGEXP_REPLACE\s*\(', re.IGNORECASE)
        self.regexp_substr = re.compile(r'\bREGEXP_SUBSTR\s*\(', re.IGNORECASE)

        # Conditional expressions
        self.try_cast = re.compile(r'\bTRY_CAST\s*\(', re.IGNORECASE)
        self.try_to_number = re.compile(r'\bTRY_TO_\w+\s*\(', re.IGNORECASE)

        # Hash functions
        self.hash_function = re.compile(r'\bHASH\s*\(', re.IGNORECASE)
        self.md5_function = re.compile(r'\bMD5\s*\(', re.IGNORECASE)
        self.sha_function = re.compile(r'\bSHA\d*\s*\(', re.IGNORECASE)

        # Encryption
        self.encrypt_function = re.compile(r'\b(ENCRYPT|DECRYPT)\s*\(', re.IGNORECASE)

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
            # Parse with Snowflake dialect and lenient error handling
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

        return StatementLineage(
            file_path=file_path,
            statement_type="MERGE",
            target_table=target_table,
            source_tables=list(set(source_tables)),
            column_lineage=column_lineage,
            cte_definitions=cte_definitions
        )

    def _analyze_create(self, tree: exp.Create, file_path: str, cte_definitions: Dict) -> StatementLineage:
        """Analyze CREATE TABLE/VIEW/FUNCTION (including CTAS)"""
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

        # Determine if this is a temp table (Snowflake uses TEMPORARY keyword)
        temp_tables = []
        sql_text = tree.sql().upper()
        if 'TEMPORARY' in sql_text or 'TRANSIENT' in sql_text:
            temp_tables = [target_table] if target_table else []

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

        # Check for SELECT INTO (less common in Snowflake)
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

        return StatementLineage(
            file_path=file_path,
            statement_type="SELECT",
            statement_subtype=stmt_subtype,
            target_table=target_table,
            source_tables=source_tables,
            column_lineage=column_lineage,
            cte_definitions=cte_definitions,
            temp_tables=[]
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
        """Get statement subtype with Snowflake-specific patterns"""
        sql_upper = sql.upper()

        # Snowflake CTAS patterns
        if 'CREATE' in sql_upper and 'AS' in sql_upper and 'SELECT' in sql_upper:
            if 'MATERIALIZED' in sql_upper and 'VIEW' in sql_upper:
                return "CREATE_MATERIALIZED_VIEW"
            if 'TABLE' in sql_upper:
                return "CTAS"
            if 'VIEW' in sql_upper:
                return "CREATE_VIEW"

        if isinstance(tree, exp.Insert) and tree.expression and isinstance(tree.expression, exp.Select):
            return "INSERT_SELECT"

        # Set operations
        if 'UNION' in sql_upper:
            return "UNION"
        if 'INTERSECT' in sql_upper:
            return "INTERSECT"
        if 'EXCEPT' in sql_upper or 'MINUS' in sql_upper:
            return "EXCEPT"

        # Snowflake-specific patterns - Semi-structured data
        if self.lateral_flatten.search(sql):
            return "LATERAL_FLATTEN"
        if self.parse_json.search(sql):
            return "PARSE_JSON"
        if self.object_construct.search(sql) or self.array_construct.search(sql):
            return "CONSTRUCT_OBJECT"

        # Time travel and versioning
        if self.time_travel_at.search(sql) or self.time_travel_before.search(sql):
            return "TIME_TRAVEL"
        if self.changes_clause.search(sql):
            return "CHANGES"

        # Result scan and metadata
        if self.result_scan.search(sql):
            return "RESULT_SCAN"
        if self.last_query_id.search(sql):
            return "QUERY_METADATA"

        # Window functions and analytics
        if self.qualify_clause.search(sql):
            return "QUALIFY"
        if self.match_recognize.search(sql):
            return "MATCH_RECOGNIZE"

        # Data loading
        if self.copy_into.search(sql):
            return "COPY_INTO"
        if self.stage_pattern.search(sql):
            return "STAGE_REFERENCE"

        # Pivot/Unpivot
        if self.pivot_clause.search(sql):
            return "PIVOT"
        if self.unpivot_clause.search(sql):
            return "UNPIVOT"

        # Hierarchical queries
        if self.connect_by.search(sql):
            return "CONNECT_BY"

        # Sampling
        if self.sample_clause.search(sql) or self.tablesample.search(sql):
            return "SAMPLE"

        # Generator
        if self.generator.search(sql):
            return "GENERATOR"

        # Geospatial
        if self.geo_functions.search(sql):
            return "GEOSPATIAL"

        # External tables
        if self.external_table.search(sql):
            return "EXTERNAL_TABLE"

        # Secure views
        if self.secure_view.search(sql):
            return "SECURE_VIEW"

        # Streams
        if self.stream_has_data.search(sql):
            return "STREAM_CHECK"

        # Policies
        if self.masking_policy.search(sql):
            return "MASKING_POLICY"
        if self.row_access_policy.search(sql):
            return "ROW_ACCESS_POLICY"

        return None

    def _extract_target_table(self, tree: exp.Expression) -> Optional[str]:
        """Extract target table"""
        if isinstance(tree, (exp.Create, exp.Insert, exp.Update, exp.Delete, exp.Merge)):
            table_node = tree.find(exp.Table)
            if table_node:
                return self._get_full_table_name(table_node)

        return None

    def _get_full_table_name(self, table: exp.Table) -> str:
        """Get fully qualified table name (Snowflake: database.schema.table)"""
        parts = []
        if table.catalog:
            parts.append(str(table.catalog).strip('"'))
        if table.db:
            parts.append(str(table.db).strip('"'))
        parts.append(str(table.name).strip('"'))
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

        # Get table-valued functions (like FLATTEN, GENERATOR, etc.)
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

        # Handle Snowflake variant access (JSON path notation)
        sql_text = expr.sql()
        for match in self.variant_access.finditer(sql_text):
            col_name = match.group(1)
            json_path = match.group(2)
            sources.append({
                "table": "unknown",
                "column": f"{col_name}:{json_path}",
                "cte_reference": None,
                "is_variant": True
            })

        return sources

    def _build_alias_map(self, tree: exp.Expression) -> Dict[str, str]:
        """Build a mapping from table aliases to fully qualified base table names."""
        alias_map: Dict[str, str] = {}
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

    def _classify_transform(self, expr: exp.Expression) -> str:
        """Classify transformation type with Snowflake-specific patterns"""
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
            # Check for Snowflake-specific functions
            func = expr.find(exp.Func)
            func_name = func.name.upper() if func else ""

            # Semi-structured data functions
            if func_name in ('PARSE_JSON', 'TO_JSON', 'TO_VARIANT', 'TRY_PARSE_JSON'):
                return "json_parse"
            elif func_name in ('OBJECT_CONSTRUCT', 'OBJECT_CONSTRUCT_KEEP_NULL'):
                return "object_construct"
            elif func_name in ('ARRAY_CONSTRUCT', 'ARRAY_CONSTRUCT_COMPACT'):
                return "array_construct"
            elif func_name in ('FLATTEN', 'LATERAL'):
                return "flatten"
            elif func_name in ('ARRAY_AGG', 'OBJECT_AGG', 'ARRAYAGG', 'OBJECTAGG'):
                return "array_aggregate"
            elif func_name in ('GET', 'GET_PATH', 'OBJECT_KEYS', 'ARRAY_SIZE', 'ARRAY_SLICE'):
                return "semi_structured_access"

            # Geospatial functions
            elif func_name.startswith('ST_') or func_name in ('TO_GEOGRAPHY', 'TO_GEOMETRY'):
                return "geospatial"

            # Window functions
            elif func_name in ('ROW_NUMBER', 'RANK', 'DENSE_RANK', 'NTILE', 'LAG', 'LEAD',
                              'FIRST_VALUE', 'LAST_VALUE', 'NTH_VALUE', 'CUME_DIST', 'PERCENT_RANK'):
                return "window_function"

            # Conditional functions
            elif func_name in ('IFF', 'NULLIF', 'ZEROIFNULL', 'NVL', 'NVL2', 'DECODE',
                              'IFNULL', 'COALESCE', 'GREATEST', 'LEAST'):
                return "conditional"

            # Date/Time functions
            elif func_name in ('DATEADD', 'DATEDIFF', 'DATE_TRUNC', 'TIME_SLICE',
                              'CONVERT_TIMEZONE', 'TIMESTAMPADD', 'TIMESTAMPDIFF',
                              'DATE_PART', 'DAYOFWEEK', 'DAYOFYEAR', 'WEEKOFYEAR',
                              'LAST_DAY', 'NEXT_DAY', 'PREVIOUS_DAY', 'ADD_MONTHS'):
                return "date_function"

            # String functions
            elif func_name in ('SPLIT_PART', 'STRTOK', 'STRTOK_TO_ARRAY', 'SPLIT',
                              'REGEXP_REPLACE', 'REGEXP_SUBSTR', 'REGEXP_COUNT', 'REGEXP_INSTR',
                              'TRIM', 'LTRIM', 'RTRIM', 'LPAD', 'RPAD', 'REPEAT',
                              'REVERSE', 'TRANSLATE', 'INITCAP', 'SOUNDEX', 'EDITDISTANCE'):
                return "string_function"

            # Conversion functions
            elif func_name in ('TRY_CAST', 'TRY_TO_NUMBER', 'TRY_TO_DECIMAL', 'TRY_TO_DOUBLE',
                              'TRY_TO_DATE', 'TRY_TO_TIMESTAMP', 'TRY_TO_BINARY', 'TRY_TO_BOOLEAN',
                              'TO_CHAR', 'TO_VARCHAR', 'TO_NUMBER', 'TO_DECIMAL', 'TO_DOUBLE',
                              'TO_DATE', 'TO_TIMESTAMP', 'TO_TIME', 'TO_BINARY', 'TO_BOOLEAN'):
                return "conversion"

            # Hash and encryption
            elif func_name in ('HASH', 'MD5', 'MD5_HEX', 'SHA1', 'SHA1_HEX', 'SHA2',
                              'SHA2_HEX', 'ENCRYPT', 'DECRYPT', 'ENCRYPT_RAW', 'DECRYPT_RAW'):
                return "hash_encrypt"

            # Aggregate functions
            elif func_name in ('LISTAGG', 'MEDIAN', 'MODE', 'PERCENTILE_CONT', 'PERCENTILE_DISC',
                              'STDDEV', 'STDDEV_POP', 'STDDEV_SAMP', 'VARIANCE', 'VAR_POP', 'VAR_SAMP',
                              'CORR', 'COVAR_POP', 'COVAR_SAMP', 'REGR_SLOPE', 'REGR_INTERCEPT',
                              'APPROX_COUNT_DISTINCT', 'HLL', 'HLL_ACCUMULATE', 'HLL_COMBINE',
                              'APPROX_PERCENTILE', 'APPROX_TOP_K', 'MINHASH', 'MINHASH_COMBINE'):
                return "advanced_aggregate"

            # Bitwise functions
            elif func_name in ('BITAND', 'BITOR', 'BITXOR', 'BITNOT', 'BITSHIFTLEFT', 'BITSHIFTRIGHT'):
                return "bitwise"

            # System functions
            elif func_name in ('CURRENT_USER', 'CURRENT_ROLE', 'CURRENT_WAREHOUSE', 'CURRENT_DATABASE',
                              'CURRENT_SCHEMA', 'CURRENT_SESSION', 'CURRENT_STATEMENT',
                              'SYSTEM$TYPEOF', 'SYSTEM$CLUSTERING_INFORMATION'):
                return "system_function"

            # Table functions
            elif func_name in ('GENERATOR', 'RESULT_SCAN', 'VALIDATE', 'INFER_SCHEMA',
                              'SPLIT_TO_TABLE', 'STRTOK_SPLIT_TO_TABLE'):
                return "table_function"

            return "function"
        elif expr.find(exp.Subquery):
            return "subquery"
        elif expr.find(exp.Window):
            return "window"

        # Check for variant access pattern in expression text
        sql_text = expr.sql()
        if ':' in sql_text and '::' not in sql_text.replace('::', ''):
            return "variant_access"

        return "expression"

    def _is_aggregate(self, expr: exp.Expression) -> bool:
        """Check if expression contains aggregates"""
        agg_funcs = [exp.Sum, exp.Count, exp.Avg, exp.Max, exp.Min, exp.AggFunc]
        return any(expr.find(agg) for agg in agg_funcs)

    def _is_calculated(self, expr: exp.Expression) -> bool:
        """Check if expression is calculated (not direct column reference)"""
        return not isinstance(expr, exp.Column)

    def _is_dynamic_sql(self, sql: str) -> bool:
        """Check if SQL is dynamic (Snowflake uses EXECUTE IMMEDIATE)"""
        return bool(self.execute_immediate.search(sql))

    def _extract_temp_table_names(self, table_name: Optional[str]) -> List[str]:
        """Extract temp table names (Snowflake uses TEMPORARY keyword, not #)"""
        if not table_name:
            return []
        return []  # Snowflake temp tables are identified by keyword, not naming


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
