"""
Metadata Statement Builder for Oracle
Builds lineage JSON reports from analyzed views and query history.

This module produces the same output format as EnhancedLineageJSONBuilder
but works with metadata-based analysis results instead of file-based results.
Supports Oracle-specific features including packages, hierarchical queries,
PIVOT/UNPIVOT, and database links.
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
    has_connect_by: bool = False  # Oracle CONNECT BY
    has_pivot: bool = False  # Oracle PIVOT/UNPIVOT
    has_model: bool = False  # Oracle MODEL clause


@dataclass
class TableInfo:
    """Aggregated table information with Oracle-specific flags"""
    table_name: str
    columns: Dict[str, ColumnInfo] = field(default_factory=dict)
    definition_sources: Set[str] = field(default_factory=set)
    definition_types: Set[str] = field(default_factory=set)
    depends_on: Set[str] = field(default_factory=set)
    is_temp: bool = False
    is_cte: bool = False
    is_view: bool = False
    is_global_temp: bool = False  # Oracle GLOBAL TEMPORARY table
    is_materialized_view: bool = False  # Oracle Materialized View
    statement_subtypes: Set[str] = field(default_factory=set)
    oracle_features: Set[str] = field(default_factory=set)  # Track Oracle features used


@dataclass
class CTEInfo:
    """CTE definition information"""
    name: str
    defining_source: str
    columns: List[str] = field(default_factory=list)
    source_tables: List[str] = field(default_factory=list)
    query_snippet: str = ""


@dataclass
class PackageInfo:
    """Oracle package information"""
    name: str
    owner: Optional[str] = None
    package_type: str = "PACKAGE"  # PACKAGE or PACKAGE BODY
    defining_source: str = ""
    procedures: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    description: str = ""


class MetadataStatementBuilder:
    """
    Build comprehensive lineage JSON report from metadata-based analysis.

    Produces the same output format as EnhancedLineageJSONBuilder for
    frontend compatibility, with additional support for Oracle-specific
    features including packages, hierarchical queries, and materialized views.
    """

    def __init__(
        self,
        dialect: str = "oracle",
        database_name: str = "",
        metadata: Optional[Dict] = None
    ):
        """
        Initialize the builder.

        Args:
            dialect: SQL dialect (default: "oracle")
            database_name: Database name
            metadata: Database metadata for context
        """
        self.dialect = dialect
        self.database_name = database_name
        self.metadata = metadata or {}

        # Aggregated data structures
        self.tables: Dict[str, TableInfo] = {}
        self.columns: Dict[Tuple[str, str], ColumnInfo] = {}  # (table, column)
        self.ctes: Dict[str, CTEInfo] = {}
        self.packages: Dict[str, PackageInfo] = {}

        # Track processing stats
        self.stats = defaultdict(int)

    def add_view_lineage(self, lineage: Any):
        """
        Add lineage from a single view analysis.

        Args:
            lineage: ViewLineage object from MetadataViewAnalyzer
        """
        view_name = lineage.name
        self.stats['views_processed'] += 1

        # Register the view as a table
        if view_name not in self.tables:
            self.tables[view_name] = TableInfo(
                table_name=view_name,
                is_view=True
            )

        view_info = self.tables[view_name]
        view_info.definition_sources.add(view_name)
        view_info.definition_types.add("VIEW")

        # Add Oracle features
        if lineage.oracle_features:
            view_info.oracle_features.update(lineage.oracle_features)

        # Add statement subtypes
        if lineage.statement_subtype:
            view_info.statement_subtypes.add(lineage.statement_subtype)

        # Register source tables
        for source_table in lineage.source_tables:
            view_info.depends_on.add(source_table)

            # Ensure source table exists in our registry
            if source_table not in self.tables:
                self.tables[source_table] = TableInfo(table_name=source_table)

        # Process CTEs
        for cte_name, cte_def in lineage.cte_definitions.items():
            if cte_name not in self.ctes:
                self.ctes[cte_name] = CTEInfo(
                    name=cte_name,
                    defining_source=view_name,
                    columns=cte_def.get('columns', []),
                    source_tables=cte_def.get('source_tables', [])
                )

        # Process column lineage
        for col_lineage in lineage.column_lineage:
            self._add_column_lineage(
                target_table=col_lineage.target_table,
                target_column=col_lineage.target_column,
                source_columns=col_lineage.source_columns,
                transform_type=col_lineage.transform_type,
                expression=col_lineage.expression,
                is_aggregate=col_lineage.is_aggregate,
                is_calculated=col_lineage.is_calculated,
                cte_dependency=col_lineage.cte_dependency,
                defining_source=view_name,
                has_connect_by=col_lineage.has_connect_by,
                has_pivot=col_lineage.has_pivot,
                has_model=col_lineage.has_model
            )

    def _add_column_lineage(
        self,
        target_table: str,
        target_column: str,
        source_columns: List[Dict[str, str]],
        transform_type: str,
        expression: str,
        is_aggregate: bool,
        is_calculated: bool,
        cte_dependency: Optional[str],
        defining_source: str,
        has_connect_by: bool = False,
        has_pivot: bool = False,
        has_model: bool = False
    ):
        """Add or update column lineage information"""
        key = (target_table, target_column)

        if key not in self.columns:
            self.columns[key] = ColumnInfo(
                name=target_column,
                table=target_table
            )

        col_info = self.columns[key]

        # Add source columns
        for source in source_columns:
            source_table = source.get('table', 'UNKNOWN')
            source_column = source.get('column', '')
            if source_column:
                col_info.source_columns.add((source_table, source_column))

        # Add transform information
        col_info.transforms.add(transform_type)

        if is_aggregate:
            col_info.is_aggregate = True
        if is_calculated:
            col_info.is_calculated = True
        if is_aggregate or is_calculated or len(source_columns) > 1:
            col_info.is_derived = True

        # Add expression
        if expression and expression not in col_info.expressions:
            col_info.expressions.append(expression)

        # Add defining source
        col_info.defining_sources.add(defining_source)

        # Add CTE dependency
        if cte_dependency:
            col_info.cte_dependencies.add(cte_dependency)

        # Oracle-specific flags
        if has_connect_by:
            col_info.has_connect_by = True
        if has_pivot:
            col_info.has_pivot = True
        if has_model:
            col_info.has_model = True

        # Ensure column is registered in table
        if target_table in self.tables:
            table_info = self.tables[target_table]
            table_info.columns[target_column] = col_info

    def add_package_info(self, package: Dict):
        """Add Oracle package information"""
        package_name = package.get('package_name', '')
        owner = package.get('owner', '')
        package_type = package.get('object_type', 'PACKAGE')

        qualified_name = f"{owner}.{package_name}" if owner else package_name

        if qualified_name not in self.packages:
            self.packages[qualified_name] = PackageInfo(
                name=package_name,
                owner=owner,
                package_type=package_type,
                defining_source=qualified_name
            )

    def build_report(self) -> Dict[str, Any]:
        """
        Build the complete lineage report.

        Returns:
            Dictionary with comprehensive lineage information
        """
        # Build table-level lineage
        table_lineage = self._build_table_lineage()

        # Build column-level lineage
        column_lineage = self._build_column_lineage()

        # Build dependency graph
        dependency_graph = self._build_dependency_graph()

        # Build summary
        summary = self._build_summary()

        # Build Oracle-specific sections
        oracle_info = self._build_oracle_info()

        report = {
            "metadata": {
                "database": self.database_name,
                "dialect": self.dialect,
                "generation_timestamp": datetime.utcnow().isoformat(),
                "total_tables": len(self.tables),
                "total_columns": len(self.columns),
                "total_ctes": len(self.ctes),
                "total_packages": len(self.packages),
            },
            "table_lineage": table_lineage,
            "column_lineage": column_lineage,
            "dependency_graph": dependency_graph,
            "cte_definitions": self._format_ctes(),
            "oracle_specific": oracle_info,
            "summary": summary,
            "statistics": dict(self.stats)
        }

        return report

    def _build_table_lineage(self) -> List[Dict[str, Any]]:
        """Build table-level lineage"""
        lineage = []

        for table_name, table_info in self.tables.items():
            entry = {
                "table_name": table_name,
                "depends_on": sorted(list(table_info.depends_on)),
                "column_count": len(table_info.columns),
                "is_view": table_info.is_view,
                "is_cte": table_info.is_cte,
                "is_temp": table_info.is_temp,
                "is_global_temp": table_info.is_global_temp,
                "is_materialized_view": table_info.is_materialized_view,
                "definition_sources": sorted(list(table_info.definition_sources)),
                "definition_types": sorted(list(table_info.definition_types)),
                "statement_subtypes": sorted(list(table_info.statement_subtypes)),
                "oracle_features": sorted(list(table_info.oracle_features)),
            }
            lineage.append(entry)

        return sorted(lineage, key=lambda x: x['table_name'])

    def _build_column_lineage(self) -> List[Dict[str, Any]]:
        """Build column-level lineage"""
        lineage = []

        for (table_name, col_name), col_info in self.columns.items():
            entry = {
                "target_table": table_name,
                "target_column": col_name,
                "source_columns": [
                    {"table": t, "column": c}
                    for t, c in sorted(col_info.source_columns)
                ],
                "transforms": sorted(list(col_info.transforms)),
                "is_derived": col_info.is_derived,
                "is_aggregate": col_info.is_aggregate,
                "is_calculated": col_info.is_calculated,
                "expressions": col_info.expressions,
                "defining_sources": sorted(list(col_info.defining_sources)),
                "cte_dependencies": sorted(list(col_info.cte_dependencies)),
                "confidence_score": col_info.confidence_score,
                "oracle_features": {
                    "has_connect_by": col_info.has_connect_by,
                    "has_pivot": col_info.has_pivot,
                    "has_model": col_info.has_model,
                }
            }
            lineage.append(entry)

        return sorted(lineage, key=lambda x: (x['target_table'], x['target_column']))

    def _build_dependency_graph(self) -> Dict[str, Any]:
        """Build table dependency graph for visualization"""
        nodes = []
        edges = []

        # Create nodes for each table
        for table_name, table_info in self.tables.items():
            node = {
                "id": table_name,
                "label": table_name,
                "type": self._get_node_type(table_info),
                "column_count": len(table_info.columns),
                "oracle_features": sorted(list(table_info.oracle_features)),
            }
            nodes.append(node)

        # Create edges for dependencies
        for table_name, table_info in self.tables.items():
            for source_table in table_info.depends_on:
                edge = {
                    "from": source_table,
                    "to": table_name,
                    "type": "data_flow"
                }
                edges.append(edge)

        return {
            "nodes": nodes,
            "edges": edges
        }

    def _get_node_type(self, table_info: TableInfo) -> str:
        """Determine node type for visualization"""
        if table_info.is_view:
            return "view"
        elif table_info.is_materialized_view:
            return "materialized_view"
        elif table_info.is_cte:
            return "cte"
        elif table_info.is_global_temp:
            return "global_temp"
        else:
            return "table"

    def _format_ctes(self) -> List[Dict[str, Any]]:
        """Format CTE information"""
        cte_list = []

        for cte_name, cte_info in self.ctes.items():
            entry = {
                "name": cte_name,
                "defining_source": cte_info.defining_source,
                "columns": cte_info.columns,
                "source_tables": cte_info.source_tables,
                "query_snippet": cte_info.query_snippet
            }
            cte_list.append(entry)

        return sorted(cte_list, key=lambda x: x['name'])

    def _build_oracle_info(self) -> Dict[str, Any]:
        """Build Oracle-specific information section"""
        oracle_info = {
            "packages": [
                {
                    "name": pkg.name,
                    "owner": pkg.owner,
                    "type": pkg.package_type,
                    "procedures": pkg.procedures,
                    "functions": pkg.functions,
                }
                for pkg in self.packages.values()
            ],
            "feature_usage": self._analyze_feature_usage(),
            "hierarchical_queries": self._count_feature("CONNECT_BY"),
            "pivot_operations": self._count_feature("PIVOT"),
            "model_clauses": self._count_feature("MODEL"),
            "flashback_queries": self._count_feature("FLASHBACK"),
            "database_links": self._count_feature("DATABASE_LINK"),
        }

        return oracle_info

    def _analyze_feature_usage(self) -> Dict[str, int]:
        """Analyze usage of Oracle-specific features"""
        feature_counts = defaultdict(int)

        for table_info in self.tables.values():
            for feature in table_info.oracle_features:
                feature_counts[feature] += 1

        return dict(feature_counts)

    def _count_feature(self, feature_name: str) -> int:
        """Count occurrences of a specific Oracle feature"""
        count = 0
        for table_info in self.tables.values():
            if feature_name in table_info.oracle_features:
                count += 1
        return count

    def _build_summary(self) -> Dict[str, Any]:
        """Build summary statistics"""
        return {
            "total_tables": len(self.tables),
            "total_views": sum(1 for t in self.tables.values() if t.is_view),
            "total_materialized_views": sum(1 for t in self.tables.values() if t.is_materialized_view),
            "total_global_temp_tables": sum(1 for t in self.tables.values() if t.is_global_temp),
            "total_ctes": len(self.ctes),
            "total_columns": len(self.columns),
            "total_packages": len(self.packages),
            "derived_columns": sum(1 for c in self.columns.values() if c.is_derived),
            "aggregate_columns": sum(1 for c in self.columns.values() if c.is_aggregate),
            "calculated_columns": sum(1 for c in self.columns.values() if c.is_calculated),
        }

    def save_report(self, output_path: str):
        """Save report to JSON file"""
        report = self.build_report()

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)

        print(f"Lineage report saved to: {output_path}")

    def get_stats(self) -> Dict[str, int]:
        """Get processing statistics"""
        return dict(self.stats)
