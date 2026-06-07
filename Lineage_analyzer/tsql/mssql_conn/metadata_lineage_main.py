"""
Metadata-Based Lineage Analysis Orchestrator
Uses database connection via enhanced_metadata_extractor instead of SQL files.

This module:
1. Extracts metadata from database using enhanced_metadata_extractor
2. Separates tabular SQL (views, query history) from executable SQL (procedures, functions, triggers)
3. Uses EnhancedSQLAnalyzer for tabular SQL (views, query history)
4. Uses EnhancedLLMLineageAnalyzer for executable SQL (procedures, functions, triggers)
5. Produces output in the same format as tsql_main.py for frontend compatibility
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

# Import the metadata extractor
from .enhanced_metadata_extractor import (
    extract_enhanced_database_metadata,
    build_connection_url
)

# Import SQL analysis components
from .tsql_analyzer import EnhancedSQLAnalyzer
from .json_builder import EnhancedLineageJSONBuilder

# Import LLM-based procedure analyzer
from .enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer
from .enhanced_json_builder import EnhancedProcedureJSONBuilder

# Import the metadata-based builders
from .metadata_statement_builder import MetadataStatementBuilder
from .metadata_view_analyzer import MetadataViewAnalyzer


class MetadataLineageOrchestrator:
    """
    Main orchestrator for metadata-based lineage analysis.
    
    Uses database connection instead of SQL files:
    1. Extracts metadata via enhanced_metadata_extractor
    2. Analyzes views and query history with traditional parsing (tabular SQL)
    3. Analyzes procedures/functions/triggers with LLM (executable SQL)
    4. Outputs in same format as file-based analysis for frontend compatibility
    """

    def __init__(
        self,
        # Database connection parameters
        server: str,
        database: str,
        username: str,
        password: str,
        driver: str = "{ODBC Driver 17 for SQL Server}",
        # Output configuration
        output_directory: str = "./lineage_output",
        dialect: str = "tsql",
        debug: bool = False,
        # LLM Configuration
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:14b",
        openai_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
        batch_size: int = 10,
        timeout: int = 300,
        # Optional: Pre-loaded metadata (if already extracted)
        preloaded_metadata: Optional[Dict] = None,
        # Optional: Metadata file path (load from disk)
        metadata_file_path: Optional[str] = None,
    ):
        """
        Initialize the metadata-based lineage orchestrator.
        
        Args:
            server: SQL Server hostname
            database: Database name
            username: Login username
            password: Login password
            driver: ODBC driver name
            output_directory: Output directory for reports
            dialect: SQL dialect (default: tsql)
            debug: Enable debug mode
            ollama_url: Ollama API endpoint
            ollama_model: Ollama model name
            openai_api_key: OpenAI API key (uses OpenAI if provided)
            openai_model: OpenAI model name
            batch_size: Parallel processing batch size
            timeout: Request timeout in seconds
            preloaded_metadata: Pre-extracted metadata dictionary
            metadata_file_path: Path to metadata JSON file
        """
        # Database connection params
        self.server = server
        self.database = database
        self.username = username
        self.password = password
        self.driver = driver
        
        # Configuration
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.dialect = dialect
        self.debug = debug
        
        # LLM configuration
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.batch_size = batch_size
        self.timeout = timeout
        
        # Metadata storage
        self.metadata: Optional[Dict] = None
        self.metadata_file_path: Optional[Path] = None
        
        # Load metadata from various sources
        if preloaded_metadata:
            self.metadata = preloaded_metadata
        elif metadata_file_path:
            self.metadata_file_path = Path(metadata_file_path)
            with open(self.metadata_file_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
        
        # Results storage
        self.view_results = []
        self.query_history_results = []
        self.procedure_results = []
        self.function_results = []
        self.trigger_results = []
        
        # LLM analyzed results
        self.llm_analyzed_procedures = []
        self.llm_analyzed_functions = []
        self.llm_analyzed_triggers = []
        
        # Statistics
        self.stats = defaultdict(int)

    def extract_metadata(self, force_refresh: bool = False) -> Dict:
        """
        Extract metadata from database connection.
        
        Args:
            force_refresh: Force re-extraction even if metadata exists
            
        Returns:
            Extracted metadata dictionary
        """
        if self.metadata and not force_refresh:
            print(f"Using existing metadata ({len(self.metadata.get('tables', []))} tables)")
            return self.metadata
        
        print("\n" + "="*80)
        print("EXTRACTING DATABASE METADATA")
        print("="*80)
        print(f"Server: {self.server}")
        print(f"Database: {self.database}")
        
        self.metadata, metadata_path = extract_enhanced_database_metadata(
            server=self.server,
            database=self.database,
            username=self.username,
            password=self.password,
            driver=self.driver,
            output_dir=self.output_directory
        )
        
        self.metadata_file_path = metadata_path
        
        # Print extraction summary
        summary = self.metadata.get('summary', {})
        print(f"\n✓ Metadata extraction complete:")
        print(f"   Tables: {summary.get('table_count', 0)}")
        print(f"   Views: {summary.get('view_count', 0)}")
        print(f"   Procedures: {summary.get('procedure_count', 0)}")
        print(f"   Functions: {summary.get('function_count', 0)}")
        print(f"   Triggers: {summary.get('trigger_count', 0)}")
        print(f"   Query History: {summary.get('query_history_count', 0)}")
        
        return self.metadata

    def run_full_analysis(self) -> Dict:
        """
        Run complete lineage analysis pipeline using database metadata.
        
        Returns:
            Complete analysis results dictionary
        """
        print("\n" + "="*80)
        print("METADATA-BASED LINEAGE ANALYSIS PIPELINE")
        print("="*80)
        
        start_time = datetime.now()
        
        # Step 1: Ensure metadata is extracted
        print("\n[1/7] Extracting/Loading database metadata...")
        metadata = self.extract_metadata()
        self.stats['metadata_extracted'] = 1
        
        # Step 2: Separate tabular vs executable SQL
        print("\n[2/7] Separating tabular and executable SQL components...")
        tabular_sql, executable_sql = self._separate_sql_components()
        print(f"   ✓ Tabular SQL (views, query history): {len(tabular_sql)}")
        print(f"   ✓ Executable SQL (procedures, functions, triggers): {len(executable_sql)}")
        
        # Step 3: Analyze tabular SQL (views, query history) with traditional parsing
        print("\n[3/7] Analyzing tabular SQL components...")
        self._analyze_tabular_sql(tabular_sql)
        print(f"   ✓ Analyzed {len(self.view_results)} views")
        print(f"   ✓ Analyzed {len(self.query_history_results)} query history entries")
        
        # Step 4: Initialize LLM analyzer with metadata context
        print("\n[4/7] Initializing LLM analyzer with table metadata context...")
        llm_analyzer = EnhancedLLMLineageAnalyzer(
            metadata=metadata,
            ollama_url=self.ollama_url,
            ollama_model=self.ollama_model,
            openai_api_key=self.openai_api_key,
            openai_model=self.openai_model,
            batch_size=self.batch_size,
            timeout=self.timeout
        )
        print(f"   ✓ LLM provider: {'OpenAI' if llm_analyzer.use_openai else 'Ollama'}")
        print(f"   ✓ Model: {self.openai_model if llm_analyzer.use_openai else self.ollama_model}")
        
        # Step 5: Analyze executable SQL with LLM
        print("\n[5/7] Analyzing executable SQL with LLM...")
        if executable_sql:
            llm_results = llm_analyzer.analyze_statements(executable_sql)
            
            # Separate results by type
            for result in llm_results:
                stmt_type = (result.get('type') or 'UNKNOWN').upper()
                if stmt_type in ['PROCEDURE', 'STORED_PROCEDURE']:
                    self.llm_analyzed_procedures.append(result)
                elif stmt_type in ['FUNCTION', 'SCALAR_FUNCTION', 'TABLE_FUNCTION', 'INLINE_FUNCTION']:
                    self.llm_analyzed_functions.append(result)
                elif stmt_type == 'TRIGGER':
                    self.llm_analyzed_triggers.append(result)
                else:
                    print(f"   ⚠ Warning: Unknown statement type '{stmt_type}' for {result.get('name', 'unknown')}")
            
            llm_analyzer.print_statistics()
        else:
            print("   ⚠ No executable SQL found to analyze")
        
        # Step 6: Build statement lineage JSON (views, query history)
        print("\n[6/7] Building statement lineage report...")
        statement_builder = MetadataStatementBuilder(
            dialect=self.dialect,
            database_name=self.database,
            metadata=metadata
        )
        statement_report = statement_builder.build_lineage_report(
            view_results=self.view_results,
            query_history_results=self.query_history_results
        )
        statement_output = self.output_directory / f"statement_lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(statement_output, 'w', encoding='utf-8') as f:
            json.dump(statement_report, f, indent=2, ensure_ascii=False)
        print(f"   ✓ Saved to: {statement_output.name}")
        
        # Step 7: Build LLM-enhanced procedure/function lineage JSON
        print("\n[7/7] Building LLM-enhanced procedure/function lineage report...")
        procedure_json_builder = EnhancedProcedureJSONBuilder(
            output_dir=self.output_directory
        )
        
        # Add all LLM results
        all_llm_results = (
            self.llm_analyzed_procedures + 
            self.llm_analyzed_functions + 
            self.llm_analyzed_triggers
        )
        procedure_json_builder.add_analysis_results(all_llm_results)
        
        # Generate all output files
        procedure_prefix = f"procedure_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_files = procedure_json_builder.generate_all_outputs(prefix=procedure_prefix)
        
        # Produce backward-compatible procedure report for UI/clients
        legacy_procedure_report = self._build_legacy_procedure_report(all_llm_results)
        legacy_procedure_path = self.output_directory / f"procedure_lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(legacy_procedure_path, 'w', encoding='utf-8') as f:
            json.dump(legacy_procedure_report, f, indent=2, ensure_ascii=False)
        print(f"   ✓ Legacy procedure lineage saved to: {legacy_procedure_path.name}")
        
        # Print summary
        procedure_json_builder.print_summary_report()
        
        # Build combined summary
        print("\n[8/8] Building combined summary...")
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
        print(f"\nMetadata source: Database connection ({self.server}/{self.database})")
        print(f"\nOutput files:")
        print(f"  1. Statement lineage:     {statement_output.name}")
        print(f"  2. Executable Components catalog:     {output_files.get('catalog', 'N/A')}")
        print(f"  3. Column lineage:        {output_files.get('column_lineage', 'N/A')}")
        print(f"  4. Dependency graph:      {output_files.get('dependency_graph', 'N/A')}")
        print(f"  5. Tabular Components usage:           {output_files.get('table_usage', 'N/A')}")
        print(f"  6. Complete analysis:     {output_files.get('complete', 'N/A')}")
        print(f"  7. Combined summary:      {summary_output.name}")
        if self.metadata_file_path:
            print(f"  8. Metadata cache:        {self.metadata_file_path}")
        print("="*80 + "\n")
        
        return {
            'statement_report': statement_report,
            'procedure_report': legacy_procedure_report,
            'procedure_analysis': all_llm_results,
            'combined_summary': combined_summary,
            'metadata': self.metadata,
            'output_files': {
                'statements': str(statement_output),
                'summary': str(summary_output),
                'procedures': str(legacy_procedure_path),
                'metadata': str(self.metadata_file_path) if self.metadata_file_path else None,
                **{k: str(v) for k, v in output_files.items()}
            },
            'elapsed_time': elapsed.total_seconds(),
            'statistics': {
                'total_tables': len(self.metadata.get('tables', [])),
                'total_views': len(self.view_results),
                'total_query_history': len(self.query_history_results),
                'total_procedures': len(self.llm_analyzed_procedures),
                'total_functions': len(self.llm_analyzed_functions),
                'total_triggers': len(self.llm_analyzed_triggers),
                'llm_success_rate': self._calculate_llm_success_rate()
            }
        }

    def _separate_sql_components(self) -> Tuple[List[Dict], List[Dict]]:
        """
        Separate metadata into tabular SQL and executable SQL.
        
        Returns:
            Tuple of (tabular_sql, executable_sql) lists
        """
        tabular_sql = []
        executable_sql = []
        
        # Views go to tabular SQL (analyzed with traditional parsing)
        for view in self.metadata.get('views', []):
            if view.get('definition'):
                tabular_sql.append({
                    'type': 'VIEW',
                    'name': f"{view.get('schema_name', 'dbo')}.{view.get('view_name')}",
                    'schema_name': view.get('schema_name', 'dbo'),
                    'object_name': view.get('view_name'),
                    'definition': view.get('definition'),
                    'original_sql': view.get('definition'),
                    'modified_sql': view.get('definition'),
                    'create_date': view.get('create_date'),
                    'modify_date': view.get('modify_date'),
                    'description': view.get('description')
                })
        
        # Query history goes to tabular SQL
        for query in self.metadata.get('query_history', []):
            if query.get('query_sql_text'):
                tabular_sql.append({
                    'type': 'QUERY_HISTORY',
                    'name': f"query_{query.get('query_text_id', 'unknown')}",
                    'query_text_id': query.get('query_text_id'),
                    'definition': query.get('query_sql_text'),
                    'original_sql': query.get('query_sql_text'),
                    'modified_sql': query.get('query_sql_text'),
                    'execution_count': query.get('count_executions'),
                    'avg_duration_ms': query.get('avg_duration_ms'),
                    'avg_cpu_time_ms': query.get('avg_cpu_time_ms'),
                    'last_execution_time': query.get('last_execution_time')
                })
        
        # Procedures go to executable SQL (analyzed with LLM)
        for proc in self.metadata.get('procedures', []):
            if proc.get('definition'):
                executable_sql.append({
                    'type': 'PROCEDURE',
                    'name': f"{proc.get('schema_name', 'dbo')}.{proc.get('procedure_name')}",
                    'schema_name': proc.get('schema_name', 'dbo'),
                    'object_name': proc.get('procedure_name'),
                    'definition': proc.get('definition'),
                    'original_sql': proc.get('definition'),
                    'modified_sql': proc.get('definition'),
                    'create_date': proc.get('create_date'),
                    'modify_date': proc.get('modify_date'),
                    'description': proc.get('description')
                })
        
        # Functions go to executable SQL (analyzed with LLM)
        for func in self.metadata.get('functions', []):
            if func.get('definition'):
                func_type = self._detect_function_type(func.get('function_type', ''))
                executable_sql.append({
                    'type': func_type,
                    'name': f"{func.get('schema_name', 'dbo')}.{func.get('function_name')}",
                    'schema_name': func.get('schema_name', 'dbo'),
                    'object_name': func.get('function_name'),
                    'definition': func.get('definition'),
                    'original_sql': func.get('definition'),
                    'modified_sql': func.get('definition'),
                    'create_date': func.get('create_date'),
                    'modify_date': func.get('modify_date'),
                    'description': func.get('description')
                })
        
        # Triggers go to executable SQL (analyzed with LLM)
        for trigger in self.metadata.get('triggers', []):
            if trigger.get('definition'):
                executable_sql.append({
                    'type': 'TRIGGER',
                    'name': f"{trigger.get('schema_name', 'dbo')}.{trigger.get('trigger_name')}",
                    'schema_name': trigger.get('schema_name', 'dbo'),
                    'object_name': trigger.get('trigger_name'),
                    'definition': trigger.get('definition'),
                    'original_sql': trigger.get('definition'),
                    'modified_sql': trigger.get('definition'),
                    'table_name': trigger.get('table_name'),
                    'trigger_event': trigger.get('trigger_event'),
                    'is_disabled': trigger.get('is_disabled'),
                    'create_date': trigger.get('create_date'),
                    'modify_date': trigger.get('modify_date')
                })
        
        return tabular_sql, executable_sql

    def _detect_function_type(self, function_type_desc: str) -> str:
        """Convert SQL Server function type description to our type."""
        type_map = {
            'SQL_SCALAR_FUNCTION': 'SCALAR_FUNCTION',
            'SQL_TABLE_VALUED_FUNCTION': 'TABLE_FUNCTION',
            'SQL_INLINE_TABLE_VALUED_FUNCTION': 'INLINE_FUNCTION',
            'CLR_SCALAR_FUNCTION': 'SCALAR_FUNCTION',
            'CLR_TABLE_VALUED_FUNCTION': 'TABLE_FUNCTION',
        }
        return type_map.get(function_type_desc, 'FUNCTION')

    def _analyze_tabular_sql(self, tabular_sql: List[Dict]):
        """
        Analyze tabular SQL (views, query history) using traditional parsing.
        
        Args:
            tabular_sql: List of tabular SQL components
        """
        # Initialize the view analyzer
        view_analyzer = MetadataViewAnalyzer(
            dialect=self.dialect,
            metadata=self.metadata,
            debug=self.debug
        )
        
        for item in tabular_sql:
            sql_type = item.get('type', 'UNKNOWN')
            definition = item.get('definition', '')
            
            if not definition:
                continue
            
            try:
                # Analyze the SQL
                result = view_analyzer.analyze_sql(
                    sql=definition,
                    name=item.get('name'),
                    sql_type=sql_type
                )
                
                # Add metadata
                result['metadata'] = {
                    'schema_name': item.get('schema_name'),
                    'object_name': item.get('object_name'),
                    'create_date': item.get('create_date'),
                    'modify_date': item.get('modify_date'),
                    'description': item.get('description')
                }
                
                # Add query history specific metadata
                if sql_type == 'QUERY_HISTORY':
                    result['query_stats'] = {
                        'query_text_id': item.get('query_text_id'),
                        'execution_count': item.get('execution_count'),
                        'avg_duration_ms': item.get('avg_duration_ms'),
                        'avg_cpu_time_ms': item.get('avg_cpu_time_ms'),
                        'last_execution_time': str(item.get('last_execution_time'))
                    }
                    self.query_history_results.append(result)
                else:
                    self.view_results.append(result)
                
                self.stats['tabular_analyzed'] += 1
                
            except Exception as e:
                if self.debug:
                    print(f"   Warning: Failed to analyze {item.get('name')}: {e}")
                self.stats['tabular_errors'] += 1

    def _calculate_llm_success_rate(self) -> str:
        """Calculate success rate of LLM analysis."""
        total = (
            len(self.llm_analyzed_procedures) + 
            len(self.llm_analyzed_functions) + 
            len(self.llm_analyzed_triggers)
        )
        if total == 0:
            return "N/A"
        
        successful = sum(
            1 for result in (
                self.llm_analyzed_procedures + 
                self.llm_analyzed_functions + 
                self.llm_analyzed_triggers
            )
            if result.get('analysis_success', False)
        )
        
        return f"{(successful / total * 100):.1f}%"

    def _build_combined_summary(
        self, 
        statement_report: Dict, 
        procedure_output_files: Dict
    ) -> Dict:
        """Build a combined summary report."""
        s = statement_report.get('summary', {}) or {}
        metadata_summary = self.metadata.get('summary', {}) or {}
        
        # LLM statistics
        total_procs = len(self.llm_analyzed_procedures)
        total_funcs = len(self.llm_analyzed_functions)
        total_triggers = len(self.llm_analyzed_triggers)
        successful_llm = sum(
            1 for r in (
                self.llm_analyzed_procedures + 
                self.llm_analyzed_functions + 
                self.llm_analyzed_triggers
            )
            if r.get('analysis_success', False)
        )
        total_llm = total_procs + total_funcs + total_triggers
        llm_success_rate = f"{(successful_llm / max(total_llm, 1) * 100):.1f}%"
        
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_type": "database_connection",
                "server": self.server,
                "database": self.database,
                "dialect": self.dialect,
                "analysis_method": "Metadata-Based with LLM-Enhanced Procedure Analysis"
            },
            "database_summary": {
                "extraction_timestamp": metadata_summary.get('extraction_timestamp'),
                "total_tables": metadata_summary.get('table_count', 0),
                "total_views": metadata_summary.get('view_count', 0),
                "total_procedures": metadata_summary.get('procedure_count', 0),
                "total_functions": metadata_summary.get('function_count', 0),
                "total_triggers": metadata_summary.get('trigger_count', 0),
                "total_columns": metadata_summary.get('column_count', 0),
                "total_indexes": metadata_summary.get('index_count', 0),
                "total_foreign_keys": metadata_summary.get('foreign_key_count', 0),
                "query_history_count": metadata_summary.get('query_history_count', 0)
            },
            "overall_summary": {
                "views_analyzed": len(self.view_results),
                "query_history_analyzed": len(self.query_history_results),
                "total_tables_referenced": s.get('total_tables', 0),
                "total_columns_mapped": s.get('total_columns', 0),
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
                "parse_success_rate": s.get('parse_success_rate', 'N/A')
            },
            "procedure_lineage": {
                "analysis_method": "LLM-based" if total_llm > 0 else "None",
                "llm_provider": "OpenAI" if self.openai_api_key else "Ollama",
                "llm_model": self.openai_model if self.openai_api_key else self.ollama_model,
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
            }
        }

    def _build_legacy_procedure_report(self, all_llm_results: List[Dict]) -> Dict:
        """
        Build legacy procedure report for frontend compatibility.
        
        This produces the same format as tsql_main.py for seamless integration.
        """
        procedures = {}
        functions = {}
        triggers = {}
        
        for result in all_llm_results:
            stmt_type = (result.get('type') or 'UNKNOWN').upper()
            name = result.get('name', 'unknown')
            
            entry = self._build_legacy_entry(result)
            
            if stmt_type in ['PROCEDURE', 'STORED_PROCEDURE']:
                procedures[name] = entry
            elif stmt_type in ['FUNCTION', 'SCALAR_FUNCTION', 'TABLE_FUNCTION', 'INLINE_FUNCTION']:
                functions[name] = entry
            elif stmt_type == 'TRIGGER':
                triggers[name] = entry
        
        # Populate called_by relations
        self._populate_called_by_relations(procedures, procedures)
        self._populate_called_by_relations(procedures, functions)
        self._populate_called_by_relations(functions, procedures)
        self._populate_called_by_relations(functions, functions)
        
        # Calculate statistics
        total = len(all_llm_results)
        successful = sum(1 for r in all_llm_results if r.get('analysis_success', False))
        
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_type": "database_metadata",
                "server": self.server,
                "database": self.database,
                "analysis_method": "LLM-based",
                "llm_provider": "OpenAI" if self.openai_api_key else "Ollama"
            },
            "summary": {
                "total_analyzed": total,
                "successful": successful,
                "failed": total - successful,
                "success_rate": f"{(successful / max(total, 1) * 100):.1f}%",
                "procedures_count": len(procedures),
                "functions_count": len(functions),
                "triggers_count": len(triggers)
            },
            "procedures": procedures,
            "functions": functions,
            "triggers": triggers
        }

    def _build_legacy_entry(self, result: Dict) -> Dict:
        """Build a single legacy entry from LLM analysis result."""
        lineage = result.get('lineage_analysis', {}) or {}
        
        # Initialize entry
        entry = {
            'name': result.get('name'),
            'type': result.get('type'),
            'schema_name': result.get('schema_name'),
            'analysis_success': result.get('analysis_success', False),
            'analyzed_at': result.get('analyzed_at'),
            'llm_provider': result.get('llm_provider'),
            'llm_prompt': result.get('llm_prompt', ''),
            'llm_raw_response': result.get('llm_raw_response') or json.dumps(lineage, indent=2, default=str),
            'table_context_used': result.get('table_context_used', []),
            'lineage_analysis': lineage,
            'reads_tables': [],
            'writes_tables': [],
            'columns_read': [],
            'columns_written': [],
            'columns_returned': [],
            'calls_procedures': [],
            'calls_functions': [],
            'called_by': [],
            'creates_temp_tables': [],
            'column_lineage': [],
            'original_sql': result.get('original_sql', ''),
            'complexity_score': 0
        }
        
        if 'error' in lineage:
            entry['error'] = lineage.get('error')
            return entry
        
        # Process source tables (reads)
        read_tables = set()
        read_columns = set()
        for source in lineage.get('source_tables', []):
            table_name = source.get('table_list')
            if table_name:
                read_tables.add(table_name)
                for col in source.get('columns_used', []):
                    read_columns.add(f"{table_name}.{col}")
        entry['reads_tables'] = sorted(read_tables)
        
        # Process target (writes)
        write_tables = set()
        written_columns = set()
        returned_columns = set()
        target = lineage.get('target', {})
        target_name = target.get('name')
        operation = (target.get('operation') or '').upper()
        
        if target_name and operation in ['INSERT', 'UPDATE', 'DELETE', 'MERGE', 'CREATE']:
            write_tables.add(target_name)
            for col in target.get('columns_affected', []):
                ref = f"{target_name}.{col}"
                written_columns.add(ref)
        
        entry['writes_tables'] = sorted(write_tables)
        entry['columns_written'] = sorted(written_columns)
        
        # Process dependencies (procedure/function calls)
        deps = lineage.get('dependencies', {})
        entry['calls_procedures'] = deps.get('procedures', [])
        entry['calls_functions'] = deps.get('functions', [])
        
        # Process temp tables
        temp_tables = set()
        for obj in lineage.get('intermediate_objects', []):
            obj_name = obj.get('name')
            obj_type = (obj.get('type') or '').upper()
            if obj_name and (obj_type.startswith('TEMP') or obj_name.startswith('#')):
                temp_tables.add(obj_name)
                write_tables.add(obj_name)
        entry['creates_temp_tables'] = sorted(temp_tables)
        
        # Process column lineage
        column_lineage_entries = []
        for mapping in lineage.get('column_lineage', []):
            sources = []
            for source in mapping.get('source_columns', []):
                if isinstance(source, str):
                    sources.append(source)
                elif isinstance(source, dict):
                    table = source.get('table_list', '')
                    col = source.get('column', '')
                    if table and col:
                        sources.append(f"{table}.{col}")
                    elif col:
                        sources.append(col)
            read_columns.update(sources)
            
            target_col = mapping.get('target_column')
            if target_col:
                returned_columns.add(target_col)
            
            column_lineage_entries.append({
                "target_column": target_col,
                "sources": sources,
                "transformation": mapping.get('transformation', {})
            })
        
        entry['column_lineage'] = column_lineage_entries
        entry['columns_read'] = sorted(read_columns)
        entry['columns_returned'] = sorted(returned_columns)
        
        # Calculate complexity score
        metrics = lineage.get('complexity_metrics', {})
        entry['complexity_score'] = self._compute_complexity_score(metrics)
        
        return entry

    def _populate_called_by_relations(
        self, 
        source_entries: Dict[str, Dict], 
        target_entries: Dict[str, Dict]
    ):
        """Populate called_by lists based on calls_procedures fields."""
        for caller, entry in source_entries.items():
            for callee in entry.get('calls_procedures', []) + entry.get('calls_functions', []):
                if callee in target_entries:
                    target = target_entries[callee]
                    callers = target.setdefault('called_by', [])
                    if caller not in callers:
                        callers.append(caller)

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
    """Main entry point with command-line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Metadata-Based T-SQL Lineage Analyzer with LLM Enhancement'
    )
    
    # Database connection arguments
    parser.add_argument('--server', '-s', required=True, help='SQL Server hostname')
    parser.add_argument('--database', '-db', required=True, help='Database name')
    parser.add_argument('--username', '-u', required=True, help='Login username')
    parser.add_argument('--password', '-p', required=True, help='Login password')
    parser.add_argument('--driver', default='{ODBC Driver 17 for SQL Server}', help='ODBC driver')
    
    # Output configuration
    parser.add_argument('--output', '-o', default='./lineage_output', help='Output directory')
    parser.add_argument('--dialect', '-d', default='tsql', help='SQL dialect')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    # LLM configuration
    parser.add_argument('--ollama-url', default='http://localhost:11434', help='Ollama API URL')
    parser.add_argument('--ollama-model', default='qwen2.5-coder:14b', help='Ollama model name')
    parser.add_argument('--openai-key', help='OpenAI API key (uses OpenAI if provided)')
    parser.add_argument('--openai-model', default='gpt-4o-mini', help='OpenAI model name')
    parser.add_argument('--batch-size', type=int, default=10, help='Parallel processing batch size')
    parser.add_argument('--timeout', type=int, default=300, help='Request timeout in seconds')
    
    # Metadata options
    parser.add_argument('--metadata-file', help='Path to pre-extracted metadata JSON file')
    
    args = parser.parse_args()
    
    # Run analysis
    orchestrator = MetadataLineageOrchestrator(
        server=args.server,
        database=args.database,
        username=args.username,
        password=args.password,
        driver=args.driver,
        output_directory=args.output,
        dialect=args.dialect,
        debug=args.debug,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        openai_api_key=args.openai_key,
        openai_model=args.openai_model,
        batch_size=args.batch_size,
        timeout=args.timeout,
        metadata_file_path=args.metadata_file
    )
    
    try:
        results = orchestrator.run_full_analysis()
        print("\n✓ Analysis completed successfully!")
        print(f"\nStatistics:")
        stats = results['statistics']
        print(f"  Tables in database: {stats['total_tables']}")
        print(f"  Views analyzed: {stats['total_views']}")
        print(f"  Query history analyzed: {stats['total_query_history']}")
        print(f"  Procedures: {stats['total_procedures']}")
        print(f"  Functions: {stats['total_functions']}")
        print(f"  Triggers: {stats['total_triggers']}")
        print(f"  LLM success rate: {stats['llm_success_rate']}")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Analysis failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
