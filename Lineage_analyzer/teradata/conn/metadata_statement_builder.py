"""
Metadata Statement Builder for Teradata
Builds lineage JSON reports from analyzed views and query history.

This module produces the same output format as EnhancedLineageJSONBuilder
but works with metadata-based analysis results instead of file-based results.
Supports Teradata-specific features including volatile tables, global temporary
tables, macros, and Database.TableName format.
"""

import json
import re
from typing import Dict, List, Any, Set, Tuple, Optional
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ColumnInfo:
    """Aggregated column information"""
    name: str
    table: str
    source_columns: Set[Tuple[str, str]] = field(default_factory=set)
    transforms: Set[str] = field(default_factory=set)
    is_derived: bool = False
    is_aggregate: bool = False
    is_calculated: bool = False
    defining_sources: Set[str] = field(default_factory=set)  # view names or query IDs
    expressions: List[str] = field(default_factory=list)
    cte_dependencies: Set[str] = field(default_factory=set)
    confidence_score: float = 1.0
    has_qualify: bool = False  # Teradata QUALIFY clause
    has_sample: bool = False   # Teradata SAMPLE clause


@dataclass
class TableInfo:
    """Aggregated table information with Teradata-specific flags"""
    table_name: str
    columns: Dict[str, ColumnInfo] = field(default_factory=dict)
    definition_sources: Set[str] = field(default_factory=set)
    definition_types: Set[str] = field(default_factory=set)
    depends_on: Set[str] = field(default_factory=set)
    is_temp: bool = False
    is_cte: bool = False
    is_view: bool = False
    is_volatile: bool = False  # Teradata VOLATILE table
    is_global_temp: bool = False  # Teradata GLOBAL TEMPORARY table
    statement_subtypes: Set[str] = field(default_factory=set)
    teradata_features: Set[str] = field(default_factory=set)  # Track TD features used


@dataclass
class CTEInfo:
    """CTE definition information"""
    name: str
    defining_source: str
    columns: List[str] = field(default_factory=list)
    source_tables: List[str] = field(default_factory=list)
    query_snippet: str = ""


@dataclass
class MacroInfo:
    """Teradata macro information"""
    name: str
    database: Optional[str] = None
    defining_source: str = ""
    parameters: List[str] = field(default_factory=list)
    referenced_tables: List[str] = field(default_factory=list)
    description: str = ""


