"""
Enhanced Procedure and Function Lineage JSON Builder
Builds comprehensive reports with column-level tracking for procedures
"""

from typing import Dict, List, Any, Set, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
import json


@dataclass
class ProcedureNode:
    """Graph node for a procedure/function with column tracking"""
    name: str
    object_type: str
    file_path: str
    parameters: List[Dict] = field(default_factory=list)
    return_type: str = None
    is_table_valued: bool = False
    output_columns: List[Dict] = field(default_factory=list)
    reads_tables: Set[str] = field(default_factory=set)
    writes_tables: Set[str] = field(default_factory=set)
    creates_temp_tables: Set[str] = field(default_factory=set)
    calls_procedures: Set[str] = field(default_factory=set)
    called_by: Set[str] = field(default_factory=set)
    column_references: List[Dict] = field(default_factory=list)
    internal_statement_count: int = 0
    complexity_score: float = 0.0


class PostgreSQLProcedureJSONBuilder:
    """Build comprehensive lineage JSON report for procedures and functions"""
    
    def __init__(self, dialect: str, source_directory: str):
        self.dialect = dialect
        self.source_directory = source_directory
        
        # Procedure/function registry
        self.procedures: Dict[str, ProcedureNode] = {}
        self.functions: Dict[str, ProcedureNode] = {}
        self.triggers: Dict[str, ProcedureNode] = {}
        
        # Call graph
        self.call_graph: Dict[str, Set[str]] = defaultdict(set)
        
        # Table access patterns
        self.table_readers: Dict[str, Set[str]] = defaultdict(set)
        self.table_writers: Dict[str, Set[str]] = defaultdict(set)
        
        # Column access patterns (NEW)
        self.column_readers: Dict[str, Set[str]] = defaultdict(set)  # "table.column" -> set of procs
        self.column_writers: Dict[str, Set[str]] = defaultdict(set)  # "table.column" -> set of procs
        
        # Statistics
        self.stats = {
            'total_procedures': 0,
            'total_functions': 0,
            'total_triggers': 0,
            'table_valued_functions': 0,
            'scalar_functions': 0,
            'output_parameters': 0,
            'procedure_calls': 0,
            'temp_table_usage': 0,
            'circular_call_chains': [],
            'orphan_procedures': [],
            'complex_procedures': [],
            'total_column_references': 0,
            'tables_accessed': 0,
            'columns_accessed': 0
        }
    
    def build_lineage_report(self, procedure_results: List, function_results: List, trigger_results: List = None) -> Dict:
        """Build comprehensive procedure/function lineage report"""
        print(f"   Processing procedures and functions...")
        
        # Step 1: Register all procedures
        for proc_lineage in procedure_results:
            if not proc_lineage.parse_error:
                self._register_procedure(proc_lineage)
        
        # Step 2: Register all functions
        for func_lineage in function_results:
            if not func_lineage.parse_error:
                self._register_function(func_lineage)
        
        # Step 3: Register triggers if provided
        if trigger_results:
            for trigger_lineage in trigger_results:
                if not trigger_lineage.parse_error:
                    self._register_trigger(trigger_lineage)
        
        # Step 4: Build call graph
        self._build_call_graph()
        
        # Step 5: Analyze table and column access patterns
        self._analyze_access_patterns()
        
        # Step 6: Calculate complexity scores
        self._calculate_complexity_scores()
        
        # Step 7: Detect circular calls
        self._detect_circular_calls()
        
        # Step 8: Find orphan procedures
        self._find_orphan_procedures()
        
        # Step 9: Calculate execution order
        execution_order = self._calculate_execution_order()
        
        # Step 10: Build final JSON
        return self._build_json_report(execution_order)
    
    def _register_procedure(self, proc_lineage):
        """Register a stored procedure with column tracking"""
        # Process column references
        column_refs = []
        for col_ref in proc_lineage.column_references:
            column_refs.append({
                'table': col_ref.table,
                'column': col_ref.column,
                'operation': col_ref.operation,
                'statement_type': col_ref.statement_type
            })
        
        node = ProcedureNode(
            name=proc_lineage.object_name,
            object_type='PROCEDURE',
            file_path=proc_lineage.file_path,
            parameters=[{
                'name': p.name,
                'data_type': p.data_type,
                'is_output': p.is_output,
                'default_value': p.default_value
            } for p in proc_lineage.parameters],
            reads_tables=set(proc_lineage.reads_tables),
            writes_tables=set(proc_lineage.writes_tables),
            creates_temp_tables=set(proc_lineage.creates_temp_tables),
            calls_procedures=set(proc_lineage.calls_procedures),
            column_references=column_refs,
            internal_statement_count=len(proc_lineage.internal_statements)
        )
        
        self.procedures[proc_lineage.object_name] = node
        self.stats['total_procedures'] += 1
        self.stats['total_column_references'] += len(column_refs)
        
        if any(p.is_output for p in proc_lineage.parameters):
            self.stats['output_parameters'] += 1
        
        if proc_lineage.creates_temp_tables:
            self.stats['temp_table_usage'] += 1
    
    def _register_function(self, func_lineage):
        """Register a function with column tracking"""
        # Process column references
        column_refs = []
        for col_ref in func_lineage.column_references:
            column_refs.append({
                'table': col_ref.table,
                'column': col_ref.column,
                'operation': col_ref.operation,
                'statement_type': col_ref.statement_type
            })
        
        node = ProcedureNode(
            name=func_lineage.object_name,
            object_type='FUNCTION',
            file_path=func_lineage.file_path,
            parameters=[{
                'name': p.name,
                'data_type': p.data_type,
                'is_output': p.is_output,
                'default_value': p.default_value
            } for p in func_lineage.parameters],
            return_type=func_lineage.return_type,
            is_table_valued=func_lineage.is_table_valued,
            output_columns=func_lineage.output_columns,
            reads_tables=set(func_lineage.reads_tables),
            writes_tables=set(func_lineage.writes_tables),
            creates_temp_tables=set(func_lineage.creates_temp_tables),
            calls_procedures=set(func_lineage.calls_procedures),
            column_references=column_refs,
            internal_statement_count=len(func_lineage.internal_statements)
        )
        
        self.functions[func_lineage.object_name] = node
        self.stats['total_functions'] += 1
        self.stats['total_column_references'] += len(column_refs)
        
        if func_lineage.is_table_valued:
            self.stats['table_valued_functions'] += 1
        else:
            self.stats['scalar_functions'] += 1
        
        if func_lineage.creates_temp_tables:
            self.stats['temp_table_usage'] += 1
    
    def _register_trigger(self, trigger_lineage):
        """Register a trigger with column tracking"""
        # Process column references
        column_refs = []
        for col_ref in trigger_lineage.column_references:
            column_refs.append({
                'table': col_ref.table,
                'column': col_ref.column,
                'operation': col_ref.operation,
                'statement_type': col_ref.statement_type
            })
        
        node = ProcedureNode(
            name=trigger_lineage.object_name,
            object_type='TRIGGER',
            file_path=trigger_lineage.file_path,
            reads_tables=set(trigger_lineage.reads_tables),
            writes_tables=set(trigger_lineage.writes_tables),
            creates_temp_tables=set(trigger_lineage.creates_temp_tables),
            column_references=column_refs,
            internal_statement_count=len(trigger_lineage.internal_statements)
        )
        
        self.triggers[trigger_lineage.object_name] = node
        self.stats['total_triggers'] += 1
        self.stats['total_column_references'] += len(column_refs)
    
    def _build_call_graph(self):
        """Build procedure call graph"""
        all_objects = {**self.procedures, **self.functions, **self.triggers}
        
        for obj_name, obj_node in all_objects.items():
            for called_proc in obj_node.calls_procedures:
                self.call_graph[obj_name].add(called_proc)
                self.stats['procedure_calls'] += 1
                
                if called_proc in all_objects:
                    all_objects[called_proc].called_by.add(obj_name)
    
    def _analyze_access_patterns(self):
        """Analyze which procedures/functions access which tables and columns"""
        all_objects = {**self.procedures, **self.functions, **self.triggers}
        
        tables_accessed = set()
        columns_accessed = set()
        
        for obj_name, obj_node in all_objects.items():
            # Track table-level access
            for table in obj_node.reads_tables:
                self.table_readers[table].add(obj_name)
                tables_accessed.add(table)
            
            for table in obj_node.writes_tables:
                self.table_writers[table].add(obj_name)
                tables_accessed.add(table)
            
            # Track column-level access (NEW)
            for col_ref in obj_node.column_references:
                col_key = f"{col_ref['table']}.{col_ref['column']}"
                columns_accessed.add(col_key)
                
                if col_ref['operation'] in ['READ', 'UPDATE']:
                    self.column_readers[col_key].add(obj_name)
                
                if col_ref['operation'] in ['WRITE', 'UPDATE']:
                    self.column_writers[col_key].add(obj_name)
        
        self.stats['tables_accessed'] = len(tables_accessed)
        self.stats['columns_accessed'] = len(columns_accessed)
    
    def _calculate_complexity_scores(self):
        """Calculate complexity score for each procedure/function"""
        all_objects = {**self.procedures, **self.functions, **self.triggers}
        
        for obj_node in all_objects.values():
            score = 0.0
            
            # Base score from statement count
            score += min(obj_node.internal_statement_count * 0.5, 10.0)
            
            # Parameters complexity
            score += len(obj_node.parameters) * 0.3
            
            # Table operations
            score += len(obj_node.reads_tables) * 0.2
            score += len(obj_node.writes_tables) * 0.5
            
            # Column references (more detailed = more complex)
            score += len(obj_node.column_references) * 0.1
            
            # Temp tables
            score += len(obj_node.creates_temp_tables) * 0.4
            
            # Procedure calls
            score += len(obj_node.calls_procedures) * 0.6
            
            # Output parameters
            output_params = sum(1 for p in obj_node.parameters if p.get('is_output'))
            score += output_params * 0.4
            
            obj_node.complexity_score = round(score, 2)
            
            # Flag complex procedures
            if score > 15.0:
                self.stats['complex_procedures'].append({
                    'name': obj_node.name,
                    'score': obj_node.complexity_score
                })
    
    def _detect_circular_calls(self):
        """Detect circular procedure call chains"""
        visited = set()
        rec_stack = set()
        circular_chains = []
        
        def dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self.call_graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor, path.copy()):
                        return True
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    circular_chains.append(cycle)
                    return True
            
            rec_stack.remove(node)
            return False
        
        all_nodes = set(self.call_graph.keys())
        for node in all_nodes:
            if node not in visited:
                dfs(node, [])
        
        self.stats['circular_call_chains'] = circular_chains
    
    def _find_orphan_procedures(self):
        """Find procedures that are never called"""
        all_objects = {**self.procedures, **self.functions}
        
        for obj_name, obj_node in all_objects.items():
            if not obj_node.called_by and obj_node.object_type == 'PROCEDURE':
                self.stats['orphan_procedures'].append(obj_name)
    
    def _calculate_execution_order(self) -> Dict:
        """Calculate procedure execution order"""
        in_degree = defaultdict(int)
        adj_list = defaultdict(list)
        
        all_objects = list(self.procedures.keys()) + list(self.functions.keys())
        
        for obj in all_objects:
            if obj not in in_degree:
                in_degree[obj] = 0
        
        for caller, callees in self.call_graph.items():
            for callee in callees:
                if callee in all_objects:
                    adj_list[caller].append(callee)
                    in_degree[callee] += 1
        
        # Topological sort
        queue = deque([obj for obj, deg in in_degree.items() if deg == 0])
        order = []
        levels = defaultdict(list)
        
        current_level = 0
        while queue:
            level_size = len(queue)
            
            for _ in range(level_size):
                obj = queue.popleft()
                order.append(obj)
                levels[f"level_{current_level}"].append(obj)
                
                for neighbor in adj_list[obj]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            
            current_level += 1
        
        return {
            "execution_order": order,
            "levels": dict(levels),
            "has_circular_calls": len(self.stats['circular_call_chains']) > 0
        }
    
    def _build_json_report(self, execution_order: Dict) -> Dict:
        """Build final JSON report with column-level details"""
        # Build procedures section
        procedures_json = {}
        for name, node in self.procedures.items():
            # Group column references by operation
            columns_read = []
            columns_written = []
            columns_updated = []
            
            for col_ref in node.column_references:
                col_key = f"{col_ref['table']}.{col_ref['column']}"
                if col_ref['operation'] == 'READ':
                    columns_read.append(col_key)
                elif col_ref['operation'] == 'WRITE':
                    columns_written.append(col_key)
                elif col_ref['operation'] == 'UPDATE':
                    columns_updated.append(col_key)
            
            procedures_json[name] = {
                "file_path": node.file_path,
                "parameters": node.parameters,
                "reads_tables": list(node.reads_tables),
                "writes_tables": list(node.writes_tables),
                "creates_temp_tables": list(node.creates_temp_tables),
                "calls_procedures": list(node.calls_procedures),
                "called_by": list(node.called_by),
                "columns_read": list(set(columns_read)),
                "columns_written": list(set(columns_written)),
                "columns_updated": list(set(columns_updated)),
                "column_reference_count": len(node.column_references),
                "statement_count": node.internal_statement_count,
                "complexity_score": node.complexity_score
            }
        
        # Build functions section
        functions_json = {}
        for name, node in self.functions.items():
            columns_read = []
            columns_written = []
            
            for col_ref in node.column_references:
                col_key = f"{col_ref['table']}.{col_ref['column']}"
                if col_ref['operation'] == 'READ':
                    columns_read.append(col_key)
                elif col_ref['operation'] in ['WRITE', 'UPDATE']:
                    columns_written.append(col_key)
            
            functions_json[name] = {
                "file_path": node.file_path,
                "parameters": node.parameters,
                "return_type": node.return_type,
                "is_table_valued": node.is_table_valued,
                "output_columns": node.output_columns,
                "reads_tables": list(node.reads_tables),
                "writes_tables": list(node.writes_tables),
                "creates_temp_tables": list(node.creates_temp_tables),
                "called_by": list(node.called_by),
                "columns_read": list(set(columns_read)),
                "columns_written": list(set(columns_written)),
                "column_reference_count": len(node.column_references),
                "statement_count": node.internal_statement_count,
                "complexity_score": node.complexity_score
            }
        
        # Build triggers section
        triggers_json = {}
        for name, node in self.triggers.items():
            columns_read = []
            columns_written = []
            
            for col_ref in node.column_references:
                col_key = f"{col_ref['table']}.{col_ref['column']}"
                if col_ref['operation'] == 'READ':
                    columns_read.append(col_key)
                elif col_ref['operation'] in ['WRITE', 'UPDATE']:
                    columns_written.append(col_key)
            
            triggers_json[name] = {
                "file_path": node.file_path,
                "reads_tables": list(node.reads_tables),
                "writes_tables": list(node.writes_tables),
                "columns_read": list(set(columns_read)),
                "columns_written": list(set(columns_written)),
                "column_reference_count": len(node.column_references),
                "statement_count": node.internal_statement_count,
                "complexity_score": node.complexity_score
            }
        
        # Build table access matrix
        table_access_json = {}
        all_tables = set(self.table_readers.keys()) | set(self.table_writers.keys())
        for table in all_tables:
            table_access_json[table] = {
                "read_by": list(self.table_readers.get(table, set())),
                "written_by": list(self.table_writers.get(table, set()))
            }
        
        # Build column access matrix (NEW)
        column_access_json = {}
        for col_key in sorted(self.column_readers.keys() | self.column_writers.keys()):
            column_access_json[col_key] = {
                "read_by": list(self.column_readers.get(col_key, set())),
                "written_by": list(self.column_writers.get(col_key, set()))
            }
        
        # Build call graph
        call_graph_json = {}
        for caller, callees in self.call_graph.items():
            call_graph_json[caller] = list(callees)
        
        # Final report
        report = {
            "metadata": {
                "dialect": self.dialect,
                "source_directory": self.source_directory,
                "report_type": "procedure_function_lineage",
                "version": "2.1"
            },
            "summary": {
                "total_procedures": self.stats['total_procedures'],
                "total_functions": self.stats['total_functions'],
                "total_triggers": self.stats['total_triggers'],
                "table_valued_functions": self.stats['table_valued_functions'],
                "scalar_functions": self.stats['scalar_functions'],
                "output_parameters": self.stats['output_parameters'],
                "procedure_calls": self.stats['procedure_calls'],
                "temp_table_usage": self.stats['temp_table_usage'],
                "complex_procedures_count": len(self.stats['complex_procedures']),
                "orphan_procedures_count": len(self.stats['orphan_procedures']),
                "total_column_references": self.stats['total_column_references'],
                "tables_accessed": self.stats['tables_accessed'],
                "columns_accessed": self.stats['columns_accessed']
            },
            "execution_order": execution_order,
            "procedures": procedures_json,
            "functions": functions_json,
            "triggers": triggers_json,
            "table_access_matrix": table_access_json,
            "column_access_matrix": column_access_json,
            "call_graph": call_graph_json,
            "warnings": {
                "circular_call_chains": self.stats['circular_call_chains'],
                "orphan_procedures": self.stats['orphan_procedures'],
                "complex_procedures": self.stats['complex_procedures'][:10]
            }
        }
        
        return report
    
    def save_report(self, report: Dict, output_path: str):
        """Save report to JSON file"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n   Procedure/Function report saved to: {output_path}")


if __name__ == "__main__":
    builder = PostgreSQLProcedureJSONBuilder("postgres", "./sql_files")
    report = builder.build_lineage_report([], [], [])
    print(json.dumps(report, indent=2))