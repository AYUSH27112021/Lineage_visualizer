"""
Metadata View Analyzer for Teradata
Analyzes views and query history SQL using traditional parsing (sqlglot).

This module provides the same analysis capabilities as EnhancedSQLAnalyzer
but optimized for working with database metadata instead of SQL files.

Teradata-specific features:
- QUALIFY clauses for window function filtering
- SAMPLE clauses for data sampling
- Teradata outer join syntax (+)
- MULTISET/SET specifications
- VOLATILE and GLOBAL TEMPORARY table references
- TOP N syntax
- Named expressions and TITLE clauses
- COLLECT STATISTICS statements
- Teradata-specific functions (TRIM, SUBSTR, etc.)
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
    has_qualify: bool = False
    has_sample: bool = False


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
    volatile_tables: List[str] = field(default_factory=list)
    is_dynamic: bool = False
    parse_error: Optional[str] = None
    statement_subtype: Optional[str] = None
    teradata_features: List[str] = field(default_factory=list)


class MetadataViewAnalyzer:
    """
    Analyze views and query history SQL extracted from Teradata metadata.

    Uses sqlglot for traditional parsing with full schema context from metadata.
    """

    def __init__(
        self,
        dialect: str = "teradata",
        metadata: Optional[Dict] = None,
        debug: bool = False
    ):
        """
        Initialize the analyzer.

        Args:
            dialect: SQL dialect (default: teradata)
            metadata: Database metadata for schema context
            debug: Enable debug output
        """
        self.dialect = dialect
        self.metadata = metadata or {}
        self.debug = debug

        # Build table and column lookup from metadata
        self.table_lookup = self._build_table_lookup()
        self.column_lookup = self._build_column_lookup()

        # Track volatile and temp tables
        self.volatile_table_registry: Dict[str, Dict] = {}
        self.temp_table_registry: Dict[str, Dict] = {}

        # Statistics
        self.stats = defaultdict(int)

        # Compile Teradata-specific patterns
        self._compile_patterns()

    def _build_table_lookup(self) -> Dict[str, Dict]:
        """Build lookup dictionary for table names."""
        lookup = {}

        for table in self.metadata.get('tables', []):
            database = table.get('database', 'DBC')
            schema = table.get('schema', database)
            name = table.get('name')

            if name:
                # Store with multiple key variations for flexible matching
                qualified_name = f"{database}.{name}"
                lookup[name.lower()] = {'database': database, 'schema': schema, 'name': name, 'qualified': qualified_name}
                lookup[qualified_name.lower()] = {'database': database, 'schema': schema, 'name': name, 'qualified': qualified_name}

                # Also store schema.name format
                schema_qualified = f"{schema}.{name}"
                lookup[schema_qualified.lower()] = {'database': database, 'schema': schema, 'name': name, 'qualified': qualified_name}

        # Also include views in lookup
        for view in self.metadata.get('views', []):
            database = view.get('database_name', 'DBC')
            schema = view.get('schema_name', database)
            name = view.get('view_name')

            if name:
                qualified_name = f"{database}.{name}"
                lookup[name.lower()] = {'database': database, 'schema': schema, 'name': name, 'qualified': qualified_name, 'is_view': True}
                lookup[qualified_name.lower()] = {'database': database, 'schema': schema, 'name': name, 'qualified': qualified_name, 'is_view': True}

                schema_qualified = f"{schema}.{name}"
                lookup[schema_qualified.lower()] = {'database': database, 'schema': schema, 'name': name, 'qualified': qualified_name, 'is_view': True}

        return lookup

    def _build_column_lookup(self) -> Dict[str, Set[str]]:
        """Build lookup of columns per table."""
        lookup = defaultdict(set)

        for table in self.metadata.get('tables', []):
            database = table.get('database', 'DBC')
            name = table.get('name')
            qualified_name = f"{database}.{name}"

            for col in table.get('columns', []):
                col_name = col.get('name') or col.get('column_name')
                if col_name:
                    lookup[qualified_name.lower()].add(col_name.lower())
                    lookup[name.lower()].add(col_name.lower())

        return dict(lookup)

    def _compile_patterns(self):
        """Compile regex patterns for Teradata-specific detection."""
        # Teradata temporary tables
        self.volatile_table = re.compile(
            r'(?:CREATE\s+)?(?:MULTISET\s+|SET\s+)?VOLATILE\s+TABLE\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.global_temp = re.compile(
            r'CREATE\s+(?:MULTISET\s+|SET\s+)?GLOBAL\s+TEMPORARY\s+TABLE\s+([\w\.\"]+)',
            re.IGNORECASE
        )

        # Teradata-style outer joins (old syntax)
        # e.g., table1.col = table2.col(+) or table1.col(+) = table2.col
        self.td_outer_join = re.compile(
            r'(\w+\.\w+)\s*\(\+\)\s*=\s*(\w+\.\w+)|(\w+\.\w+)\s*=\s*(\w+\.\w+)\s*\(\+\)',
            re.IGNORECASE
        )

        # QUALIFY clause (Teradata-specific for window function filtering)
        self.qualify_clause = re.compile(r'\bQUALIFY\b', re.IGNORECASE)

        # SAMPLE clause (Teradata sampling)
        self.sample_clause = re.compile(r'\bSAMPLE\s+\d+', re.IGNORECASE)

        # TOP N syntax
        self.top_n = re.compile(r'\bSEL(?:ECT)?\s+TOP\s+\d+\b', re.IGNORECASE)

        # COLLECT STATISTICS
        self.collect_stats = re.compile(
            r'COLLECT\s+(?:STATISTICS|STAT)\s+(?:ON|FOR)',
            re.IGNORECASE
        )

        # Teradata-specific keywords
        self.named_expr = re.compile(r'\bNAMED\b', re.IGNORECASE)
        self.title_clause = re.compile(r'\bTITLE\b', re.IGNORECASE)

        # MULTISET/SET keywords
        self.multiset = re.compile(r'\bMULTISET\b', re.IGNORECASE)
        self.set_table = re.compile(r'\bSET\s+TABLE\b', re.IGNORECASE)

        # Teradata-specific functions
        self.td_functions = re.compile(
            r'\b(SUBSTR|TRIM|ZEROIFNULL|NULLIFZERO|CASESPECIFIC|CHARACTERS|BYTES|'
            r'CAST\s+\(.*?\s+AS\s+FORMAT|HASHROW|HASHAMP|HASHBUCKET|RANDOM|'
            r'ACCOUNT|PROFILE|USER|DATABASE|ROLE)\s*\(',
            re.IGNORECASE
        )

        # Dynamic SQL
        self.execute_immediate = re.compile(r'EXECUTE\s+IMMEDIATE', re.IGNORECASE)
        self.using_clause = re.compile(r'\bUSING\b', re.IGNORECASE)

        # Merge operations
        self.merge_into = re.compile(r'MERGE\s+INTO', re.IGNORECASE)

        # Macro definitions
        self.create_macro = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?MACRO', re.IGNORECASE)

        # Fast export/load patterns
        self.fast_export = re.compile(r'\.EXPORT\s+', re.IGNORECASE)
        self.fast_load = re.compile(r'\.IMPORT\s+', re.IGNORECASE)

        # Recursive queries
        self.recursive_cte = re.compile(r'WITH\s+RECURSIVE', re.IGNORECASE)

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
                'volatile_tables': [],
                'is_dynamic': self._is_dynamic_sql(sql),
                'teradata_features': self._detect_teradata_features_list(sql)
            }

    def analyze_views(self, views: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze multiple views and build dependency graph.

        Args:
            views: List of view dictionaries with 'name' and 'definition' keys

        Returns:
            Dictionary containing:
                - view_lineages: List of lineage results for each view
                - dependency_graph: Graph showing view dependencies
                - statistics: Analysis statistics
        """
        view_lineages = []
        dependency_graph = {}

        for view in views:
            view_name = view.get('view_name') or view.get('name')
            view_def = view.get('view_definition') or view.get('definition')

            if not view_name or not view_def:
                continue

            # Analyze the view
            lineage = self.analyze_sql(view_def, view_name, "VIEW")
            view_lineages.append(lineage)

            # Add to dependency graph
            dependency_graph[view_name] = {
                'source_tables': lineage.get('source_tables', []),
                'target_table': lineage.get('target_table', view_name),
                'type': 'VIEW',
                'has_error': lineage.get('parse_error') is not None
            }

        # Build the full dependency graph
        full_graph = self._build_dependency_graph(dependency_graph)

        return {
            'view_lineages': view_lineages,
            'dependency_graph': full_graph,
            'statistics': dict(self.stats)
        }

    def _analyze_statement(
        self,
        sql: str,
        name: str,
        sql_type: str
    ) -> ViewLineage:
        """Analyze a single SQL statement."""
        try:
            # Parse with Teradata dialect and lenient error handling
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

            # Detect Teradata features
            td_features = self._detect_teradata_features_list(sql)

            # Extract CTEs first
            cte_definitions = self._extract_ctes(tree)

            # Extract target table (for views, this is the view name)
            if sql_type == "VIEW":
                target_table = name
            else:
                target_table = self._extract_target_table(tree)

            # Extract source tables
            source_tables = self._extract_source_tables(tree)

            # Extract volatile and temp tables
            volatile_tables = self._extract_volatile_tables(sql)
            temp_tables = self._extract_temp_tables(sql)

            # Build alias map for column resolution
            alias_map = self._build_alias_map(tree)

            # Extract column lineage
            column_lineage = self._extract_column_lineage(
                tree, target_table, cte_definitions, alias_map, sql
            )

            return ViewLineage(
                name=name,
                sql_type=sql_type,
                target_table=target_table,
                source_tables=source_tables,
                column_lineage=column_lineage,
                cte_definitions=cte_definitions,
                temp_tables=temp_tables,
                volatile_tables=volatile_tables,
                is_dynamic=self._is_dynamic_sql(sql),
                statement_subtype=stmt_subtype,
                teradata_features=td_features
            )

        except Exception as e:
            return ViewLineage(
                name=name,
                sql_type=sql_type,
                parse_error=str(e)
            )

    def _analyze_single_view(
        self,
        view_name: str,
        view_definition: str
    ) -> Dict[str, Any]:
        """
        Analyze a single view definition.

        Args:
            view_name: Name of the view
            view_definition: SQL definition of the view

        Returns:
            Analysis result dictionary
        """
        return self.analyze_sql(view_definition, view_name, "VIEW")

    def _extract_view_lineage(
        self,
        tree: exp.Expression,
        view_name: str
    ) -> Dict[str, Any]:
        """
        Extract complete lineage from a view definition.

        Args:
            tree: Parsed SQL expression tree
            view_name: Name of the view

        Returns:
            Dictionary with source tables, column mappings, and CTEs
        """
        # Extract CTEs
        cte_definitions = self._extract_ctes(tree)

        # Extract source tables
        source_tables = self._extract_source_tables(tree)

        # Build alias map
        alias_map = self._build_alias_map(tree)

        # Extract column mappings
        column_lineage = self._extract_column_lineage(
            tree, view_name, cte_definitions, alias_map, tree.sql()
        )

        return {
            'view_name': view_name,
            'source_tables': source_tables,
            'column_lineage': column_lineage,
            'cte_definitions': cte_definitions
        }

    def _extract_column_mappings(
        self,
        tree: exp.Expression,
        target_table: str,
        cte_definitions: Dict,
        alias_map: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Extract column-level mappings from source to target.

        Args:
            tree: Parsed SQL expression tree
            target_table: Name of the target table/view
            cte_definitions: Dictionary of CTE definitions
            alias_map: Mapping of table aliases

        Returns:
            List of column mapping dictionaries
        """
        mappings = []

        # Find the SELECT statement
        select = self._find_select_statement(tree)
        if not select:
            return mappings

        for i, projection in enumerate(select.expressions):
            output_col = projection.alias_or_name or f"column_{i}"

            # Find source columns
            source_cols = self._find_source_columns(projection, cte_definitions, alias_map)

            # Classify transformation
            transform_type = self._classify_transform(projection)

            mappings.append({
                'target_column': output_col,
                'target_table': target_table,
                'source_columns': source_cols,
                'transform_type': transform_type,
                'expression': projection.sql()[:200],
                'is_aggregate': self._is_aggregate(projection),
                'is_calculated': self._is_calculated(projection)
            })

        return mappings

    def _build_dependency_graph(self, initial_graph: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Build a complete dependency graph showing view relationships.

        Args:
            initial_graph: Initial graph with direct dependencies

        Returns:
            Enhanced graph with levels, cycles, and ordering information
        """
        graph = {}
        view_levels = {}

        # Build adjacency lists
        for view_name, info in initial_graph.items():
            dependencies = []
            for source in info.get('source_tables', []):
                if source in initial_graph:  # Only track view-to-view dependencies
                    dependencies.append(source)

            graph[view_name] = {
                'dependencies': dependencies,
                'dependents': [],
                'level': 0,
                'info': info
            }

        # Build reverse dependencies (dependents)
        for view_name, node in graph.items():
            for dep in node['dependencies']:
                if dep in graph:
                    graph[dep]['dependents'].append(view_name)

        # Calculate levels (topological ordering)
        visited = set()
        temp_visited = set()
        has_cycle = False

        def calculate_level(view: str) -> int:
            nonlocal has_cycle

            if view in temp_visited:
                has_cycle = True
                return 0

            if view in visited:
                return view_levels.get(view, 0)

            temp_visited.add(view)

            max_dep_level = -1
            for dep in graph[view]['dependencies']:
                if dep in graph:
                    dep_level = calculate_level(dep)
                    max_dep_level = max(max_dep_level, dep_level)

            temp_visited.remove(view)
            visited.add(view)

            level = max_dep_level + 1
            view_levels[view] = level
            graph[view]['level'] = level

            return level

        # Calculate levels for all views
        for view_name in graph:
            if view_name not in visited:
                calculate_level(view_name)

        # Sort views by level
        sorted_views = sorted(graph.keys(), key=lambda v: graph[v]['level'])

        return {
            'graph': graph,
            'sorted_views': sorted_views,
            'has_cycle': has_cycle,
            'max_level': max(view_levels.values()) if view_levels else 0,
            'total_views': len(graph)
        }

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
        """Get statement subtype with Teradata-specific patterns."""
        sql_upper = sql.upper()

        if 'CREATE' in sql_upper and 'AS' in sql_upper and 'SELECT' in sql_upper:
            return "CTAS"

        if isinstance(tree, exp.Insert) and tree.expression and isinstance(tree.expression, exp.Select):
            return "INSERT_SELECT"

        if 'UNION' in sql_upper:
            return "UNION"

        if 'INTERSECT' in sql_upper:
            return "INTERSECT"

        if 'EXCEPT' in sql_upper or 'MINUS' in sql_upper:
            return "EXCEPT"

        if self.qualify_clause.search(sql):
            return "QUALIFY"

        if self.sample_clause.search(sql):
            return "SAMPLE"

        if self.merge_into.search(sql):
            return "MERGE"

        if self.recursive_cte.search(sql):
            return "RECURSIVE_CTE"

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
            parts.append(str(table.catalog).strip('"'))
        if table.db:
            parts.append(str(table.db).strip('"'))
        parts.append(str(table.name).strip('"'))

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

    def _extract_volatile_tables(self, sql: str) -> List[str]:
        """Extract volatile table names from SQL."""
        volatile_tables = []

        for match in self.volatile_table.finditer(sql):
            table_name = match.group(1).strip('"')
            if table_name not in volatile_tables:
                volatile_tables.append(table_name)
                self.volatile_table_registry[table_name] = {'sql': sql[:200]}

        return volatile_tables

    def _extract_temp_tables(self, sql: str) -> List[str]:
        """Extract global temporary table names from SQL."""
        temp_tables = []

        for match in self.global_temp.finditer(sql):
            table_name = match.group(1).strip('"')
            if table_name not in temp_tables:
                temp_tables.append(table_name)
                self.temp_table_registry[table_name] = {'sql': sql[:200]}

        return temp_tables

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

    def _find_select_statement(self, tree: exp.Expression) -> Optional[exp.Select]:
        """Find the main SELECT statement in the tree."""
        if isinstance(tree, exp.Select):
            return tree
        elif isinstance(tree, exp.Create):
            return tree.find(exp.Select)
        elif isinstance(tree, exp.Insert):
            return tree.expression if isinstance(tree.expression, exp.Select) else None

        return tree.find(exp.Select)

    def _extract_column_lineage(
        self,
        tree: exp.Expression,
        target_table: Optional[str],
        cte_definitions: Dict,
        alias_map: Dict[str, str],
        sql: str
    ) -> List[ColumnLineage]:
        """Extract column-level lineage."""
        column_lineage = []

        # Find the SELECT statement(s)
        select = self._find_select_statement(tree)

        if not select:
            return column_lineage

        # Check for QUALIFY and SAMPLE in SQL
        has_qualify = bool(self.qualify_clause.search(sql))
        has_sample = bool(self.sample_clause.search(sql))

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
                is_calculated=self._is_calculated(projection),
                has_qualify=has_qualify,
                has_sample=has_sample
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
        return bool(self.execute_immediate.search(sql))

    def _detect_teradata_features_list(self, sql: str) -> List[str]:
        """Detect Teradata-specific features in SQL and return as list."""
        features = []

        if self.volatile_table.search(sql):
            features.append('volatile_table')
        if self.global_temp.search(sql):
            features.append('global_temporary_table')
        if self.td_outer_join.search(sql):
            features.append('teradata_outer_join')
        if self.qualify_clause.search(sql):
            features.append('qualify_clause')
        if self.sample_clause.search(sql):
            features.append('sample_clause')
        if self.top_n.search(sql):
            features.append('top_n')
        if self.collect_stats.search(sql):
            features.append('collect_statistics')
        if self.named_expr.search(sql):
            features.append('named_expression')
        if self.title_clause.search(sql):
            features.append('title_clause')
        if self.multiset.search(sql):
            features.append('multiset')
        if self.set_table.search(sql):
            features.append('set_table')
        if self.td_functions.search(sql):
            features.append('teradata_functions')
        if self.merge_into.search(sql):
            features.append('merge_into')
        if self.create_macro.search(sql):
            features.append('macro')
        if self.recursive_cte.search(sql):
            features.append('recursive_cte')

        return features

    def _detect_teradata_features(self, sql: str) -> Dict[str, bool]:
        """Detect Teradata-specific features in SQL."""
        return {
            'has_volatile_table': bool(self.volatile_table.search(sql)),
            'has_global_temp': bool(self.global_temp.search(sql)),
            'has_td_outer_join': bool(self.td_outer_join.search(sql)),
            'has_qualify': bool(self.qualify_clause.search(sql)),
            'has_sample': bool(self.sample_clause.search(sql)),
            'has_top_n': bool(self.top_n.search(sql)),
            'has_collect_stats': bool(self.collect_stats.search(sql)),
            'has_named': bool(self.named_expr.search(sql)),
            'has_title': bool(self.title_clause.search(sql)),
            'has_multiset': bool(self.multiset.search(sql)),
            'has_set_table': bool(self.set_table.search(sql)),
            'has_td_functions': bool(self.td_functions.search(sql)),
            'has_merge': bool(self.merge_into.search(sql)),
            'has_macro': bool(self.create_macro.search(sql)),
            'has_recursive_cte': bool(self.recursive_cte.search(sql))
        }

    def _lineage_to_dict(self, lineage: ViewLineage) -> Dict[str, Any]:
        """Convert ViewLineage to dictionary."""
        # Get the original SQL for feature detection
        sql_for_detection = ""
        if lineage.column_lineage:
            sql_for_detection = lineage.column_lineage[0].expression

        # Detect Teradata features
        teradata_features = self._detect_teradata_features(sql_for_detection)

        result = {
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
                    'cte_dependency': cl.cte_dependency,
                    'has_qualify': cl.has_qualify,
                    'has_sample': cl.has_sample
                }
                for cl in lineage.column_lineage
            ],
            'cte_definitions': lineage.cte_definitions,
            'temp_tables': lineage.temp_tables,
            'volatile_tables': lineage.volatile_tables,
            'is_dynamic': lineage.is_dynamic,
            'parse_error': lineage.parse_error,
            'statement_subtype': lineage.statement_subtype,
            'analysis_success': lineage.parse_error is None,
            'teradata_features': lineage.teradata_features,
            # Teradata-specific feature flags
            **teradata_features
        }

        return result

    def get_statistics(self) -> Dict[str, Any]:
        """Get analysis statistics."""
        return {
            'total_analyzed': self.stats['total_analyzed'],
            'successful_parses': self.stats['successful_parses'],
            'parse_errors': self.stats['parse_errors'],
            'success_rate': (
                self.stats['successful_parses'] / self.stats['total_analyzed']
                if self.stats['total_analyzed'] > 0 else 0
            ),
            'volatile_tables_found': len(self.volatile_table_registry),
            'temp_tables_found': len(self.temp_table_registry)
        }


if __name__ == "__main__":
    analyzer = MetadataViewAnalyzer(debug=True)

    test_sql = """
    CREATE VIEW vw_customer_orders AS
    SELECT TOP 100
        c.customer_id,
        c.customer_name,
        COUNT(o.order_id) as order_count,
        SUM(o.total_amount) as total_spent,
        ROW_NUMBER() OVER (PARTITION BY c.customer_id ORDER BY o.order_date DESC) as rn
    FROM customers c
    LEFT JOIN orders o ON c.customer_id = o.customer_id(+)
    GROUP BY c.customer_id, c.customer_name
    QUALIFY rn <= 10
    SAMPLE 1000
    """

    result = analyzer.analyze_sql(test_sql, "vw_customer_orders", "VIEW")

    import json
    print(json.dumps(result, indent=2))
    print("\nStatistics:")
    print(json.dumps(analyzer.get_statistics(), indent=2))
