"""
Enhanced Procedure JSON Builder for Teradata
Processes LLM-analyzed lineage data and builds comprehensive JSON outputs
Optimized for LLM-generated lineage with full context
Supports Teradata-specific elements: procedures, functions, macros, volatile tables
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Set, Optional
from datetime import datetime
from collections import defaultdict


class EnhancedProcedureJSONBuilder:
    """
    Build comprehensive JSON outputs from LLM-analyzed Teradata lineage data.
    Creates multiple output files optimized for different use cases.
    Supports Teradata-specific elements: macros, volatile tables, etc.
    """

    def __init__(self, output_dir: Path = Path("lineage_output")):
        """
        Initialize the JSON builder.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.analysis_results = []
        self.dependency_graph = defaultdict(set)
        self.column_lineage_map = defaultdict(list)
        self.table_usage_stats = defaultdict(lambda: {
            'read_count': 0,
            'write_count': 0,
            'procedures': set(),
            'functions': set(),
            'macros': set(),  # Teradata-specific
            'columns_used': set()
        })
        self.volatile_table_usage = defaultdict(set)  # Track volatile table usage

    def add_analysis_results(self, results: List[Dict[str, Any]]):
        """
        Add LLM analysis results to the builder and process them.

        Args:
            results: List of analyzed procedure/function/macro results
        """
        self.analysis_results.extend(results)
        self._process_results(results)

    def _process_results(self, results: List[Dict[str, Any]]):
        """
        Process LLM analysis results to build dependency graphs and statistics.
        Optimized for LLM-generated lineage structure.
        Handles Teradata-specific elements.
        """

        for result in results:
            stmt_name = result.get('name', 'unknown')
            stmt_type = result.get('type', 'UNKNOWN')
            lineage = result.get('lineage_analysis', {}) or {}

            # Skip if analysis failed
            if 'error' in lineage:
                continue

            # Process table dependencies
            dependencies = lineage.get('dependencies') or {}
            for table in dependencies.get('tables') or []:
                self.dependency_graph[stmt_name].add(table)
                self.table_usage_stats[table]['read_count'] += 1

                # Track by statement type (including macros)
                if stmt_type.upper() in ['PROCEDURE', 'STORED_PROCEDURE']:
                    self.table_usage_stats[table]['procedures'].add(stmt_name)
                elif 'FUNCTION' in stmt_type.upper():
                    self.table_usage_stats[table]['functions'].add(stmt_name)
                elif stmt_type.upper() == 'MACRO':
                    self.table_usage_stats[table]['macros'].add(stmt_name)

            # Process source tables with columns
            for source_table in lineage.get('source_tables') or []:
                table_name = source_table.get('table_list')
                if table_name:
                    self.table_usage_stats[table_name]['read_count'] += 1

                    if stmt_type.upper() in ['PROCEDURE', 'STORED_PROCEDURE']:
                        self.table_usage_stats[table_name]['procedures'].add(stmt_name)
                    elif 'FUNCTION' in stmt_type.upper():
                        self.table_usage_stats[table_name]['functions'].add(stmt_name)
                    elif stmt_type.upper() == 'MACRO':
                        self.table_usage_stats[table_name]['macros'].add(stmt_name)

                    # Track specific columns used
                    for col in source_table.get('columns_used', []):
                        self.table_usage_stats[table_name]['columns_used'].add(col)

            # Process target table (writes)
            target = lineage.get('target') or {}
            target_name = target.get('name')
            if target_name:
                operation = target.get('operation', '').upper()
                if operation in ['INSERT', 'UPDATE', 'DELETE', 'CREATE', 'MERGE']:
                    self.table_usage_stats[target_name]['write_count'] += 1

                    if stmt_type.upper() in ['PROCEDURE', 'STORED_PROCEDURE']:
                        self.table_usage_stats[target_name]['procedures'].add(stmt_name)
                    elif 'FUNCTION' in stmt_type.upper():
                        self.table_usage_stats[target_name]['functions'].add(stmt_name)
                    elif stmt_type.upper() == 'MACRO':
                        self.table_usage_stats[target_name]['macros'].add(stmt_name)

            # Process volatile tables (Teradata-specific)
            for volatile_table in lineage.get('intermediate_objects') or []:
                if volatile_table.get('type') == 'VOLATILE_TABLE':
                    self.volatile_table_usage[stmt_name].add(volatile_table.get('name'))

            # Process column-level lineage
            for col_lineage in lineage.get('column_lineage') or []:
                target_col = col_lineage.get('target_column')
                if target_col:
                    self.column_lineage_map[target_col].append({
                        'procedure': stmt_name,
                        'type': stmt_type,
                        'source_columns': col_lineage.get('source_columns', []),
                        'transformation': col_lineage.get('transformation', {})
                    })

    def _build_summary_statistics(self) -> Dict[str, Any]:
        """
        Build comprehensive summary statistics from LLM-analyzed results.
        Includes Teradata-specific metrics.
        """

        total_statements = len(self.analysis_results)
        successful = sum(1 for r in self.analysis_results if r.get('analysis_success'))
        failed = total_statements - successful

        # Count by type (including macros)
        by_type = defaultdict(int)
        procedures_count = 0
        functions_count = 0
        macros_count = 0

        for result in self.analysis_results:
            stmt_type = result.get('type', 'UNKNOWN')
            by_type[stmt_type] += 1

            if stmt_type.upper() in ['PROCEDURE', 'STORED_PROCEDURE']:
                procedures_count += 1
            elif 'FUNCTION' in stmt_type.upper():
                functions_count += 1
            elif stmt_type.upper() == 'MACRO':
                macros_count += 1

        # Calculate complexity metrics from LLM analysis
        total_tables = len(self.table_usage_stats)
        total_dependencies = sum(len(deps) for deps in self.dependency_graph.values())
        total_volatile_tables = sum(len(vts) for vts in self.volatile_table_usage.values())

        # Analyze complexity of procedures/functions/macros
        complexity_scores = []
        for result in self.analysis_results:
            lineage = result.get('lineage_analysis', {}) or {}
            if 'error' not in lineage:
                metrics = lineage.get('complexity_metrics') or {}
                complexity_scores.append({
                    'name': result.get('name'),
                    'type': result.get('type'),
                    'num_tables': metrics.get('num_tables', 0),
                    'num_joins': metrics.get('num_joins', 0),
                    'num_calculations': metrics.get('num_calculations', 0),
                    'has_aggregation': metrics.get('has_aggregation', False),
                    'has_window_functions': metrics.get('has_window_functions', False),
                    'has_subqueries': metrics.get('has_subqueries', False),
                    'has_cte': metrics.get('has_cte', False),
                    'uses_volatile_tables': len(self.volatile_table_usage.get(result.get('name'), [])) > 0
                })

        # Sort by complexity score
        complexity_scores.sort(
            key=lambda x: (
                x['num_tables'] +
                x['num_joins'] * 2 +
                x['num_calculations'] +
                (10 if x['has_aggregation'] else 0) +
                (10 if x['has_window_functions'] else 0) +
                (5 if x['has_subqueries'] else 0) +
                (5 if x['has_cte'] else 0) +
                (3 if x['uses_volatile_tables'] else 0)
            ),
            reverse=True
        )

        # LLM provider statistics
        llm_providers = defaultdict(int)
        for result in self.analysis_results:
            provider = result.get('llm_provider', 'Unknown')
            llm_providers[provider] += 1

        return {
            'total_statements_analyzed': total_statements,
            'successful_analyses': successful,
            'failed_analyses': failed,
            'success_rate': f"{(successful/max(total_statements,1)*100):.2f}%",
            'statements_by_type': dict(by_type),
            'procedures_count': procedures_count,
            'functions_count': functions_count,
            'macros_count': macros_count,  # Teradata-specific
            'total_unique_tables': total_tables,
            'total_dependencies': total_dependencies,
            'total_volatile_tables_used': total_volatile_tables,  # Teradata-specific
            'most_complex_procedures': complexity_scores[:10],
            'llm_providers': dict(llm_providers),
            'analysis_method': 'LLM-based',
            'database_type': 'Teradata',
            'generated_at': datetime.utcnow().isoformat()
        }

    def _build_procedure_catalog(self) -> List[Dict[str, Any]]:
        """
        Build a comprehensive catalog of all analyzed Executable Components.
        Optimized for LLM-generated lineage data.
        Includes Teradata-specific elements.
        """

        catalog = []

        for result in self.analysis_results:
            lineage = result.get('lineage_analysis', {}) or {}

            # Build base entry
            entry = {
                'name': result.get('name'),
                'type': result.get('type'),
                'description': result.get('description', ''),
                'analysis_success': result.get('analysis_success', False),
                'analyzed_at': result.get('analyzed_at'),
                'analysis_method': result.get('analysis_method', 'LLM'),
                'llm_provider': result.get('llm_provider', 'Unknown'),
                'original_sql': result.get('original_sql', ''),
                'modified_sql': result.get('modified_sql', ''),
                'was_sql_modified': result.get('was_modified', False),
                'table_context_used': result.get('table_context_used', [])
            }

            if 'error' not in lineage:
                # Add LLM-extracted lineage information
                entry['statement_info'] = lineage.get('statement_info') or {}
                entry['source_tables'] = lineage.get('source_tables') or []
                entry['target'] = lineage.get('target') or {}
                entry['dependencies'] = lineage.get('dependencies') or {}
                entry['complexity_metrics'] = lineage.get('complexity_metrics') or {}
                entry['filters'] = lineage.get('filters') or {}
                entry['intermediate_objects'] = lineage.get('intermediate_objects') or []
                entry['column_lineage_count'] = len(lineage.get('column_lineage') or [])

                # Teradata-specific: volatile table usage
                stmt_name = result.get('name')
                if stmt_name in self.volatile_table_usage:
                    entry['volatile_tables_used'] = sorted(list(self.volatile_table_usage[stmt_name]))
                else:
                    entry['volatile_tables_used'] = []

                # Add summary of lineage depth
                entry['lineage_summary'] = {
                    'num_source_tables': len(lineage.get('source_tables') or []),
                    'num_source_columns': sum(
                        len(t.get('columns_used') or [])
                        for t in lineage.get('source_tables') or []
                    ),
                    'num_target_columns': len((lineage.get('target') or {}).get('columns_affected') or []),
                    'num_column_mappings': len(lineage.get('column_lineage') or []),
                    'num_volatile_tables': len(entry['volatile_tables_used'])
                }
            else:
                entry['error'] = lineage.get('error')
                entry['raw_response'] = lineage.get('raw_response', '')[:200]

            catalog.append(entry)

        # Sort by type, then name
        catalog.sort(key=lambda x: (x['type'], x['name']))

        return catalog

    def _build_column_lineage_catalog(self) -> List[Dict[str, Any]]:
        """
        Build detailed column-level lineage catalog from LLM analysis.
        """

        catalog = []

        for result in self.analysis_results:
            lineage = result.get('lineage_analysis', {})

            if 'error' in lineage:
                continue

            stmt_name = result.get('name')
            stmt_type = result.get('type')

            for col_lineage in lineage.get('column_lineage', []):
                target_column = col_lineage.get('target_column')
                source_columns = col_lineage.get('source_columns', [])
                transformation = col_lineage.get('transformation', {})

                if target_column:
                    catalog.append({
                        'procedure_name': stmt_name,
                        'procedure_type': stmt_type,
                        'target_column': target_column,
                        'source_columns': source_columns,
                        'num_sources': len(source_columns),
                        'transformation_type': transformation.get('type', 'UNKNOWN'),
                        'transformation_expression': transformation.get('expression', ''),
                        'functions_used': transformation.get('functions_used', []),
                        'is_calculated': transformation.get('type') not in ['DIRECT', 'PASSTHROUGH'],
                        'analyzed_at': result.get('analyzed_at')
                    })

        # Sort by procedure, then target column
        catalog.sort(key=lambda x: (x['procedure_name'], x['target_column']))

        return catalog

    def _build_dependency_graph_export(self) -> Dict[str, Any]:
        """
        Build a graph structure suitable for visualization tools.
        Includes procedures, functions, macros, tables, and volatile tables.
        """

        nodes = []
        edges = []
        node_ids = set()

        # Add procedure/function/macro nodes
        for result in self.analysis_results:
            node_id = result.get('name')
            node_type = result.get('type')

            if node_id not in node_ids:
                lineage = result.get('lineage_analysis', {})
                metrics = lineage.get('complexity_metrics', {})

                # Determine category
                if 'PROCEDURE' in node_type.upper():
                    category = 'procedure'
                elif 'FUNCTION' in node_type.upper():
                    category = 'function'
                elif 'MACRO' in node_type.upper():
                    category = 'macro'
                else:
                    category = 'executable'

                nodes.append({
                    'id': node_id,
                    'type': node_type,
                    'label': node_id,
                    'complexity': {
                        'tables': metrics.get('num_tables', 0),
                        'joins': metrics.get('num_joins', 0),
                        'calculations': metrics.get('num_calculations', 0)
                    },
                    'category': category
                })
                node_ids.add(node_id)

        # Add table nodes and edges
        for stmt_name, deps in self.dependency_graph.items():
            for table_name in deps:
                # Add table node if not exists
                if table_name not in node_ids:
                    nodes.append({
                        'id': table_name,
                        'type': 'TABLE',
                        'label': table_name,
                        'category': 'table'
                    })
                    node_ids.add(table_name)

                # Add edge from procedure/function/macro to table
                edges.append({
                    'source': stmt_name,
                    'target': table_name,
                    'type': 'DEPENDS_ON'
                })

        # Add volatile table nodes and edges (Teradata-specific)
        for stmt_name, volatile_tables in self.volatile_table_usage.items():
            for vt_name in volatile_tables:
                # Add volatile table node if not exists
                if vt_name not in node_ids:
                    nodes.append({
                        'id': vt_name,
                        'type': 'VOLATILE_TABLE',
                        'label': vt_name,
                        'category': 'volatile_table'
                    })
                    node_ids.add(vt_name)

                # Add edge from procedure/function/macro to volatile table
                edges.append({
                    'source': stmt_name,
                    'target': vt_name,
                    'type': 'CREATES_VOLATILE'
                })

        return {
            'metadata': {
                'generated_at': datetime.utcnow().isoformat(),
                'database_type': 'Teradata',
                'total_nodes': len(nodes),
                'total_edges': len(edges)
            },
            'nodes': nodes,
            'edges': edges,
            'format': 'directed_graph'
        }

    def _build_table_usage_report(self) -> List[Dict[str, Any]]:
        """
        Build a comprehensive Tabular Components usage report.
        Shows which Executable Components read/write each Tabular Component.
        Includes Teradata-specific macros.
        """

        report = []

        for table_name, stats in self.table_usage_stats.items():
            report.append({
                'table_name': table_name,
                'read_count': stats['read_count'],
                'write_count': stats['write_count'],
                'total_operations': stats['read_count'] + stats['write_count'],
                'procedures': sorted(list(stats['procedures'])),
                'functions': sorted(list(stats['functions'])),
                'macros': sorted(list(stats['macros'])),  # Teradata-specific
                'total_procedures': len(stats['procedures']),
                'total_functions': len(stats['functions']),
                'total_macros': len(stats['macros']),  # Teradata-specific
                'columns_referenced': sorted(list(stats['columns_used'])),
                'num_columns_referenced': len(stats['columns_used'])
            })

        # Sort by total operations (most used first)
        report.sort(key=lambda x: x['total_operations'], reverse=True)

        return report

    def _build_volatile_table_report(self) -> List[Dict[str, Any]]:
        """
        Build a report of volatile table usage (Teradata-specific).
        Shows which procedures/functions/macros use which volatile tables.
        """

        report = []

        # Invert the mapping: volatile table -> statements that use it
        vt_to_statements = defaultdict(list)
        for stmt_name, volatile_tables in self.volatile_table_usage.items():
            for vt_name in volatile_tables:
                # Find the statement type
                stmt_type = 'UNKNOWN'
                for result in self.analysis_results:
                    if result.get('name') == stmt_name:
                        stmt_type = result.get('type', 'UNKNOWN')
                        break

                vt_to_statements[vt_name].append({
                    'name': stmt_name,
                    'type': stmt_type
                })

        for vt_name, statements in vt_to_statements.items():
            report.append({
                'volatile_table_name': vt_name,
                'used_by_count': len(statements),
                'used_by': statements
            })

        # Sort by usage count (most used first)
        report.sort(key=lambda x: x['used_by_count'], reverse=True)

        return report

    def generate_all_outputs(self, prefix: str = "lineage") -> Dict[str, Path]:
        """
        Generate all output files for LLM-analyzed Teradata lineage.

        Args:
            prefix: Prefix for output filenames

        Returns:
            Dictionary mapping output type to file path
        """

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        output_files = {}

        print(f"\n{'='*80}")
        print("GENERATING TERADATA LINEAGE OUTPUT FILES")
        print(f"{'='*80}")

        # 1. Complete Analysis Results (all LLM data)
        complete_file = self.output_dir / f"{prefix}_complete_{timestamp}.json"
        complete_data = {
            'metadata': {
                'generated_at': datetime.utcnow().isoformat(),
                'database_type': 'Teradata',
                'total_statements': len(self.analysis_results),
                'output_version': '3.0',
                'analysis_method': 'LLM-based (Ollama/OpenAI)'
            },
            'summary': self._build_summary_statistics(),
            'analysis_results': self.analysis_results
        }

        with open(complete_file, 'w', encoding='utf-8') as f:
            json.dump(complete_data, f, indent=2, default=str)
        output_files['complete'] = complete_file
        print(f"✓ Complete analysis: {complete_file.name}")
        
        catalog_file = self.output_dir / f"{prefix}_executable_components_catalog_{timestamp}.json"
        catalog_data = {
            'metadata': {
                'generated_at': datetime.utcnow().isoformat(),
                'database_type': 'Teradata',
                'total_executable_components': len(self.analysis_results),
                'analysis_method': 'LLM-based'
            },
            'summary': self._build_summary_statistics(),
            'executable_components': self._build_procedure_catalog()
        }

        with open(catalog_file, 'w', encoding='utf-8') as f:
            json.dump(catalog_data, f, indent=2, default=str)
        output_files['catalog'] = catalog_file
        print(f"✓ Executable Components catalog: {catalog_file.name}")

        # 3. Column Lineage (detailed column-level mappings)
        column_file = self.output_dir / f"{prefix}_column_lineage_{timestamp}.json"
        column_lineage_catalog = self._build_column_lineage_catalog()
        column_data = {
            'metadata': {
                'generated_at': datetime.utcnow().isoformat(),
                'database_type': 'Teradata',
                'total_column_mappings': len(column_lineage_catalog),
                'analysis_method': 'LLM-extracted'
            },
            'column_lineage': column_lineage_catalog
        }

        with open(column_file, 'w', encoding='utf-8') as f:
            json.dump(column_data, f, indent=2, default=str)
        output_files['column_lineage'] = column_file
        print(f"✓ Column lineage: {column_file.name}")

        # 4. Dependency Graph (for visualization tools)
        graph_file = self.output_dir / f"{prefix}_dependency_graph_{timestamp}.json"
        graph_data = self._build_dependency_graph_export()

        with open(graph_file, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, indent=2, default=str)
        output_files['dependency_graph'] = graph_file
        print(f"✓ Dependency graph: {graph_file.name}")

        # 5. Tabular Components Usage Report
        table_file = self.output_dir / f"{prefix}_tabular_components_usage_{timestamp}.json"
        table_data = {
            'metadata': {
                'generated_at': datetime.utcnow().isoformat(),
                'database_type': 'Teradata',
                'total_tabular_components': len(self.table_usage_stats)
            },
            'tabular_components_usage': self._build_table_usage_report()
        }

        with open(table_file, 'w', encoding='utf-8') as f:
            json.dump(table_data, f, indent=2, default=str)
        output_files['table_usage'] = table_file
        print(f"✓ Tabular Components usage report: {table_file.name}")

        # 6. Volatile Table Usage Report (Teradata-specific)
        if self.volatile_table_usage:
            volatile_file = self.output_dir / f"{prefix}_volatile_tables_usage_{timestamp}.json"
            volatile_data = {
                'metadata': {
                    'generated_at': datetime.utcnow().isoformat(),
                    'database_type': 'Teradata',
                    'total_volatile_tables': len(set(
                        vt for vts in self.volatile_table_usage.values() for vt in vts
                    ))
                },
                'volatile_tables_usage': self._build_volatile_table_report()
            }

            with open(volatile_file, 'w', encoding='utf-8') as f:
                json.dump(volatile_data, f, indent=2, default=str)
            output_files['volatile_tables'] = volatile_file
            print(f"✓ Volatile tables usage report: {volatile_file.name}")

        # 7. Error Report (if any failures)
        failed_results = [
            r for r in self.analysis_results
            if not r.get('analysis_success', False)
        ]

        if failed_results:
            error_file = self.output_dir / f"{prefix}_errors_{timestamp}.json"
            error_data = {
                'metadata': {
                    'generated_at': datetime.utcnow().isoformat(),
                    'database_type': 'Teradata',
                    'total_failures': len(failed_results)
                },
                'failed_analyses': [
                    {
                        'name': r.get('name'),
                        'type': r.get('type'),
                        'error': r.get('lineage_analysis', {}).get('error'),
                        'llm_provider': r.get('llm_provider'),
                        'sql_preview': r.get('modified_sql', '')[:300]
                    }
                    for r in failed_results
                ]
            }

            with open(error_file, 'w', encoding='utf-8') as f:
                json.dump(error_data, f, indent=2, default=str)
            output_files['errors'] = error_file
            print(f"✓ Error report: {error_file.name} ({len(failed_results)} failures)")

        print(f"{'='*80}")
        print(f"✓ All outputs saved to: {self.output_dir.absolute()}")
        print(f"{'='*80}\n")

        return output_files

    def generate_summary_report(self) -> str:
        """Generate a human-readable summary report for Teradata."""

        summary = self._build_summary_statistics()

        report = f"""
{'='*80}
TERADATA LINEAGE ANALYSIS SUMMARY REPORT (LLM-Based)
{'='*80}

Generated: {summary['generated_at']}
Database Type: {summary.get('database_type', 'Teradata')}
Analysis Method: {summary.get('analysis_method', 'LLM-based')}

OVERALL STATISTICS:
------------------
Total Statements Analyzed: {summary['total_statements_analyzed']}
  - Procedures: {summary.get('procedures_count', 0)}
  - Functions: {summary.get('functions_count', 0)}
  - Macros: {summary.get('macros_count', 0)}

Successful Analyses: {summary['successful_analyses']}
Failed Analyses: {summary['failed_analyses']}
Success Rate: {summary['success_rate']}

LLM PROVIDERS:
-------------
"""

        for provider, count in summary.get('llm_providers', {}).items():
            report += f"  {provider:20s}: {count:4d}\n"

        report += f"""
STATEMENTS BY TYPE:
------------------
"""

        for stmt_type, count in sorted(summary['statements_by_type'].items()):
            report += f"  {stmt_type:20s}: {count:4d}\n"

        report += f"""
DATABASE OBJECTS:
----------------
Total Unique Tabular Components: {summary['total_unique_tables']}
Total Dependencies: {summary['total_dependencies']}
Total Volatile Tables Used: {summary.get('total_volatile_tables_used', 0)}

MOST COMPLEX EXECUTABLE COMPONENTS (TOP 10):
------------------------------------------
"""

        for i, proc in enumerate(summary['most_complex_procedures'], 1):
            report += f"  {i:2d}. {proc['name']} ({proc['type']})\n"
            report += f"      Tables: {proc['num_tables']}, "
            report += f"Joins: {proc['num_joins']}, "
            report += f"Calculations: {proc['num_calculations']}\n"
            if proc['has_aggregation']:
                report += f"      Has Aggregations: Yes\n"
            if proc['has_window_functions']:
                report += f"      Has Window Functions: Yes\n"
            if proc.get('has_subqueries'):
                report += f"      Has Subqueries: Yes\n"
            if proc.get('has_cte'):
                report += f"      Has CTEs: Yes\n"
            if proc.get('uses_volatile_tables'):
                report += f"      Uses Volatile Tables: Yes\n"

        report += f"\n{'='*80}\n"

        return report

    def print_summary_report(self):
        """Print summary report to console."""
        print(self.generate_summary_report())

    def save_summary_report(self, prefix: str = "lineage") -> Path:
        """Save summary report as text file."""
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        report_file = self.output_dir / f"{prefix}_summary_report_{timestamp}.txt"

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(self.generate_summary_report())

        print(f"✓ Summary report saved: {report_file.name}")
        return report_file


def main():
    """Main execution function for testing."""

    print("Enhanced Teradata Executable Components JSON Builder (LLM-Optimized)")
    print("=" * 80)
    print("\nFeatures:")
    print("  ✓ Processes LLM-generated Teradata lineage data")
    print("  ✓ Comprehensive JSON outputs")
    print("  ✓ Executable Components catalogs (procedures, functions, macros)")
    print("  ✓ Column-level lineage tracking")
    print("  ✓ Dependency graphs for visualization")
    print("  ✓ Tabular Components usage reports")
    print("  ✓ Volatile table tracking (Teradata-specific)")
    print("\nUsage:")
    print("  builder = EnhancedProcedureJSONBuilder(output_dir='lineage_output')")
    print("  builder.add_analysis_results(analyzed_results)")
    print("  output_files = builder.generate_all_outputs()")
    print("  builder.print_summary_report()")


if __name__ == "__main__":
    main()
