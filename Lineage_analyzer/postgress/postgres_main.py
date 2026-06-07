"""
Main Orchestrator for PostgreSQL Lineage Analysis
Coordinates cleaning, analysis, and JSON building for complete database lineage
"""

import sys
from pathlib import Path
from datetime import datetime
import json
from typing import Dict, List

# Import all components
from .postgres_cleaner import PostgreSQLCleaner
from .postgres_analyzer import PostgreSQLAnalyzer
from .postgres_procedure_analyzer import PostgreSQLProcedureAnalyzer
from .postgres_json_builder import PostgreSQLLineageJSONBuilder
from .postgres_procedure_json_builder import PostgreSQLProcedureJSONBuilder


class LineageOrchestrator:
    """Main orchestrator for complete lineage analysis"""
    
    def __init__(self, sql_directory: str, output_directory: str, dialect: str = "postgres", debug: bool = False):
        self.sql_directory = Path(sql_directory)
        self.output_directory = Path(output_directory)
        self.dialect = dialect
        self.debug = debug
        
        # Create output directory
        self.output_directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.cleaner = PostgreSQLCleaner(sql_directory, debug=debug)
        self.statement_analyzer = PostgreSQLAnalyzer(dialect=dialect, debug=debug)
        self.procedure_analyzer = PostgreSQLProcedureAnalyzer(dialect=dialect, debug=debug)
        self.statement_json_builder = PostgreSQLLineageJSONBuilder(dialect, sql_directory)
        self.procedure_json_builder = PostgreSQLProcedureJSONBuilder(dialect, sql_directory)
        
        # Storage for results
        self.cleaned_files = {}
        self.statement_results = []
        self.procedure_results = []
        self.function_results = []
        self.view_results = []
        self.trigger_results = []
    
    def run_full_analysis(self, max_files: int = None) -> Dict:
        """Run complete lineage analysis pipeline"""
        print("\n" + "="*70)
        print("POSTGRESQL LINEAGE ANALYSIS PIPELINE")
        print("="*70)
        
        start_time = datetime.now()
        
        # Step 1: Clean SQL files
        print("\n[1/5] Cleaning SQL files...")
        self.cleaned_files = self.cleaner.clean_all_files(max_files=max_files)
        print(f"   Cleaned {len(self.cleaned_files)} files")
        
        # Step 2: Analyze statements
        print("\n[2/5] Analyzing SQL statements...")
        self._analyze_statements()
        print(f"   Analyzed {len(self.statement_results)} files with statements")
        
        # Step 3: Analyze procedures, functions, views
        print("\n[3/5] Analyzing procedures, functions, and views...")
        self._analyze_procedures_and_functions()
        print(f"   Analyzed {len(self.procedure_results)} procedures")
        print(f"   Analyzed {len(self.function_results)} functions")
        print(f"   Analyzed {len(self.view_results)} views")
        if self.trigger_results:
            print(f"   Analyzed {len(self.trigger_results)} triggers")
        
        # Step 4: Build statement lineage JSON
        print("\n[4/5] Building statement lineage report...")
        statement_report = self.statement_json_builder.build_lineage_report(self.statement_results)
        statement_output = self.output_directory / f"statement_lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.statement_json_builder.save_report(statement_report, str(statement_output))
        
        # Step 5: Build procedure/function lineage JSON
        print("\n[5/5] Building procedure/function lineage report...")
        procedure_report = self.procedure_json_builder.build_lineage_report(
            self.procedure_results,
            self.function_results,
            self.trigger_results
        )
        procedure_output = self.output_directory / f"procedure_lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        self.procedure_json_builder.save_report(procedure_report, str(procedure_output))
        
        # Step 6: Build combined summary
        print("\n[6/6] Building combined summary...")
        combined_summary = self._build_combined_summary(statement_report, procedure_report)
        summary_output = self.output_directory / f"lineage_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_output, 'w', encoding='utf-8') as f:
            json.dump(combined_summary, f, indent=2, ensure_ascii=False)
        print(f"   Summary saved to: {summary_output}")
        
        # Calculate elapsed time
        elapsed = datetime.now() - start_time
        
        # Print final summary
        print("\n" + "="*70)
        print("ANALYSIS COMPLETE")
        print("="*70)
        print(f"Total time: {elapsed.total_seconds():.2f} seconds")
        print(f"\nOutput files:")
        print(f"  1. Statement lineage: {statement_output.name}")
        print(f"  2. Procedure lineage: {procedure_output.name}")
        print(f"  3. Combined summary:  {summary_output.name}")
        print("="*70 + "\n")
        
        return {
            'statement_report': statement_report,
            'procedure_report': procedure_report,
            'combined_summary': combined_summary,
            'output_files': {
                'statements': str(statement_output),
                'procedures': str(procedure_output),
                'summary': str(summary_output)
            },
            'elapsed_time': elapsed.total_seconds()
        }
    
    def _analyze_statements(self):
        """Analyze regular SQL statements"""
        for file_path, content in self.cleaned_files.items():
            statements = content.get('statements', [])
            
            if statements:
                # Analyze all statements in file
                result = self.statement_analyzer.analyze_file(file_path, statements)
                self.statement_results.append(result)
            
            # Separately track views (they may have special handling)
            if content.get('views'):
                for view in content['views']:
                    # Views are analyzed like statements but tracked separately
                    view_result = self.statement_analyzer.analyze_file(
                        file_path,
                        [view['content']]
                    )
                    self.view_results.append({
                        'name': view['name'],
                        'file_path': file_path,
                        'result': view_result
                    })
    
    def _analyze_procedures_and_functions(self):
        """Analyze procedures and functions"""
        # Extract known tables from statement analysis
        known_tables = {}
        if hasattr(self.statement_json_builder, 'tables') and self.statement_json_builder.tables:
            for table_name, table_info in self.statement_json_builder.tables.items():
                columns = list(getattr(table_info, 'columns', {}).keys()) if hasattr(table_info, 'columns') else list(table_info.get('columns', {}).keys())
                known_tables[table_name] = columns

            # Pass known tables to procedure analyzer
            if hasattr(self.procedure_analyzer, 'set_known_tables'):
                self.procedure_analyzer.set_known_tables(known_tables)

            if self.debug:
                print(f"   Loaded {len(known_tables)} known tables for procedure analysis")
        
        for file_path, content in self.cleaned_files.items():
            # Analyze procedures
            if content.get('procedures'):
                proc_results = self.procedure_analyzer.analyze_procedures(
                    file_path,
                    content['procedures']
                )
                self.procedure_results.extend(proc_results)

            # Analyze functions
            if content.get('functions'):
                func_results = self.procedure_analyzer.analyze_functions(
                    file_path,
                    content['functions']
                )
                self.function_results.extend(func_results)

            # Analyze triggers
            if content.get('triggers'):
                trigger_results = self.procedure_analyzer.analyze_triggers(
                    file_path,
                    content['triggers']
                )
                self.trigger_results.extend(trigger_results)
    
    def _build_combined_summary(self, statement_report: Dict, procedure_report: Dict) -> Dict:
        """Build a combined summary report with safe defaults for missing keys"""
        s = statement_report.get('summary', {}) or {}
        p = procedure_report.get('summary', {}) or {}
        ws = statement_report.get('warnings', {}) or {}
        wp = procedure_report.get('warnings', {}) or {}

        total_statements = s.get('total_statements', 0)
        successful_parses = s.get('successful_parses', 0)
        denom = max(total_statements, 1)
        parse_success_rate = f"{(successful_parses / denom * 100):.1f}%"

        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_directory": str(self.sql_directory),
                "dialect": self.dialect,
                "database_type": "PostgreSQL"
            },
            "overall_summary": {
                "total_files_analyzed": len(self.cleaned_files),
                "total_statements": total_statements,
                "total_tables": s.get('total_tables', 0),
                "total_columns": s.get('total_columns', 0),
                "total_procedures": p.get('total_procedures', 0),
                "total_functions": p.get('total_functions', 0),
                "total_triggers": p.get('total_triggers', 0),
                "temp_tables": s.get('temp_tables', 0),
                "ctes": s.get('ctes', 0),
                "materialized_views": s.get('materialized_views', 0)
            },
            "statement_lineage": {
                "total_dependencies": s.get('total_dependencies', 0),
                "dynamic_sql_count": s.get('dynamic_sql_count', 0),
                "set_operations": s.get('set_operations', 0),
                "parse_success_rate": parse_success_rate,
                "array_operations": s.get('array_operations', 0),
                "jsonb_operations": s.get('jsonb_operations', 0),
                "upserts": s.get('upserts', 0),
                "returning_clauses": s.get('returning_clauses', 0)
            },
            "procedure_lineage": {
                "procedure_calls": p.get('procedure_calls', 0),
                "table_valued_functions": p.get('table_valued_functions', 0),
                "complex_procedures": p.get('complex_procedures_count', 0),
                "orphan_procedures": p.get('orphan_procedures_count', 0)
            },
            "warnings": {
                "circular_dependencies": ws.get('circular_dependencies', []),
                "circular_call_chains": wp.get('circular_call_chains', []),
                "dynamic_sql_detected": ws.get('dynamic_sql_detected', False)
            },
            "data_flow_summary": {
                "description": "Tables and their relationships",
                "most_referenced_tables": self._get_most_referenced_tables(statement_report),
                "most_active_procedures": self._get_most_active_procedures(procedure_report)
            }
        }
    
    def _get_most_referenced_tables(self, statement_report: Dict, top_n: int = 10) -> List[Dict]:
        """Get most referenced tables"""
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
    
    def _get_most_active_procedures(self, procedure_report: Dict, top_n: int = 10) -> List[Dict]:
        """Get most active procedures (by complexity score)"""
        proc_scores = []
        
        for proc_name, proc_info in procedure_report.get('procedures', {}).items():
            proc_scores.append({
                "procedure": proc_name,
                "complexity_score": proc_info.get('complexity_score', 0),
                "writes_tables": len(proc_info.get('writes_tables', [])),
                "reads_tables": len(proc_info.get('reads_tables', []))
            })
        
        # Sort by complexity score
        sorted_procs = sorted(proc_scores, key=lambda x: x['complexity_score'], reverse=True)
        
        return sorted_procs[:top_n]


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PostgreSQL Database Lineage Analyzer')
    parser.add_argument('sql_directory', help='Directory containing SQL files')
    parser.add_argument('--output', '-o', default='./lineage_output', help='Output directory for reports')
    parser.add_argument('--dialect', '-d', default='postgres', help='SQL dialect (default: postgres)')
    parser.add_argument('--max-files', '-m', type=int, help='Maximum number of files to process')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Validate input directory
    if not Path(args.sql_directory).exists():
        print(f"Error: Directory '{args.sql_directory}' does not exist")
        sys.exit(1)
    
    # Run analysis
    orchestrator = LineageOrchestrator(
        sql_directory=args.sql_directory,
        output_directory=args.output,
        dialect=args.dialect,
        debug=args.debug
    )
    
    try:
        results = orchestrator.run_full_analysis(max_files=args.max_files)
        print("\nAnalysis completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"\nAnalysis failed: {e}")
        if args.debug:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
