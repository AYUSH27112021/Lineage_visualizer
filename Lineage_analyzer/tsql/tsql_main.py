"""
Main Orchestrator for T-SQL Lineage Analysis with LLM-based Procedure Analysis
Coordinates cleaning, analysis, and JSON building for complete database lineage
"""

import sys
import json
from pathlib import Path
from datetime import datetime

from typing import Dict, List, Optional, Tuple

# Import existing components
from .tsql_cleaner import EnhancedSQLCleaner
from .tsql_analyzer import EnhancedSQLAnalyzer
from .json_builder import EnhancedLineageJSONBuilder

# Import new LLM-based components
from .enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer
from .enhanced_json_builder import EnhancedProcedureJSONBuilder


class LineageOrchestrator:
    """Main orchestrator for complete lineage analysis with LLM-powered procedure analysis"""
    
    def __init__(
        self,
        sql_directory: str,
        output_directory: str,
        dialect: str = "tsql",
        debug: bool = False,
        # LLM Configuration
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:14b",
        openai_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
        batch_size: int = 10,
        timeout: int = 300,  # Increased default timeout to 5 minutes for complex procedures
        # Metadata configuration
        metadata: Optional[Dict] = None
    ):
        self.sql_directory = Path(sql_directory)
        self.output_directory = Path(output_directory)
        self.dialect = dialect
        self.debug = debug
        
        # Create output directory
        self.output_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize existing components (for statement analysis)
        self.cleaner = EnhancedSQLCleaner(sql_directory, debug=debug)
        self.statement_analyzer = EnhancedSQLAnalyzer(dialect=dialect, debug=debug)
        self.statement_json_builder = EnhancedLineageJSONBuilder(dialect, sql_directory)
        
        # Initialize NEW LLM-based procedure analyzer
        self.llm_analyzer = EnhancedLLMLineageAnalyzer(
            metadata=metadata or {},
            ollama_url=ollama_url,
            ollama_model=ollama_model,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
            batch_size=batch_size,
            timeout=timeout
        )
        
        # Initialize NEW JSON builder for procedures
        self.procedure_json_builder = EnhancedProcedureJSONBuilder(
            output_dir=self.output_directory
        )
        
        # Storage for results
        self.cleaned_files = {}
        self.statement_results = []
        self.procedure_results = []
        self.function_results = []
        self.view_results = []
        self.trigger_results = []
        
        # Storage for LLM analysis
        self.llm_analyzed_procedures = []
        self.llm_analyzed_functions = []
        self.metadata = metadata or {}
    
    def run_full_analysis(self, max_files: int = None) -> Dict:
        """Run complete lineage analysis pipeline with LLM-based procedure analysis"""
        print("\n" + "="*80)
        print("T-SQL LINEAGE ANALYSIS PIPELINE (with LLM-Enhanced Procedure Analysis)")
        print("="*80)
        
        start_time = datetime.now()
        
        # Step 1: Clean SQL files
        print("\n[1/6] Cleaning SQL files...")
        self.cleaned_files = self.cleaner.clean_all_files(max_files=max_files)
        print(f"   ✓ Cleaned {len(self.cleaned_files)} files")
        
        # Step 2: Analyze regular statements (tables, views, simple queries)
        print("\n[2/6] Analyzing SQL statements (tables, views, queries)...")
        self._analyze_statements()
        print(f"   ✓ Analyzed {len(self.statement_results)} files with statements")
        if self.view_results:
            print(f"   ✓ Found {len(self.view_results)} views")
        
        # Step 3: Extract procedures, functions, and triggers for LLM analysis
        print("\n[3/6] Extracting procedures, functions, and triggers...")
        proc_func_statements = self._extract_procedures_and_functions()
        print(f"   ✓ Found {len([s for s in proc_func_statements if s['type'] == 'PROCEDURE'])} procedures")
        print(f"   ✓ Found {len([s for s in proc_func_statements if s['type'] in ['FUNCTION', 'SCALAR_FUNCTION', 'TABLE_FUNCTION']])} functions")
        trigger_count = len([s for s in proc_func_statements if s['type'] == 'TRIGGER'])
        if trigger_count > 0:
            print(f"   ✓ Found {trigger_count} triggers")
        
        # Step 4: Perform LLM-based analysis on procedures/functions/triggers
        print("\n[4/6] Analyzing procedures/functions/triggers with LLM...")
        print(f"   Using: {'OpenAI' if self.llm_analyzer.use_openai else 'Ollama'}")
        print(f"   Model: {self.llm_analyzer.openai_model if self.llm_analyzer.use_openai else self.llm_analyzer.ollama_model}")
        
        if proc_func_statements:
            llm_results = self.llm_analyzer.analyze_statements(proc_func_statements)
            
            # Separate results by type
            for result in llm_results:
                stmt_type = (result.get('type') or 'UNKNOWN').upper()
                if stmt_type == 'PROCEDURE':
                    self.llm_analyzed_procedures.append(result)
                elif stmt_type in ['FUNCTION', 'SCALAR_FUNCTION', 'TABLE_FUNCTION']:
                    self.llm_analyzed_functions.append(result)
                elif stmt_type == 'TRIGGER':
                    self.trigger_results.append(result)
                else:
                    print(f"   ⚠ Warning: Unknown statement type '{stmt_type}' for {result.get('name', 'unknown')}")
            
            # Print LLM analysis statistics
            self.llm_analyzer.print_statistics()
        else:
            print("   ⚠ No procedures, functions, or triggers found to analyze")
        
        # Step 5: Build statement lineage JSON (tables, views, queries)
        print("\n[5/6] Building statement lineage report...")
        statement_report = self.statement_json_builder.build_lineage_report(self.statement_results)
        statement_output = self.output_directory / f"statement_lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.statement_json_builder.save_report(statement_report, str(statement_output))
        print(f"   ✓ Saved to: {statement_output.name}")
        
        # Step 6: Build LLM-enhanced procedure/function lineage JSON
        print("\n[6/6] Building LLM-enhanced procedure/function lineage report...")
        
        # Add LLM results to procedure JSON builder
        all_llm_results = self.llm_analyzed_procedures + self.llm_analyzed_functions + self.trigger_results
        self.procedure_json_builder.add_analysis_results(all_llm_results)
        
        # Generate all output files
        procedure_prefix = f"procedure_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_files = self.procedure_json_builder.generate_all_outputs(prefix=procedure_prefix)
        
        # Produce backward-compatible procedure report for UI/clients
        legacy_procedure_report = self._build_legacy_procedure_report(all_llm_results)
        legacy_procedure_path = self.output_directory / f"procedure_lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(legacy_procedure_path, 'w', encoding='utf-8') as f:
            json.dump(legacy_procedure_report, f, indent=2, ensure_ascii=False)
        print(f"   ✓ Legacy procedure lineage saved to: {legacy_procedure_path.name}")
        
        # Print summary
        self.procedure_json_builder.print_summary_report()
        
        # Step 7: Build combined summary
        print("\n[7/7] Building combined summary...")
        combined_summary = self._build_combined_summary(statement_report, output_files)
        summary_output = self.output_directory / f"lineage_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_output, 'w', encoding='utf-8') as f:
            json.dump(combined_summary, f, indent=2, ensure_ascii=False)
        print(f"   ✓ Summary saved to: {summary_output.name}")
        
        # Calculate elapsed time
        elapsed = datetime.now() - start_time
        
        # Print final summary
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        print(f"Total time: {elapsed.total_seconds():.2f} seconds")
        print(f"\nOutput files:")
        print(f"  1. Statement lineage:     {statement_output.name}")
        print(f"  2. Executable Components catalog:     {output_files.get('catalog', 'N/A')}")
        print(f"  3. Column lineage:        {output_files.get('column_lineage', 'N/A')}")
        print(f"  4. Dependency graph:      {output_files.get('dependency_graph', 'N/A')}")
        print(f"  5. Tabular Components usage:           {output_files.get('table_usage', 'N/A')}")
        print(f"  6. Complete analysis:     {output_files.get('complete', 'N/A')}")
        print(f"  7. Combined summary:      {summary_output.name}")
        print("="*80 + "\n")
        
        return {
            'statement_report': statement_report,
            'procedure_report': legacy_procedure_report,
            'procedure_analysis': all_llm_results,
            'combined_summary': combined_summary,
            'output_files': {
                'statements': str(statement_output),
                'summary': str(summary_output),
                'procedures': str(legacy_procedure_path),
                **{k: str(v) for k, v in output_files.items()}
            },
            'elapsed_time': elapsed.total_seconds(),
            'statistics': {
                'total_files': len(self.cleaned_files),
                'total_statements': len(self.statement_results),
                'total_procedures': len(self.llm_analyzed_procedures),
                'total_functions': len(self.llm_analyzed_functions),
                'total_triggers': len(self.trigger_results),
                'llm_success_rate': self._calculate_llm_success_rate()
            }
        }
    
    def _analyze_statements(self):
        """Analyze regular SQL statements (not procedures/functions)"""
        for file_path, content in self.cleaned_files.items():
            statements = content.get('statements', [])
            
            if statements:
                # Analyze all statements in file
                result = self.statement_analyzer.analyze_file(file_path, statements)
                self.statement_results.append(result)
            
            # Separately track views
            if content.get('views'):
                for view in content['views']:
                    view_result = self.statement_analyzer.analyze_file(
                        file_path,
                        [view['content']]
                    )
                    self.view_results.append({
                        'name': view['name'],
                        'file_path': file_path,
                        'result': view_result
                    })
    
    def _extract_procedures_and_functions(self) -> List[Dict]:
        """
        Extract procedures and functions from cleaned files and prepare them for LLM analysis.
        Returns a list of statements in the format expected by EnhancedLLMLineageAnalyzer.
        """
        proc_func_statements = []
        
        for file_path, content in self.cleaned_files.items():
            # Extract procedures
            if content.get('procedures'):
                for proc in content['procedures']:
                    proc_name = proc.get('name', 'unnamed_procedure')
                    proc_content = proc.get('content', '')
                    
                    statement = {
                        'type': 'PROCEDURE',
                        'name': proc_name,
                        'original_sql': proc_content,
                        'modified_sql': proc_content,  # Will be normalized later if needed
                        'file_path': str(file_path),
                        'schema_name': self._extract_schema_from_name(proc_name),
                        'object_name': self._extract_object_name(proc_name)
                    }
                    proc_func_statements.append(statement)
            
            # Extract functions
            if content.get('functions'):
                for func in content['functions']:
                    func_name = func.get('name', 'unnamed_function')
                    func_content = func.get('content', '')
                    func_type = func.get('type', 'FUNCTION')
                    
                    statement = {
                        'type': func_type,  # Could be FUNCTION, SCALAR_FUNCTION, TABLE_FUNCTION
                        'name': func_name,
                        'original_sql': func_content,
                        'modified_sql': func_content,
                        'file_path': str(file_path),
                        'schema_name': self._extract_schema_from_name(func_name),
                        'object_name': self._extract_object_name(func_name)
                    }
                    proc_func_statements.append(statement)
            
            # Extract triggers
            if content.get('triggers'):
                for trigger in content['triggers']:
                    trigger_name = trigger.get('name', 'unnamed_trigger')
                    trigger_content = trigger.get('content', '')
                    
                    statement = {
                        'type': 'TRIGGER',
                        'name': trigger_name,
                        'original_sql': trigger_content,
                        'modified_sql': trigger_content,
                        'file_path': str(file_path),
                        'schema_name': self._extract_schema_from_name(trigger_name),
                        'object_name': self._extract_object_name(trigger_name),
                        'table': trigger.get('table', ''),
                        'event': trigger.get('event', '')
                    }
                    proc_func_statements.append(statement)
        
        return proc_func_statements
    
    def _extract_schema_from_name(self, full_name: str) -> str:
        """Extract schema from qualified name (e.g., 'dbo.ProcName' -> 'dbo')"""
        if '.' in full_name:
            return full_name.split('.')[0].strip('[]')
        return 'dbo'
    
    def _extract_object_name(self, full_name: str) -> str:
        """Extract object name from qualified name (e.g., 'dbo.ProcName' -> 'ProcName')"""
        if '.' in full_name:
            return full_name.split('.')[-1].strip('[]')
        return full_name.strip('[]')
    
    def _calculate_llm_success_rate(self) -> str:
        """Calculate success rate of LLM analysis"""
        total = len(self.llm_analyzed_procedures) + len(self.llm_analyzed_functions) + len(self.trigger_results)
        if total == 0:
            return "N/A"
        
        successful = sum(
            1 for result in (self.llm_analyzed_procedures + self.llm_analyzed_functions + self.trigger_results)
            if result.get('analysis_success', False)
        )
        
        return f"{(successful / total * 100):.1f}%"
    
    def _build_combined_summary(self, statement_report: Dict, procedure_output_files: Dict) -> Dict:
        """Build a combined summary report with both statement and LLM-based procedure analysis"""
        s = statement_report.get('summary', {}) or {}
        
        # LLM statistics
        total_procs = len(self.llm_analyzed_procedures)
        total_funcs = len(self.llm_analyzed_functions)
        total_triggers = len(self.trigger_results)
        successful_llm = sum(
            1 for r in (self.llm_analyzed_procedures + self.llm_analyzed_functions + self.trigger_results)
            if r.get('analysis_success', False)
        )
        total_llm = total_procs + total_funcs + total_triggers
        llm_success_rate = f"{(successful_llm / max(total_llm, 1) * 100):.1f}%"
        
        # Statement statistics
        total_statements = s.get('total_statements', 0)
        successful_parses = s.get('successful_parses', 0)
        denom = max(total_statements, 1)
        parse_success_rate = f"{(successful_parses / denom * 100):.1f}%"
        
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_directory": str(self.sql_directory),
                "dialect": self.dialect,
                "analysis_method": "LLM-Enhanced (Ollama/OpenAI)" if total_llm > 0 else "Traditional Parsing"
            },
            "overall_summary": {
                "total_files_analyzed": len(self.cleaned_files),
                "total_statements": total_statements,
                "total_tables": s.get('total_tables', 0),
                "total_columns": s.get('total_columns', 0),
                "total_procedures": total_procs,
                "total_functions": total_funcs,
                "total_triggers": total_triggers,
                "temp_tables": s.get('temp_tables', 0),
                "ctes": s.get('ctes', 0)
            },
            "statement_lineage": {
                "total_dependencies": s.get('total_dependencies', 0),
                "dynamic_sql_count": s.get('dynamic_sql_count', 0),
                "set_operations": s.get('set_operations', 0),
                "parse_success_rate": parse_success_rate
            },
            "procedure_lineage": {
                "analysis_method": "LLM-based" if total_llm > 0 else "None",
                "llm_success_rate": llm_success_rate,
                "total_analyzed": total_llm,
                "successful_analyses": successful_llm,
                "failed_analyses": total_llm - successful_llm,
                "output_files": len(procedure_output_files)
            },
            "llm_analysis_details": {
                "procedures_analyzed": total_procs,
                "functions_analyzed": total_funcs,
                "triggers_analyzed": total_triggers,
                "column_lineage_extracted": successful_llm > 0,
                "transformation_detection": successful_llm > 0,
                "dependency_graph_generated": 'dependency_graph' in procedure_output_files
            },
            "warnings": {
                "circular_dependencies": statement_report.get('warnings', {}).get('circular_dependencies', []),
                "dynamic_sql_detected": s.get('dynamic_sql_detected', False),
                "llm_analysis_failures": total_llm - successful_llm if total_llm > 0 else 0
            },
            "data_flow_summary": {
                "description": "Tables and their relationships from statement analysis",
                "most_referenced_tables": self._get_most_referenced_tables(statement_report),
                "most_complex_procedures": self._get_most_complex_procedures()
            }
        }
    
    def _get_most_referenced_tables(self, statement_report: Dict, top_n: int = 10) -> List[Dict]:
        """Get most referenced tables from statement analysis"""
        table_refs = {}
        
        for table_name, table_info in statement_report.get('tables', {}).items():
            ref_count = len(table_info.get('depends_on', []))
            table_refs[table_name] = ref_count
        
        # Sort by reference count
        sorted_tables = sorted(table_refs.items(), key=lambda x: x[1], reverse=True)
        
        return [
            {"table": table, "reference_count": count}
            for table, count in sorted_tables[:top_n]
        ]
    
    def _get_most_complex_procedures(self, top_n: int = 10) -> List[Dict]:
        """Get most complex procedures from LLM analysis"""
        proc_complexity = []
        
        for proc in self.llm_analyzed_procedures:
            lineage = proc.get('lineage_analysis', {})
            if 'error' not in lineage:
                complexity_metrics = lineage.get('complexity_metrics', {})
                proc_complexity.append({
                    "procedure": proc.get('name'),
                    "num_tables": complexity_metrics.get('num_tables', 0),
                    "num_joins": complexity_metrics.get('num_joins', 0),
                    "num_calculations": complexity_metrics.get('num_calculations', 0),
                    "has_aggregation": complexity_metrics.get('has_aggregation', False),
                    "has_window_functions": complexity_metrics.get('has_window_functions', False),
                    "complexity_score": (
                        complexity_metrics.get('num_tables', 0) +
                        complexity_metrics.get('num_joins', 0) +
                        complexity_metrics.get('num_calculations', 0) +
                        (10 if complexity_metrics.get('has_aggregation') else 0) +
                        (10 if complexity_metrics.get('has_window_functions') else 0)
                    )
                })
        
        # Sort by complexity score
        sorted_procs = sorted(proc_complexity, key=lambda x: x['complexity_score'], reverse=True)
        
        return sorted_procs[:top_n]

    def _build_legacy_procedure_report(self, llm_results: List[Dict]) -> Dict:
        """Convert LLM analysis results into the legacy procedure report structure."""
        report = {
            "summary": {
                "total_procedures": 0,
                "total_functions": 0,
                "total_triggers": 0,
                "scalar_functions": 0,
                "table_valued_functions": 0,
                "procedure_calls": 0,
                "successful_analyses": 0,
                "failed_analyses": 0,
                "total_column_references": 0
            },
            "procedures": {},
            "functions": {},
            "triggers": {}
        }
        
        for result in llm_results:
            entry = self._convert_llm_result_to_legacy_entry(result)
            name = result.get('name')
            if not entry or not name:
                continue
            
            stmt_type = (result.get('type') or '').upper()
            summary = report["summary"]
            
            if 'PROCEDURE' in stmt_type:
                report['procedures'][name] = entry
                summary['total_procedures'] += 1
            elif 'FUNCTION' in stmt_type:
                report['functions'][name] = entry
                summary['total_functions'] += 1
                if stmt_type in {'FUNCTION', 'SCALAR_FUNCTION'}:
                    summary['scalar_functions'] += 1
                if 'TABLE' in stmt_type:
                    summary['table_valued_functions'] += 1
            elif 'TRIGGER' in stmt_type:
                report['triggers'][name] = entry
                summary['total_triggers'] += 1
            
            summary['procedure_calls'] += len(entry.get('calls_procedures', []))
            if entry.get('analysis_success'):
                summary['successful_analyses'] += 1
            else:
                summary['failed_analyses'] += 1
            summary['total_column_references'] += (
                len(entry.get('columns_read', [])) + len(entry.get('columns_written', []))
            )
        
        # Populate called_by relationships for both procedures and functions
        self._populate_called_by_relations(report['procedures'], report['procedures'])
        self._populate_called_by_relations(report['functions'], report['functions'])
        self._populate_called_by_relations(report['functions'], report['procedures'])
        self._populate_called_by_relations(report['procedures'], report['functions'])
        
        return report

    def _convert_llm_result_to_legacy_entry(self, result: Dict) -> Optional[Dict]:
        """Map a single LLM analysis result into the legacy schema expected by the UI."""
        name = result.get('name')
        if not name:
            return None
        
        schema = result.get('schema_name') or self._extract_schema_from_name(name)
        object_name = result.get('object_name') or self._extract_object_name(name)
        lineage = result.get('lineage_analysis') or {}
        statement_info = lineage.get('statement_info') or {}
        dependencies = lineage.get('dependencies') or {}
        metrics = lineage.get('complexity_metrics') or {}
        
        entry = {
            "file_path": result.get('file_path', ''),
            "schema": schema,
            "object_name": object_name,
            "original_sql": result.get('original_sql', ''),
            "modified_sql": result.get('modified_sql') or result.get('original_sql', ''),
            "parameters": statement_info.get('parameters', []),
            "description": statement_info.get('description', ''),
            "analysis_success": result.get('analysis_success', False),
            "reads_tables": [],
            "writes_tables": [],
            "columns_read": [],
            "columns_written": [],
            "columns_updated": [],
            "columns_returned": [],
            "calls_procedures": [],
            "called_by": [],
            "creates_temp_tables": [],
            "complexity_score": self._compute_complexity_score(metrics),
            "complexity_metrics": metrics,
            "filters": lineage.get('filters', {}),
            "table_context_used": result.get('table_context_used', []),
            "lineage_analysis": lineage,
            "llm_prompt": result.get('llm_prompt', ''),
            "llm_raw_response": result.get('llm_raw_response') or self._stringify_lineage(lineage),
            "llm_provider": result.get('llm_provider'),
            "analysis_method": result.get('analysis_method', 'LLM')
        }
        
        calls_raw = dependencies.get('procedures') or []
        entry['calls_procedures'] = sorted({c for c in calls_raw if c})
        
        if 'error' in lineage:
            entry['error'] = lineage.get('error')
            return entry
        
        read_tables = set()
        read_columns = set()
        source_tables = lineage.get('source_tables') or []
        for table in source_tables:
            table_name = table.get('table_list')
            if table_name:
                read_tables.add(table_name)
            for column in (table.get('columns_used') or []):
                ref = self._format_column_reference(table_name, column)
                if ref:
                    read_columns.add(ref)
        entry['reads_tables'] = sorted(read_tables)
        
        target = lineage.get('target') or {}
        target_name = target.get('name')
        operation = (target.get('operation') or '').upper()
        write_tables = set()
        written_columns = set()
        returned_columns = set()
        
        # Get the procedure/function name to avoid treating it as a table
        proc_func_name = result.get('name', '')
        
        # Only add target to writes_tables if it's a write operation (not SELECT)
        # and it's not the procedure/function name itself
        if target_name and target_name != proc_func_name:
            # Check if this is a write operation
            is_write_operation = operation in ['INSERT', 'UPDATE', 'DELETE', 'CREATE', 'MERGE']
            
            if is_write_operation:
                # Only add if target_name exists in metadata as a table, or if it's clearly a table
                # Check if it's in the metadata (would be in table_metadata_index if available)
                # For now, we'll add it but the frontend should filter out procedure/function names
                write_tables.add(target_name)
                for column in target.get('columns_affected') or []:
                    ref = self._format_column_reference(target_name, column)
                    if ref:
                        written_columns.add(ref)
            # For SELECT operations, don't add to writes_tables - it's a return/output
            # The columns_affected will be handled via column_lineage
        
        intermediate_objects = lineage.get('intermediate_objects', [])
        temp_tables = set()
        for obj in intermediate_objects or []:
            tbl_name = obj.get('name')
            if not tbl_name:
                continue
            if obj.get('type', '').upper().startswith('TEMP') or tbl_name.startswith('#'):
                temp_tables.add(tbl_name)
                write_tables.add(tbl_name)
                for column in obj.get('columns') or []:
                    ref = self._format_column_reference(tbl_name, column)
                    if ref:
                        written_columns.add(ref)
        entry['creates_temp_tables'] = sorted(temp_tables)
        
        column_lineage_entries = []
        for mapping in lineage.get('column_lineage') or []:
            sources = []
            for source in mapping.get('source_columns', []):
                if isinstance(source, str):
                    sources.append(source)
                elif isinstance(source, dict):
                    ref = self._format_column_reference(source.get('table_list'), source.get('column'))
                    if ref:
                        sources.append(ref)
            read_columns.update(sources)
            column_lineage_entries.append({
                "target_column": mapping.get('target_column'),
                "sources": sources,
                "transformation": mapping.get('transformation', {})
            })
        entry['column_lineage'] = column_lineage_entries
        
        # Collect returned columns from column_lineage and from SELECT target
        returned_from_lineage = {
            mapping.get('target_column')
            for mapping in column_lineage_entries
            if mapping.get('target_column')
        }
        returned_columns.update(returned_from_lineage)
        entry['columns_returned'] = sorted(returned_columns)
        
        entry['columns_read'] = sorted(read_columns)
        entry['writes_tables'] = sorted(write_tables)
        entry['columns_written'] = sorted(written_columns)
        if operation == 'UPDATE':
            entry['columns_updated'] = entry['columns_written'][:]
        
        return entry

    def _populate_called_by_relations(self, source_entries: Dict[str, Dict], target_entries: Dict[str, Dict]):
        """Populate called_by lists based on calls_procedures fields."""
        for caller, entry in source_entries.items():
            for callee in entry.get('calls_procedures', []):
                if callee in target_entries:
                    target = target_entries[callee]
                    callers = target.setdefault('called_by', [])
                    if caller not in callers:
                        callers.append(caller)

    def _format_column_reference(self, table_name: Optional[str], column_name: Optional[str]) -> Optional[str]:
        """Return a fully-qualified column reference when possible."""
        if table_name and column_name:
            return f"{table_name}.{column_name}"
        if column_name:
            return column_name
        if table_name:
            return table_name
        return None

    def _stringify_lineage(self, lineage: Optional[Dict]) -> str:
        """Return a human-readable JSON string for lineage data."""
        if not lineage:
            return ''
        try:
            return json.dumps(lineage, indent=2, ensure_ascii=False)
        except Exception:
            return str(lineage)

    def _compute_complexity_score(self, metrics: Dict) -> int:
        """Compute a simple complexity score from LLM-provided metrics."""
        if not metrics:
            return 0
        score = (
            metrics.get('num_tables', 0) +
            metrics.get('num_joins', 0) * 2 +
            metrics.get('num_calculations', 0)
        )
        if metrics.get('has_aggregation'):
            score += 10
        if metrics.get('has_window_functions'):
            score += 10
        if metrics.get('has_subqueries'):
            score += 5
        if metrics.get('has_cte'):
            score += 5
        return score


