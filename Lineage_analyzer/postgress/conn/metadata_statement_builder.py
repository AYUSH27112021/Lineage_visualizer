"""
Metadata Statement Builder
Builds lineage JSON reports from analyzed views and query history.

This module produces the same output format as EnhancedLineageJSONBuilder
but works with metadata-based analysis results instead of file-based results.
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


@dataclass
class TableInfo:
    """Aggregated table information"""
    table_name: str
    columns: Dict[str, ColumnInfo] = field(default_factory=dict)
    definition_sources: Set[str] = field(default_factory=set)
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
    defining_source: str
    columns: List[str] = field(default_factory=list)
    source_tables: List[str] = field(default_factory=list)
    query_snippet: str = ""


class MetadataStatementBuilder:
    """
    Build comprehensive lineage JSON report from metadata-based analysis.
    
    Produces the same output format as EnhancedLineageJSONBuilder for
    frontend compatibility.
    """
    
    def __init__(
        self,
        dialect: str = "postgres",
        database_name: str = "",
        metadata: Optional[Dict] = None
    ):
        """
        Initialize the builder.
        
        Args:
            dialect: SQL dialect
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
            'circular_dependencies': [],
            'set_operations': 0,
            'subquery_count': 0
        }
    
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
        
        # Step 4: Deduplicate and merge conflicts
        self._deduplicate_lineages()
        
        # Step 5: Remove placeholder columns
        self._remove_placeholder_columns()
        
        # Step 6: Calculate confidence scores
        self._calculate_confidence_scores()
        
        # Step 7: Calculate execution order
        execution_order = self._calculate_execution_order()
        
        # Step 8: Build final JSON structure
        return self._build_json_report(execution_order)
    
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
        
        if result.get('statement_subtype') in ['UNION', 'INTERSECT', 'EXCEPT']:
            self.stats['set_operations'] += 1
        
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
        
        # Process temp tables
        temp_tables = result.get('temp_tables', [])
        for temp_table in temp_tables:
            if temp_table not in self.temp_tables:
                self.temp_tables[temp_table] = TableInfo(
                    table_name=temp_table,
                    is_temp=True
                )
                self.temp_tables[temp_table].definition_sources.add(name)
                self.stats['temp_table_count'] += 1
        
        # Process target table (for views, this is the view name)
        target_table = result.get('target_table') or result.get('name')
        if target_table:
            self._register_table(
                target_table,
                source_type,
                name,
                result.get('statement_subtype'),
                is_view=(source_type == "VIEW")
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
        is_view: bool = False
    ):
        """Register a table in the lineage graph."""
        if table_name not in self.tables:
            self.tables[table_name] = TableInfo(
                table_name=table_name,
                is_temp=self._is_temp_table(table_name),
                is_cte=table_name.startswith('CTE:'),
                is_view=is_view
            )
        
        self.tables[table_name].definition_sources.add(source_name)
        self.tables[table_name].definition_types.add(stmt_type)
        
        if stmt_subtype:
            self.tables[table_name].statement_subtypes.add(stmt_subtype)
        
        if is_view:
            self.tables[table_name].is_view = True
    
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
        # Build tables section
        tables_json = {}
        for table_name, table_info in self.tables.items():
            tables_json[table_name] = {
                "definition_sources": list(table_info.definition_sources),
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
        
        # Build temp tables section
        temp_tables_json = {}
        for temp_name, temp_info in self.temp_tables.items():
            temp_tables_json[temp_name] = {
                "columns": list(temp_info.columns.keys()),
                "definition_sources": list(temp_info.definition_sources)
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
                "ctes": self.stats['cte_count'],
                "dynamic_sql_count": self.stats['dynamic_sql_count'],
                "dynamic_sql_detected": self.stats['dynamic_sql_count'] > 0,
                "set_operations": self.stats['set_operations'],
                "parse_errors": self.stats['parse_errors'],
                "successful_parses": self.stats['successful_parses'],
                "parse_success_rate": parse_success_rate,
                "duplicate_columns_merged": self.stats['duplicate_columns_merged']
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
    
    def _is_temp_table(self, table_name: str) -> bool:
        """Check if table is temporary."""
        temp_prefixes = ['#', '##', 'temp_', 'tmp_', 'staging_', 'stg_', '@']
        return any(table_name.lower().startswith(prefix) for prefix in temp_prefixes)
    
    def save_report(self, report: Dict, output_path: str):
        """Save report to JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n   Report saved to: {output_path}")


if __name__ == "__main__":
    builder = MetadataStatementBuilder("tsql", "TestDB")
    
    mock_view_results = [
        {
            'name': 'vw_customer_orders',
            'type': 'VIEW',
            'target_table': 'vw_customer_orders',
            'source_tables': ['dbo.customers', 'dbo.orders'],
            'column_lineage': [
                {
                    'target_column': 'customer_id',
                    'target_table': 'vw_customer_orders',
                    'source_columns': [{'table': 'dbo.customers', 'column': 'customer_id'}],
                    'transform_type': 'direct',
                    'is_aggregate': False,
                    'is_calculated': False
                }
            ],
            'cte_definitions': {},
            'temp_tables': [],
            'is_dynamic': False,
            'parse_error': None
        }
    ]
    
    report = builder.build_lineage_report(mock_view_results, [])
    print(json.dumps(report, indent=2))
