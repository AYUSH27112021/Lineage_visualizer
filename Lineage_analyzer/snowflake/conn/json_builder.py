"""
Enhanced Lineage JSON Report Builder for Regular Statements
Handles CTEs, temp tables, set operations, and complex dependencies
Optimized for Snowflake dialect
"""

from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
import json
import re


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
    defining_scripts: Set[str] = field(default_factory=set)
    expressions: List[str] = field(default_factory=list)
    cte_dependencies: Set[str] = field(default_factory=set)
    confidence_score: float = 1.0


@dataclass
class TableInfo:
    """Aggregated table information"""
    table_name: str
    columns: Dict[str, ColumnInfo] = field(default_factory=dict)
    definition_scripts: Set[str] = field(default_factory=set)
    definition_types: Set[str] = field(default_factory=set)
    depends_on: Set[str] = field(default_factory=set)
    is_temp: bool = False
    is_cte: bool = False
    is_view: bool = False
    statement_subtypes: Set[str] = field(default_factory=set)


@dataclass
class CTEInfo:
    """CTE definition information"""
    name: str
    defining_script: str
    columns: List[str] = field(default_factory=list)
    source_tables: List[str] = field(default_factory=list)
    query_snippet: str = ""


class EnhancedLineageJSONBuilder:
    """Build comprehensive lineage JSON report with advanced features for Snowflake"""

    def __init__(self, dialect: str, source_directory: str):
        self.dialect = dialect
        self.source_directory = source_directory

        # Aggregation containers
        self.tables: Dict[str, TableInfo] = {}
        self.columns: Dict[str, ColumnInfo] = {}
        self.ctes: Dict[str, List[CTEInfo]] = defaultdict(list)
        self.temp_tables: Dict[str, TableInfo] = {}
        self.table_dependencies: Dict[str, Set[str]] = defaultdict(set)

        # Statistics
        self.stats = {
            'total_scripts': 0,
            'total_statements': 0,
            'successful_parses': 0,
            'parse_errors': 0,
            'dynamic_sql_count': 0,
            'duplicate_columns_merged': 0,
            'cte_count': 0,
            'temp_table_count': 0,
            'circular_dependencies': [],
            'set_operations': 0,
            'subquery_count': 0,
            'variant_access_count': 0,
            'lateral_flatten_count': 0
        }

    def build_lineage_report(self, analysis_results: List[Dict[str, Any]]) -> Dict:
        """Build final lineage report from all analysis results"""
        print(f"   Processing {len(analysis_results)} file results...")

        # Step 1: Aggregate all lineages
        for result in analysis_results:
            self._process_file_result(result)

        # Step 2: Resolve CTEs and temp table references
        self._resolve_cte_references()

        # Step 3: Deduplicate and merge conflicts
        self._deduplicate_lineages()

        # Step 3.5: Remove placeholder columns (e.g., column_0) if real columns exist
        self._remove_placeholder_columns_when_defined()

        # Step 4: Calculate confidence scores
        self._calculate_confidence_scores()

        # Step 5: Calculate execution order
        execution_order = self._calculate_execution_order()

        # Step 6: Build final JSON structure
        return self._build_json_report(execution_order)

    def _process_file_result(self, result: Dict[str, Any]):
        """Process a single file's analysis results"""
        file_path = result['file_path']
        self.stats['total_scripts'] += 1
        self.stats['total_statements'] += result['statement_count']

        for lineage in result.get('lineages', []):
            if lineage.parse_error:
                self.stats['parse_errors'] += 1
                continue

            self.stats['successful_parses'] += 1

            # Track special features
            if lineage.is_dynamic:
                self.stats['dynamic_sql_count'] += 1

            if lineage.statement_subtype in ['UNION', 'INTERSECT', 'EXCEPT', 'MINUS']:
                self.stats['set_operations'] += 1

            # Process CTEs
            if lineage.cte_definitions:
                for cte_name, cte_def in lineage.cte_definitions.items():
                    self.ctes[cte_name].append(CTEInfo(
                        name=cte_name,
                        defining_script=file_path,
                        columns=cte_def.get('columns', []),
                        source_tables=cte_def.get('source_tables', []),
                        query_snippet=cte_def.get('query', '')[:500]
                    ))
                    self.stats['cte_count'] += 1

            # Process temp tables
            if lineage.temp_tables:
                for temp_table in lineage.temp_tables:
                    if temp_table not in self.temp_tables:
                        self.temp_tables[temp_table] = TableInfo(
                            table_name=temp_table,
                            is_temp=True
                        )
                        self.temp_tables[temp_table].definition_scripts.add(file_path)
                        self.stats['temp_table_count'] += 1

            # Process target table
            if lineage.target_table:
                self._register_table(
                    lineage.target_table,
                    lineage.statement_type,
                    file_path,
                    lineage.statement_subtype
                )

                # Process source tables (dependencies)
                for source_table in lineage.source_tables:
                    # Skip CTEs (they're handled separately)
                    if not source_table.startswith('CTE:'):
                        self.table_dependencies[lineage.target_table].add(source_table)

                        # Ensure source table exists
                        if source_table not in self.tables:
                            self._register_table(source_table, "REFERENCE", file_path)

                # Process column lineage
                for col_lineage in lineage.column_lineage:
                    self._register_column_lineage(col_lineage, file_path)

    def _register_table(self, table_name: str, stmt_type: str, file_path: str, stmt_subtype: str = None):
        """Register a table in the lineage graph"""
        if table_name not in self.tables:
            self.tables[table_name] = TableInfo(
                table_name=table_name,
                is_temp=self._is_temp_table(table_name),
                is_cte=table_name.startswith('CTE:'),
                is_view=stmt_type == 'CREATE' and 'VIEW' in table_name.upper()
            )

        self.tables[table_name].definition_scripts.add(file_path)
        self.tables[table_name].definition_types.add(stmt_type)

        if stmt_subtype:
            self.tables[table_name].statement_subtypes.add(stmt_subtype)

    def _register_column_lineage(self, col_lineage, file_path: str):
        """Register column-level lineage with enhanced tracking"""
        col_key = f"{col_lineage.target_table}.{col_lineage.target_column}"

        # Create or update column info
        if col_key not in self.columns:
            self.columns[col_key] = ColumnInfo(
                name=col_lineage.target_column,
                table=col_lineage.target_table
            )

        col_info = self.columns[col_key]

        # Add defining script
        col_info.defining_scripts.add(file_path)

        # Add source columns
        for src in col_lineage.source_columns:
            # Handle CTE references
            table_name = src['table']
            if src.get('cte_reference'):
                col_info.cte_dependencies.add(src['cte_reference'])

            col_info.source_columns.add((table_name, src['column']))

        # Add transform type
        col_info.transforms.add(col_lineage.transform_type)

        # Update flags
        if col_lineage.source_columns:
            col_info.is_derived = True

        if col_lineage.is_aggregate:
            col_info.is_aggregate = True

        if col_lineage.is_calculated:
            col_info.is_calculated = True

        # Store expression (limit duplicates)
        if col_lineage.expression and col_lineage.expression not in col_info.expressions:
            col_info.expressions.append(col_lineage.expression)

        # Add to table's column list
        if col_lineage.target_table in self.tables:
            self.tables[col_lineage.target_table].columns[col_lineage.target_column] = col_info

    def _resolve_cte_references(self):
        """Resolve CTE references in column lineage"""
        print(f"   Resolving {self.stats['cte_count']} CTE references...")

        for col_key, col_info in self.columns.items():
            if col_info.cte_dependencies:
                new_sources = set()

                for cte_name in col_info.cte_dependencies:
                    if cte_name in self.ctes:
                        # Get the first CTE definition (could be multiple)
                        cte_info = self.ctes[cte_name][0]

                        # Add the CTE's source tables as indirect sources
                        for source_table in cte_info.source_tables:
                            # Mark as coming from CTE
                            new_sources.add((f"{source_table}[via CTE:{cte_name}]", "*"))

                col_info.source_columns.update(new_sources)

    def _deduplicate_lineages(self):
        """Remove duplicate column lineages and resolve conflicts"""
        print(f"   Deduplicating lineages...")

        # Group columns by normalized key (case-insensitive)
        column_groups = defaultdict(list)
        for col_key, col_info in self.columns.items():
            normalized_key = col_key.lower()
            column_groups[normalized_key].append((col_key, col_info))

        # Merge duplicates
        for norm_key, col_list in column_groups.items():
            if len(col_list) > 1:
                self.stats['duplicate_columns_merged'] += len(col_list) - 1

                # Keep the first key, merge all info
                primary_key, primary_col = col_list[0]

                for col_key, col_info in col_list[1:]:
                    # Merge sources
                    primary_col.source_columns.update(col_info.source_columns)
                    primary_col.transforms.update(col_info.transforms)
                    primary_col.defining_scripts.update(col_info.defining_scripts)
                    primary_col.cte_dependencies.update(col_info.cte_dependencies)

                    # Merge expressions (limit to prevent bloat)
                    for expr in col_info.expressions:
                        if expr not in primary_col.expressions and len(primary_col.expressions) < 10:
                            primary_col.expressions.append(expr)

                    # Update flags
                    if col_info.is_derived:
                        primary_col.is_derived = True
                    if col_info.is_aggregate:
                        primary_col.is_aggregate = True
                    if col_info.is_calculated:
                        primary_col.is_calculated = True

                    # Remove duplicate
                    if col_key in self.columns:
                        del self.columns[col_key]

        print(f"   Merged {self.stats['duplicate_columns_merged']} duplicate columns")

    def _calculate_confidence_scores(self):
        """Calculate confidence scores for column lineage"""
        for col_info in self.columns.values():
            # Start with base confidence
            confidence = 1.0

            # Direct mapping = high confidence
            if 'direct' in col_info.transforms:
                confidence = 1.0

            # Multiple transforms = medium confidence
            elif len(col_info.transforms) > 2:
                confidence = 0.7

            # Aggregate = medium-high confidence
            elif col_info.is_aggregate:
                confidence = 0.85

            # Many sources = lower confidence (complex calculation)
            if len(col_info.source_columns) > 5:
                confidence *= 0.8

            # CTE dependencies = slight reduction
            if col_info.cte_dependencies:
                confidence *= 0.95

            # Multiple defining scripts = possible conflict
            if len(col_info.defining_scripts) > 1:
                confidence *= 0.9

            col_info.confidence_score = round(confidence, 2)

    def _calculate_execution_order(self) -> Dict:
        """Calculate table execution order via topological sort"""
        in_degree = defaultdict(int)
        adj_list = defaultdict(list)

        # Initialize all tables
        for table in self.tables:
            if table not in in_degree:
                in_degree[table] = 0

        # Build adjacency list
        for table, deps in self.table_dependencies.items():
            for dep in deps:
                adj_list[dep].append(table)
                in_degree[table] += 1

        # Topological sort (Kahn's algorithm)
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

        # Detect circular dependencies
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
        """Build final JSON report structure"""
        # Build tables section
        tables_json = {}
        for table_name, table_info in self.tables.items():
            tables_json[table_name] = {
                "definition_scripts": list(table_info.definition_scripts),
                "definition_types": list(table_info.definition_types),
                "statement_subtypes": list(table_info.statement_subtypes),
                "columns": list(table_info.columns.keys()),
                "depends_on": list(self.table_dependencies.get(table_name, set())),
                "is_temp": table_info.is_temp,
                "is_cte": table_info.is_cte,
                "is_view": table_info.is_view,
                "column_count": len(table_info.columns)
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
                "cte_dependencies": list(col_info.cte_dependencies),
                "defining_scripts": list(col_info.defining_scripts),
                "confidence_score": col_info.confidence_score,
                "sample_expressions": col_info.expressions[:3]  # Limit to 3 examples
            }

        # Build CTEs section
        ctes_json = {}
        for cte_name, cte_list in self.ctes.items():
            ctes_json[cte_name] = [{
                "defining_script": cte.defining_script,
                "columns": cte.columns,
                "source_tables": cte.source_tables,
                "query_snippet": cte.query_snippet
            } for cte in cte_list]

        # Build temp tables section
        temp_tables_json = {}
        for temp_name, temp_info in self.temp_tables.items():
            temp_tables_json[temp_name] = {
                "columns": list(temp_info.columns.keys()),
                "definition_scripts": list(temp_info.definition_scripts)
            }

        # Build final report
        report = {
            "metadata": {
                "dialect": self.dialect,
                "source_directory": self.source_directory,
                "parsing_strategy": "enhanced_lenient",
                "version": "2.0"
            },
            "summary": {
                "total_scripts": self.stats['total_scripts'],
                "total_tables": len(self.tables),
                "total_columns": len(self.columns),
                "total_dependencies": sum(len(deps) for deps in self.table_dependencies.values()),
                "temp_tables": self.stats['temp_table_count'],
                "ctes": self.stats['cte_count'],
                "dynamic_sql_count": self.stats['dynamic_sql_count'],
                "set_operations": self.stats['set_operations'],
                "parse_errors": self.stats['parse_errors'],
                "successful_parses": self.stats['successful_parses'],
                "duplicate_columns_merged": self.stats['duplicate_columns_merged'],
                "variant_access_count": self.stats['variant_access_count'],
                "lateral_flatten_count": self.stats['lateral_flatten_count']
            },
            "execution_order": execution_order,
            "tables": tables_json,
            "columns": columns_json,
            "ctes": ctes_json,
            "temp_tables": temp_tables_json,
            "warnings": {
                "circular_dependencies": self.stats['circular_dependencies'],
                "dynamic_sql_detected": self.stats['dynamic_sql_count'] > 0
            }
        }

        return report

    def _remove_placeholder_columns_when_defined(self) -> None:
        """Remove auto-generated placeholder columns (column_0, column_1, ...) when a table has real definitions.

        This prevents placeholder names from leaking into the final report once the original columns
        are available via CREATE TABLE or any non-placeholder column entries.
        """
        placeholder_pattern = re.compile(r"^column_\d+$", re.IGNORECASE)

        for table_name, table_info in self.tables.items():
            column_names = list(table_info.columns.keys())
            has_real_columns = any(not placeholder_pattern.match(col) for col in column_names)

            # If we have any real columns or the table was created explicitly, drop placeholders
            if has_real_columns or ("CREATE" in table_info.definition_types):
                for col in column_names:
                    if placeholder_pattern.match(col):
                        # Remove from table's column registry
                        table_info.columns.pop(col, None)
                        # Remove from global columns registry
                        self.columns.pop(f"{table_name}.{col}", None)

    def _is_temp_table(self, table_name: str) -> bool:
        """Check if table is temporary"""
        temp_prefixes = ['temp_', 'tmp_', 'staging_', 'stg_']
        temp_suffixes = ['_temp', '_tmp', '_staging', '_stg']

        lower_name = table_name.lower()

        # Check prefixes
        if any(lower_name.startswith(prefix) for prefix in temp_prefixes):
            return True

        # Check suffixes
        if any(lower_name.endswith(suffix) for suffix in temp_suffixes):
            return True

        return False

    def save_report(self, report: Dict, output_path: str):
        """Save report to JSON file"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n   Report saved to: {output_path}")


if __name__ == "__main__":
    builder = EnhancedLineageJSONBuilder("snowflake", "./sql_files")
    
    mock_results = []

    report = builder.build_lineage_report(mock_results)
    print(json.dumps(report, indent=2))