def main():
    """Main entry point with LLM configuration"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description='T-SQL Database Lineage Analyzer with LLM Enhancement')
    
    # Basic arguments
    parser.add_argument('sql_directory', help='Directory containing SQL files')
    parser.add_argument('--output', '-o', default='./lineage_output', help='Output directory for reports')
    parser.add_argument('--dialect', '-d', default='tsql', help='SQL dialect (default: tsql)')
    parser.add_argument('--max-files', '-m', type=int, help='Maximum number of files to process')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    # LLM configuration
    parser.add_argument('--ollama-url', default='http://localhost:11434', help='Ollama API URL')
    parser.add_argument('--ollama-model', default='qwen2.5-coder:14b', help='Ollama model name')
    parser.add_argument('--openai-key', help='OpenAI API key (uses OpenAI if provided)')
    parser.add_argument('--openai-model', default='gpt-4o-mini', help='OpenAI model name')
    parser.add_argument('--batch-size', type=int, default=10, help='Parallel processing batch size')
    parser.add_argument('--timeout', type=int, default=300, help='Request timeout in seconds (default: 300 for complex procedures)')
    
    # Metadata
    parser.add_argument('--metadata', help='Path to metadata JSON file')
    
    args = parser.parse_args()
    
    # Get OpenAI settings from args (frontend handles configuration via server)
    # Do not use environment variable - key must be passed explicitly as parameter
    openai_key = args.openai_key
    openai_model = args.openai_model
    
    # Validate input directory
    if not Path(args.sql_directory).exists():
        print(f"Error: Directory '{args.sql_directory}' does not exist")
        sys.exit(1)
    
    # Load metadata if provided
    metadata = {}
    if args.metadata and Path(args.metadata).exists():
        with open(args.metadata, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        print(f"Loaded metadata from: {args.metadata}")
    
    # Run analysis
    orchestrator = LineageOrchestrator(
        sql_directory=args.sql_directory,
        output_directory=args.output,
        dialect=args.dialect,
        debug=args.debug,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        openai_api_key=openai_key,
        openai_model=openai_model,
        batch_size=args.batch_size,
        timeout=args.timeout,
        metadata=metadata
    )
    
    try:
        results = orchestrator.run_full_analysis(max_files=args.max_files)
        print("\n✓ Analysis completed successfully!")
        print(f"\nStatistics:")
        print(f"  Files analyzed: {results['statistics']['total_files']}")
        print(f"  Procedures: {results['statistics']['total_procedures']}")
        print(f"  Functions: {results['statistics']['total_functions']}")
        print(f"  LLM success rate: {results['statistics']['llm_success_rate']}")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Analysis failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()