class MetadataStatementBuilder:
    """
    Build comprehensive lineage JSON report from metadata-based analysis.

    Produces the same output format as EnhancedLineageJSONBuilder for
    frontend compatibility, with additional support for Teradata-specific
    features including volatile tables, global temporary tables, and macros.
    """

    def __init__(
        self,
        dialect: str = "teradata",
        database_name: str = "",
        metadata: Optional[Dict] = None
    ):
        """
        Initialize the builder.

        Args:
            dialect: SQL dialect (default: "teradata")
            database_name: Database name
            metadata: Database metadata for context
        """
        self.dialect = dialect
        self.database_name = database_name
        self.metadata = metadata or {}

        # Aggregation containers
        self.tables: Dict[str, TableInfo] = {}
        self.columns: Dict[str, ColumnInfo] = {}
        self.ctes: Dict[str, List[CTEInfo]] = defaultdict(list)
        self.temp_tables: Dict[str, TableInfo] = {}
        self.volatile_tables: Dict[str, TableInfo] = {}
        self.global_temp_tables: Dict[str, TableInfo] = {}
        self.macros: Dict[str, MacroInfo] = {}
        self.table_dependencies: Dict[str, Set[str]] = defaultdict(set)

        # Statistics
        self.stats = {
            'total_views': 0,
            'total_queries': 0,
            'total_statements': 0,
            'successful_parses': 0,
            'parse_errors': 0,
            'dynamic_sql_count': 0,
            'duplicate_columns_merged': 0,
            'cte_count': 0,
            'temp_table_count': 0,
            'volatile_table_count': 0,
            'global_temp_table_count': 0,
            'macro_count': 0,
            'circular_dependencies': [],
            'set_operations': 0,
            'subquery_count': 0,
            'qualify_count': 0,
            'sample_count': 0,
            'td_outer_join_count': 0,
            'collect_statistics_count': 0
        }

    @staticmethod
    def _normalize_identifier(identifier: Optional[str]) -> str:
        """Normalize database/table identifiers for consistent lookups."""
        if not identifier:
            return ""
        # Strip whitespace and common quoting characters used across dialects
        return identifier.strip().strip('"`[]').lower()

    def build_lineage_report(
        self,
        view_results: List[Dict[str, Any]],
        query_history_results: List[Dict[str, Any]]
    ) -> Dict:
        """
        Build final lineage report from analysis results.

        Args:
            view_results: List of analyzed view results
            query_history_results: List of analyzed query history results

        Returns:
            Complete lineage report dictionary
        """
        print(f"   Processing {len(view_results)} views and {len(query_history_results)} query history entries...")

        # Step 1: Process view results
        for result in view_results:
            self._process_result(result, "VIEW")
            self.stats['total_views'] += 1

        # Step 2: Process query history results
        for result in query_history_results:
            self._process_result(result, "QUERY_HISTORY")
            self.stats['total_queries'] += 1

        self.stats['total_statements'] = self.stats['total_views'] + self.stats['total_queries']

        # Step 3: Resolve CTE references
        self._resolve_cte_references()

        # Step 4: Handle volatile tables
        self._handle_volatile_tables()

        # Step 5: Deduplicate and merge conflicts
        self._deduplicate_lineages()

        # Step 6: Remove placeholder columns
        self._remove_placeholder_columns()

        # Step 7: Calculate confidence scores
        self._calculate_confidence_scores()

        # Step 8: Calculate execution order
        execution_order = self._calculate_execution_order()p

        # Step 9: Build final JSON structure
        return self._build_json_report(execution_order)

    def _build_metadata_table_lookup(self) -> Dict[str, Dict[str, Any]]:
        """
        Build lookup map for table metadata keyed by multiple identifier formats.
        Ensures we can always retrieve full column definitions for referenced tables.
        """
        lookup: Dict[str, Dict[str, Any]] = {}

        if not self.metadata or 'database' not in self.metadata:
            return lookup

        db_metadata = self.metadata.get('database', {})
        tables_metadata = db_metadata.get('tables', [])

        for table_meta in tables_metadata:
            qualified_name = self._normalize_identifier(table_meta.get('qualified_name'))
            database_name = (
                table_meta.get('database_name')
                or table_meta.get('database')
                or db_metadata.get('name')
                or self.database_name
            )
            normalized_database = self._normalize_identifier(database_name)
            table_name = table_meta.get('table_name') or table_meta.get('name')
            normalized_table_name = self._normalize_identifier(table_name)

            potential_keys = set()
            if qualified_name:
                potential_keys.add(qualified_name)

            if normalized_database and normalized_table_name:
                potential_keys.add(f"{normalized_database}.{normalized_table_name}")

            if normalized_table_name:
                potential_keys.add(normalized_table_name)

            for key in potential_keys:
                lookup[key] = table_meta

        return lookup

    def _build_column_entry(
        self,
        table_name: str,
        column_name: str,
        column_metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build a single column payload enriched with metadata and lineage."""
        col_obj: Dict[str, Any] = {
            "name": column_name
        }

        if column_metadata:
            col_obj.update({
                "data_type": column_metadata.get('data_type'),
                "is_nullable": column_metadata.get('is_nullable'),
                "column_length": column_metadata.get('column_length'),
                "numeric_precision": column_metadata.get('numeric_precision'),
                "numeric_scale": column_metadata.get('numeric_scale'),
                "column_default": column_metadata.get('column_default'),
                "comment": column_metadata.get('comment'),
                "from_metadata": True
            })

        col_key = f"{table_name}.{column_name}"
        col_info = self.columns.get(col_key)

        if col_info:
            col_obj.update({
                "is_derived": col_info.is_derived,
                "is_aggregate": col_info.is_aggregate,
                "is_calculated": col_info.is_calculated,
                "transforms": list(col_info.transforms) if col_info.transforms else []
            })

        return col_obj

    def build_statement_with_metadata(
        self,
        statement: Dict[str, Any],
        table_metadata: Dict[str, Any],
        column_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build enriched statement with metadata context.

        Args:
            statement: Parsed statement dictionary
            table_metadata: Table metadata from database
            column_metadata: Column metadata from database

        Returns:
            Statement enriched with metadata
        """
        enriched = statement.copy()

        # Enrich tables with metadata
        if 'source_tables' in enriched:
            enriched['source_tables'] = self.enrich_tables_with_metadata(
                enriched['source_tables'],
                table_metadata
            )

        if 'target_table' in enriched:
            enriched['target_table'] = self._enrich_single_table(
                enriched['target_table'],
                table_metadata
            )

        # Enrich columns with metadata
        if 'column_lineage' in enriched:
            enriched['column_lineage'] = self.enrich_columns_with_metadata(
                enriched['column_lineage'],
                column_metadata
            )

        return enriched

    def enrich_tables_with_metadata(
        self,
        tables: List[str],
        table_metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Enrich table list with metadata.

        Args:
            tables: List of table names
            table_metadata: Table metadata dictionary

        Returns:
            List of enriched table dictionaries
        """
        enriched_tables = []

        for table in tables:
            enriched = self._enrich_single_table(table, table_metadata)
            enriched_tables.append(enriched)

        return enriched_tables

    def _enrich_single_table(
        self,
        table_name: str,
        table_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enrich single table with metadata.

        Args:
            table_name: Table name
            table_metadata: Table metadata dictionary

        Returns:
            Enriched table dictionary
        """
        enriched = {
            'name': table_name,
            'exists': False,
            'type': 'unknown',
            'database': None,
            'is_volatile': False,
            'is_global_temp': False
        }

        # Parse Database.TableName format (Teradata uses database instead of schema)
        parts = table_name.split('.')
        if len(parts) == 2:
            database, table = parts
            enriched['database'] = database
        else:
            table = table_name

        # Check if table exists in metadata
        metadata_key = table_name.lower()
        if metadata_key in table_metadata:
            meta = table_metadata[metadata_key]
            enriched['exists'] = True
            enriched['type'] = meta.get('table_type', 'TABLE')
            enriched['row_count'] = meta.get('row_count')
            enriched['created_date'] = meta.get('created_date')
            enriched['last_altered_date'] = meta.get('last_altered_date')

        # Check for Teradata-specific table types
        if 'volatile' in table_name.lower() or table_name in self.volatile_tables:
            enriched['is_volatile'] = True
            enriched['type'] = 'VOLATILE'

        if 'global_temp' in table_name.lower() or table_name in self.global_temp_tables:
            enriched['is_global_temp'] = True
            enriched['type'] = 'GLOBAL TEMPORARY'

        return enriched

    def enrich_columns_with_metadata(
        self,
        column_lineage: List[Dict[str, Any]],
        column_metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Enrich column lineage with metadata.

        Args:
            column_lineage: List of column lineage dictionaries
            column_metadata: Column metadata dictionary

        Returns:
            List of enriched column lineage dictionaries
        """
        enriched_columns = []

        for col_lin in column_lineage:
            enriched = col_lin.copy()

            # Enrich target column
            target_table = col_lin.get('target_table', '')
            target_column = col_lin.get('target_column', '')
            target_key = f"{target_table}.{target_column}".lower()

            if target_key in column_metadata:
                meta = column_metadata[target_key]
                enriched['target_column_metadata'] = {
                    'data_type': meta.get('data_type'),
                    'nullable': meta.get('nullable'),
                    'default_value': meta.get('default_value'),
                    'column_position': meta.get('column_position')
                }

            # Enrich source columns
            if 'source_columns' in enriched:
                enriched_sources = []
                for src in enriched['source_columns']:
                    src_table = src.get('table', '')
                    src_column = src.get('column', '')
                    src_key = f"{src_table}.{src_column}".lower()

                    enriched_src = src.copy()
                    if src_key in column_metadata:
                        meta = column_metadata[src_key]
                        enriched_src['metadata'] = {
                            'data_type': meta.get('data_type'),
                            'nullable': meta.get('nullable'),
                            'is_primary_key': meta.get('is_primary_key', False)
                        }

                    # Resolve column source
                    enriched_src['resolved_source'] = self._resolve_column_source(
                        src_table,
                        src_column,
                        column_metadata
                    )

                    enriched_sources.append(enriched_src)

                enriched['source_columns'] = enriched_sources

            enriched_columns.append(enriched)

        return enriched_columns

    def _resolve_column_source(
        self,
        table: str,
        column: str,
        column_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Resolve column source with metadata.

        Args:
            table: Table name
            column: Column name
            column_metadata: Column metadata dictionary

        Returns:
            Resolved source information
        """
        resolution = {
            'table': table,
            'column': column,
            'exists': False,
            'is_cte': False,
            'is_volatile': False,
            'is_global_temp': False
        }

        # Check if CTE
        if table.startswith('CTE:'):
            resolution['is_cte'] = True
            resolution['cte_name'] = table[4:]
            return resolution

        # Check if volatile table
        if table in self.volatile_tables:
            resolution['is_volatile'] = True

        # Check if global temp table
        if table in self.global_temp_tables:
            resolution['is_global_temp'] = True

        # Check metadata
        meta_key = f"{table}.{column}".lower()
        if meta_key in column_metadata:
            resolution['exists'] = True
            meta = column_metadata[meta_key]
            resolution['data_type'] = meta.get('data_type')
            resolution['nullable'] = meta.get('nullable')

        return resolution

    def _handle_volatile_tables(self):
        """
        Handle volatile table references and dependencies.
        Volatile tables are session-specific and may appear in multiple statements.
        """
        print(f"   Handling {len(self.volatile_tables)} volatile tables...")

        for vol_table_name, vol_table_info in self.volatile_tables.items():
            # Check if volatile table is used as a source in other tables
            for table_name, dependencies in self.table_dependencies.items():
                if vol_table_name in dependencies:
                    # Mark the dependency as volatile
                    if table_name in self.tables:
                        self.tables[table_name].teradata_features.add('uses_volatile_table')

            # Ensure volatile table is marked in main tables dict
            if vol_table_name in self.tables:
                self.tables[vol_table_name].is_volatile = True
                self.tables[vol_table_name].teradata_features.add('volatile_table')

    def _process_result(self, result: Dict[str, Any], source_type: str):
        """Process a single analysis result."""
        name = result.get('name', 'unknown')

        if result.get('parse_error'):
            self.stats['parse_errors'] += 1
            return

        self.stats['successful_parses'] += 1

        # Track special features
        if result.get('is_dynamic'):
            self.stats['dynamic_sql_count'] += 1

        if result.get('statement_subtype') in ['UNION', 'INTERSECT', 'EXCEPT', 'MINUS']:
            self.stats['set_operations'] += 1

        # Track Teradata-specific features
        teradata_features = result.get('teradata_features', [])
        if 'QUALIFY' in teradata_features:
            self.stats['qualify_count'] += 1
        if 'SAMPLE' in teradata_features:
            self.stats['sample_count'] += 1
        if 'TD_OUTER_JOIN' in teradata_features:
            self.stats['td_outer_join_count'] += 1
        if 'COLLECT_STATISTICS' in teradata_features:
            self.stats['collect_statistics_count'] += 1

        # Process CTEs
        cte_definitions = result.get('cte_definitions', {})
        if cte_definitions:
            for cte_name, cte_def in cte_definitions.items():
                self.ctes[cte_name].append(CTEInfo(
                    name=cte_name,
                    defining_source=name,
                    columns=cte_def.get('columns', []),
                    source_tables=cte_def.get('source_tables', []),
                    query_snippet=cte_def.get('query', '')[:500]
                ))
                self.stats['cte_count'] += 1

        # Process volatile tables
        volatile_tables = result.get('volatile_tables', [])
        for vol_table in volatile_tables:
            if vol_table not in self.volatile_tables:
                self.volatile_tables[vol_table] = TableInfo(
                    table_name=vol_table,
                    is_temp=True,
                    is_volatile=True
                )
                self.volatile_tables[vol_table].definition_sources.add(name)
                self.volatile_tables[vol_table].teradata_features.add('volatile_table')
                self.stats['volatile_table_count'] += 1

        # Process temp tables (GLOBAL TEMPORARY)
        temp_tables = result.get('temp_tables', [])
        for temp_table in temp_tables:
            if temp_table not in self.global_temp_tables:
                self.global_temp_tables[temp_table] = TableInfo(
                    table_name=temp_table,
                    is_temp=True,
                    is_global_temp=True
                )
                self.global_temp_tables[temp_table].definition_sources.add(name)
                self.global_temp_tables[temp_table].teradata_features.add('global_temp_table')
                self.stats['global_temp_table_count'] += 1

            if temp_table not in self.temp_tables:
                self.temp_tables[temp_table] = self.global_temp_tables[temp_table]
                self.stats['temp_table_count'] += 1

        # Process macros (if present)
        macros = result.get('macros', [])
        for macro_name in macros:
            if macro_name not in self.macros:
                self.macros[macro_name] = MacroInfo(
                    name=macro_name,
                    defining_source=name
                )
                self.stats['macro_count'] += 1

        # Process target table (for views, this is the view name)
        target_table = result.get('target_table') or result.get('name')
        if target_table:
            # For views, use "CREATE" as the definition type so they're classified as 'target' in frontend
            view_stmt_type = "CREATE" if source_type == "VIEW" else source_type
            self._register_table(
                target_table,
                view_stmt_type,
                name,
                result.get('statement_subtype'),
                is_view=(source_type == "VIEW"),
                teradata_features=teradata_features
            )

            # Process source tables (dependencies)
            for source_table in result.get('source_tables', []):
                if not source_table.startswith('CTE:'):
                    self.table_dependencies[target_table].add(source_table)

                    if source_table not in self.tables:
                        self._register_table(source_table, "REFERENCE", name)

            # Process column lineage
            for col_lineage in result.get('column_lineage', []):
                self._register_column_lineage(col_lineage, name)

    def _register_table(
        self,
        table_name: str,
        stmt_type: str,
        source_name: str,
        stmt_subtype: Optional[str] = None,
        is_view: bool = False,
        teradata_features: Optional[List[str]] = None
    ):
        """Register a table in the lineage graph."""
        if table_name not in self.tables:
            is_volatile = (table_name in self.volatile_tables or
                          'volatile' in table_name.lower())
            is_global_temp = (table_name in self.global_temp_tables or
                            'global_temp' in table_name.lower())

            self.tables[table_name] = TableInfo(
                table_name=table_name,
                is_temp=self._is_temp_table(table_name),
                is_cte=table_name.startswith('CTE:'),
                is_view=is_view,
                is_volatile=is_volatile,
                is_global_temp=is_global_temp
            )

        self.tables[table_name].definition_sources.add(source_name)
        self.tables[table_name].definition_types.add(stmt_type)

        if stmt_subtype:
            self.tables[table_name].statement_subtypes.add(stmt_subtype)

        if is_view:
            self.tables[table_name].is_view = True

        if teradata_features:
            self.tables[table_name].teradata_features.update(teradata_features)

    def _register_column_lineage(self, col_lineage: Dict, source_name: str):
        """Register column-level lineage."""
        target_table = col_lineage.get('target_table', 'unknown')
        target_column = col_lineage.get('target_column', 'unknown')
        col_key = f"{target_table}.{target_column}"

        # Create or update column info
        if col_key not in self.columns:
            self.columns[col_key] = ColumnInfo(
                name=target_column,
                table=target_table
            )

        col_info = self.columns[col_key]

        # Add defining source
        col_info.defining_sources.add(source_name)

        # Add source columns
        for src in col_lineage.get('source_columns', []):
            table_name = src.get('table', 'unknown')
            column_name = src.get('column', 'unknown')

            if src.get('cte_reference'):
                col_info.cte_dependencies.add(src['cte_reference'])

            col_info.source_columns.add((table_name, column_name))

        # Add transform type
        transform_type = col_lineage.get('transform_type', 'unknown')
        col_info.transforms.add(transform_type)

        # Update flags
        if col_lineage.get('source_columns'):
            col_info.is_derived = True

        if col_lineage.get('is_aggregate'):
            col_info.is_aggregate = True

        if col_lineage.get('is_calculated'):
            col_info.is_calculated = True

        # Teradata-specific flags
        if col_lineage.get('has_qualify'):
            col_info.has_qualify = True

        if col_lineage.get('has_sample'):
            col_info.has_sample = True

        # Store expression
        expression = col_lineage.get('expression', '')
        if expression and expression not in col_info.expressions:
            col_info.expressions.append(expression)

        # Add to table's column list
        if target_table in self.tables:
            self.tables[target_table].columns[target_column] = col_info

    def _resolve_cte_references(self):
        """Resolve CTE references in column lineage."""
        print(f"   Resolving {self.stats['cte_count']} CTE references...")

        for col_key, col_info in self.columns.items():
            if col_info.cte_dependencies:
                new_sources = set()

                for cte_name in col_info.cte_dependencies:
                    if cte_name in self.ctes:
                        cte_info = self.ctes[cte_name][0]

                        for source_table in cte_info.source_tables:
                            new_sources.add((f"{source_table}[via CTE:{cte_name}]", "*"))

                col_info.source_columns.update(new_sources)

    def _deduplicate_lineages(self):
        """Remove duplicate column lineages and resolve conflicts."""
        print(f"   Deduplicating lineages...")

        column_groups = defaultdict(list)
        for col_key, col_info in self.columns.items():
            normalized_key = col_key.lower()
            column_groups[normalized_key].append((col_key, col_info))

        for norm_key, col_list in column_groups.items():
            if len(col_list) > 1:
                self.stats['duplicate_columns_merged'] += len(col_list) - 1

                primary_key, primary_col = col_list[0]

                for col_key, col_info in col_list[1:]:
                    primary_col.source_columns.update(col_info.source_columns)
                    primary_col.transforms.update(col_info.transforms)
                    primary_col.defining_sources.update(col_info.defining_sources)
                    primary_col.cte_dependencies.update(col_info.cte_dependencies)

                    for expr in col_info.expressions:
                        if expr not in primary_col.expressions and len(primary_col.expressions) < 10:
                            primary_col.expressions.append(expr)

                    if col_info.is_derived:
                        primary_col.is_derived = True
                    if col_info.is_aggregate:
                        primary_col.is_aggregate = True
                    if col_info.is_calculated:
                        primary_col.is_calculated = True
                    if col_info.has_qualify:
                        primary_col.has_qualify = True
                    if col_info.has_sample:
                        primary_col.has_sample = True

                    if col_key in self.columns:
                        del self.columns[col_key]

        print(f"   Merged {self.stats['duplicate_columns_merged']} duplicate columns")

    def _remove_placeholder_columns(self):
        """Remove auto-generated placeholder columns."""
        placeholder_pattern = re.compile(r"^column_\d+$", re.IGNORECASE)

        for table_name, table_info in self.tables.items():
            column_names = list(table_info.columns.keys())
            has_real_columns = any(not placeholder_pattern.match(col) for col in column_names)

            if has_real_columns:
                for col in column_names:
                    if placeholder_pattern.match(col):
                        table_info.columns.pop(col, None)
                        self.columns.pop(f"{table_name}.{col}", None)

    def _calculate_confidence_scores(self):
        """Calculate confidence scores for column lineage."""
        for col_info in self.columns.values():
            confidence = 1.0

            if 'direct' in col_info.transforms:
                confidence = 1.0
            elif len(col_info.transforms) > 2:
                confidence = 0.7
            elif col_info.is_aggregate:
                confidence = 0.85

            if len(col_info.source_columns) > 5:
                confidence *= 0.8

            if col_info.cte_dependencies:
                confidence *= 0.95

            if len(col_info.defining_sources) > 1:
                confidence *= 0.9

            # Teradata-specific adjustments
            if col_info.has_qualify:
                confidence *= 0.95  # QUALIFY adds filtering complexity

            if col_info.has_sample:
                confidence *= 0.9  # SAMPLE adds non-determinism

            col_info.confidence_score = round(confidence, 2)

    def _calculate_execution_order(self) -> Dict:
        """Calculate table execution order via topological sort."""
        in_degree = defaultdict(int)
        adj_list = defaultdict(list)

        for table in self.tables:
            if table not in in_degree:
                in_degree[table] = 0

        for table, deps in self.table_dependencies.items():
            for dep in deps:
                adj_list[dep].append(table)
                in_degree[table] += 1

        queue = deque([t for t, deg in in_degree.items() if deg == 0])
        order = []
        levels = defaultdict(list)

        current_level = 0
        while queue:
            level_size = len(queue)

            for _ in range(level_size):
                table = queue.popleft()
                order.append(table)
                levels[f"level_{current_level}"].append(table)

                for neighbor in adj_list[table]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            current_level += 1

        has_cycle = len(order) != len(self.tables)
        if has_cycle:
            remaining = set(self.tables.keys()) - set(order)
            self.stats['circular_dependencies'] = list(remaining)

        return {
            "execution_order": order,
            "levels": dict(levels),
            "has_circular_dependency": has_cycle,
            "max_depth": current_level
        }

    def _build_json_report(self, execution_order: Dict) -> Dict:
        """Build final JSON report structure."""
        # First, enrich tables with metadata columns
        self._enrich_tables_with_metadata_columns()
        
        metadata_table_lookup = self._build_metadata_table_lookup()

        # Build tables section
        tables_json = {}
        for table_name, table_info in self.tables.items():
            # Parse schema and table name from Database.TableName format
            parts = table_name.split('.')
            if len(parts) == 2:
                schema = parts[0]
                display_table_name = parts[1]
            else:
                schema = self.database_name or ''
                display_table_name = table_name
            normalized_table_key = self._normalize_identifier(table_name)
            metadata_table = metadata_table_lookup.get(normalized_table_key)
            if not metadata_table and normalized_table_key:
                fallback_key = normalized_table_key.split('.')[-1]
                metadata_table = metadata_table_lookup.get(fallback_key)
            metadata_columns = metadata_table.get('columns', []) if metadata_table else []

            # Build columns array prioritizing metadata order, then lineage-only columns
            columns_list = []
            covered_columns: Set[str] = set()

            for col_meta in metadata_columns:
                meta_name = col_meta.get('name') or col_meta.get('column_name')
                normalized_col_name = self._normalize_identifier(meta_name)
                if not normalized_col_name:
                    continue
                columns_list.append(self._build_column_entry(table_name, meta_name, col_meta))
                covered_columns.add(normalized_col_name)

            # Add any lineage columns missing from metadata (e.g., derived columns)
            for col_name in table_info.columns.keys():
                normalized_col_name = self._normalize_identifier(col_name)
                if normalized_col_name in covered_columns:
                    continue
                columns_list.append(self._build_column_entry(table_name, col_name, None))
                covered_columns.add(normalized_col_name)
            
            tables_json[table_name] = {
                "definition_sources": list(table_info.definition_sources),
                "definition_types": list(table_info.definition_types),
                "statement_subtypes": list(table_info.statement_subtypes),
                "columns": columns_list,  # Now an array of objects, not just strings
                "depends_on": list(self.table_dependencies.get(table_name, set())),
                "is_temp": table_info.is_temp,
                "is_cte": table_info.is_cte,
                "is_view": table_info.is_view,
                "is_volatile": table_info.is_volatile,
                "is_global_temp": table_info.is_global_temp,
                "teradata_features": list(table_info.teradata_features),
                "column_count": len(columns_list),
                "schema": schema,  # Add schema for frontend
                "table_name": display_table_name,  # Add table_name for frontend
                "name": table_name  # Add name for consistency
            }
        
        # Add tables from metadata that weren't referenced in SQL
        if self.metadata and 'database' in self.metadata:
            db_metadata = self.metadata.get('database', {})
            tables_metadata = db_metadata.get('tables', [])
            
            for table_meta in tables_metadata:
                qualified_name = table_meta.get('qualified_name', '')
                if not qualified_name:
                    continue
                
                # Skip if already in tables_json
                if qualified_name in tables_json:
                    continue
                
                # Skip system tables
                db_name = table_meta.get('database_name', '')
                if db_name.upper() in ['DBC', 'SYSDBA', 'SYSBAR', 'SYSLIB']:
                    continue
                
                # Build columns from metadata
                columns_list = []
                for col_meta in table_meta.get('columns', []):
                    col_obj = {
                        "name": col_meta.get('name', ''),
                        "data_type": col_meta.get('data_type'),
                        "is_nullable": col_meta.get('is_nullable'),
                        "column_length": col_meta.get('column_length'),
                        "numeric_precision": col_meta.get('numeric_precision'),
                        "numeric_scale": col_meta.get('numeric_scale'),
                        "column_default": col_meta.get('column_default'),
                        "comment": col_meta.get('comment'),
                        "from_metadata": True
                    }
                    columns_list.append(col_obj)
                
                # Only add if it has columns
                if columns_list:
                    is_view = table_meta.get('table_type', '').upper() == 'VIEW'
                    # For views, use "CREATE" as definition type so they're classified as 'target' in frontend
                    definition_type = "CREATE" if is_view else table_meta.get('table_type', 'TABLE')
                    tables_json[qualified_name] = {
                        "definition_sources": [],
                        "definition_types": [definition_type],
                        "statement_subtypes": [],
                        "columns": columns_list,
                        "depends_on": [],
                        "is_temp": False,
                        "is_cte": False,
                        "is_view": is_view,
                        "is_volatile": False,
                        "is_global_temp": False,
                        "teradata_features": [],
                        "column_count": len(columns_list),
                        "from_metadata": True,
                        "schema": db_name,  # Teradata uses database instead of schema
                        "table_name": table_meta.get('table_name', '')
                    }

        # Build columns section
        columns_json = {}
        for col_key, col_info in self.columns.items():
            columns_json[col_key] = {
                "table": col_info.table,
                "name": col_info.name,
                "source_columns": [f"{t}.{c}" for t, c in col_info.source_columns],
                "transforms": list(col_info.transforms),
                "is_derived": col_info.is_derived,
                "is_aggregate": col_info.is_aggregate,
                "is_calculated": col_info.is_calculated,
                "has_qualify": col_info.has_qualify,
                "has_sample": col_info.has_sample,
                "cte_dependencies": list(col_info.cte_dependencies),
                "defining_sources": list(col_info.defining_sources),
                "confidence_score": col_info.confidence_score,
                "sample_expressions": col_info.expressions[:3]
            }

        # Build CTEs section
        ctes_json = {}
        for cte_name, cte_list in self.ctes.items():
            ctes_json[cte_name] = [{
                "defining_source": cte.defining_source,
                "columns": cte.columns,
                "source_tables": cte.source_tables,
                "query_snippet": cte.query_snippet
            } for cte in cte_list]

        # Build temp tables section (includes both volatile and global temp)
        temp_tables_json = {}
        for temp_name, temp_info in self.temp_tables.items():
            temp_tables_json[temp_name] = {
                "columns": list(temp_info.columns.keys()),
                "definition_sources": list(temp_info.definition_sources),
                "is_volatile": temp_info.is_volatile,
                "is_global_temp": temp_info.is_global_temp
            }

        # Build volatile tables section
        volatile_tables_json = {}
        for vol_name, vol_info in self.volatile_tables.items():
            volatile_tables_json[vol_name] = {
                "columns": list(vol_info.columns.keys()),
                "definition_sources": list(vol_info.definition_sources)
            }

        # Build macros section
        macros_json = {}
        for macro_name, macro_info in self.macros.items():
            macros_json[macro_name] = {
                "database": macro_info.database,
                "defining_source": macro_info.defining_source,
                "parameters": macro_info.parameters,
                "referenced_tables": macro_info.referenced_tables,
                "description": macro_info.description
            }

        # Calculate success rate
        total = self.stats['successful_parses'] + self.stats['parse_errors']
        parse_success_rate = f"{(self.stats['successful_parses'] / max(total, 1) * 100):.1f}%"

        # Build final report
        report = {
            "metadata": {
                "dialect": self.dialect,
                "database_name": self.database_name,
                "source_type": "database_metadata",
                "parsing_strategy": "metadata_based",
                "version": "2.0",
                "generated_at": datetime.now().isoformat()
            },
            "summary": {
                "total_views": self.stats['total_views'],
                "total_queries": self.stats['total_queries'],
                "total_statements": self.stats['total_statements'],
                "total_tables": len(self.tables),
                "total_columns": len(self.columns),
                "total_dependencies": sum(len(deps) for deps in self.table_dependencies.values()),
                "temp_tables": self.stats['temp_table_count'],
                "volatile_tables": self.stats['volatile_table_count'],
                "global_temp_tables": self.stats['global_temp_table_count'],
                "ctes": self.stats['cte_count'],
                "macros": self.stats['macro_count'],
                "dynamic_sql_count": self.stats['dynamic_sql_count'],
                "dynamic_sql_detected": self.stats['dynamic_sql_count'] > 0,
                "set_operations": self.stats['set_operations'],
                "parse_errors": self.stats['parse_errors'],
                "successful_parses": self.stats['successful_parses'],
                "parse_success_rate": parse_success_rate,
                "duplicate_columns_merged": self.stats['duplicate_columns_merged'],
                "qualify_count": self.stats['qualify_count'],
                "sample_count": self.stats['sample_count'],
                "td_outer_join_count": self.stats['td_outer_join_count'],
                "collect_statistics_count": self.stats['collect_statistics_count']
            },
            "execution_order": execution_order,
            "tables": tables_json,
            "columns": columns_json,
            "ctes": ctes_json,
            "temp_tables": temp_tables_json,
            "volatile_tables": volatile_tables_json,
            "macros": macros_json,
            "warnings": {
                "circular_dependencies": self.stats['circular_dependencies'],
                "dynamic_sql_detected": self.stats['dynamic_sql_count'] > 0
            }
        }

        return report

    def _enrich_tables_with_metadata_columns(self):
        """Enrich existing tables with column metadata from database metadata."""
        if not self.metadata or 'database' not in self.metadata:
            return
        
        db_metadata = self.metadata.get('database', {})
        tables_metadata = db_metadata.get('tables', [])
        
        # Build a lookup map for quick access
        metadata_lookup = {}
        for table_meta in tables_metadata:
            qualified_name = table_meta.get('qualified_name', '')
            if qualified_name:
                metadata_lookup[qualified_name.lower()] = table_meta
        
        # Enrich each table
        for table_name, table_info in self.tables.items():
            table_meta = metadata_lookup.get(table_name.lower())
            if not table_meta:
                continue
            
            # Add columns from metadata that aren't already tracked
            for col_meta in table_meta.get('columns', []):
                col_name = col_meta.get('name', '')
                if not col_name:
                    continue
                
                col_key = f"{table_name}.{col_name}"
                
                # Create column info if it doesn't exist
                if col_key not in self.columns:
                    self.columns[col_key] = ColumnInfo(
                        name=col_name,
                        table=table_name
                    )
                    self.columns[col_key].defining_sources.add('metadata')
                
                # Ensure column is in table's column dict
                if col_name not in table_info.columns:
                    table_info.columns[col_name] = self.columns[col_key]

    def _is_temp_table(self, table_name: str) -> bool:
        """Check if table is temporary (includes volatile and global temp)."""
        temp_prefixes = ['temp_', 'tmp_', 'staging_', 'stg_', 'volatile_', 'vol_']
        temp_suffixes = ['_temp', '_tmp', '_staging', '_stg', '_volatile', '_vol']

        lower_name = table_name.lower()

        # Check prefixes
        if any(lower_name.startswith(prefix) for prefix in temp_prefixes):
            return True

        # Check suffixes
        if any(lower_name.endswith(suffix) for suffix in temp_suffixes):
            return True

        # Check if in volatile or global temp registries
        if table_name in self.volatile_tables or table_name in self.global_temp_tables:
            return True

        return False

    def save_report(self, report: Dict, output_path: str):
        """Save report to JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n   Report saved to: {output_path}")


if __name__ == "__main__":
    builder = MetadataStatementBuilder("teradata", "TestDB")
    
    mock_view_results = [
        {
            'name': 'vw_customer_orders',
            'type': 'VIEW',
            'target_table': 'vw_customer_orders',
            'source_tables': ['dw_db.customers', 'dw_db.orders'],
            'column_lineage': [
                {
                    'target_column': 'customer_id',
                    'target_table': 'vw_customer_orders',
                    'source_columns': [{'table': 'dw_db.customers', 'column': 'customer_id'}],
                    'transform_type': 'direct',
                    'is_aggregate': False,
                    'is_calculated': False,
                    'has_qualify': False,
                    'has_sample': False
                },
                {
                    'target_column': 'order_count',
                    'target_table': 'vw_customer_orders',
                    'source_columns': [{'table': 'dw_db.orders', 'column': 'order_id'}],
                    'transform_type': 'aggregate',
                    'is_aggregate': True,
                    'is_calculated': True,
                    'has_qualify': True,  # Teradata QUALIFY used
                    'has_sample': False
                }
            ],
            'cte_definitions': {},
            'temp_tables': [],
            'volatile_tables': [],
            'teradata_features': ['QUALIFY'],
            'is_dynamic': False,
            'parse_error': None
        },
        {
            'name': 'volatile_staging',
            'type': 'CREATE',
            'target_table': 'volatile_staging',
            'source_tables': ['dw_db.raw_data'],
            'column_lineage': [
                {
                    'target_column': 'id',
                    'target_table': 'volatile_staging',
                    'source_columns': [{'table': 'dw_db.raw_data', 'column': 'id'}],
                    'transform_type': 'direct',
                    'is_aggregate': False,
                    'is_calculated': False,
                    'has_qualify': False,
                    'has_sample': True  # Teradata SAMPLE used
                }
            ],
            'cte_definitions': {},
            'temp_tables': [],
            'volatile_tables': ['volatile_staging'],
            'teradata_features': ['VOLATILE_TABLE', 'SAMPLE'],
            'is_dynamic': False,
            'parse_error': None
        }
    ]

    report = builder.build_lineage_report(mock_view_results, [])
    print(json.dumps(report, indent=2))
