"""
Metadata-Based Lineage Analysis Orchestrator for Teradata
Uses database connection via enhanced_metadata_extractor instead of SQL files.

This module:
1. Extracts metadata from Teradata database using enhanced_metadata_extractor
2. Separates tabular SQL (views, query history) from executable SQL (procedures, functions, macros)
3. Uses MetadataViewAnalyzer for tabular SQL
4. Uses EnhancedLLMLineageAnalyzer for executable SQL
5. Produces output compatible with frontend visualization

Teradata-specific features:
- Volatile tables and Global Temporary tables
- Macros (Teradata's stored procedures)
- UDFs and external procedures
- COLLECT STATISTICS statements
- QUALIFY and SAMPLE clauses
- Teradata-style outer joins
- Multiset/Set table types
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

# Import the metadata extractor (to be created)
try:
    from .enhanced_metadata_extractor import (
        extract_enhanced_database_metadata,
        build_connection_params
    )
except ImportError:
    # Fallback for when metadata extractor is not yet created
    extract_enhanced_database_metadata = None
    build_connection_params = None

# Import SQL analysis components
from .teradata_analyzer import EnhancedSQLAnalyzer

# Import LLM-based procedure analyzer
from .enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer

# Import the metadata-based builders (to be created)
try:
    from .metadata_view_analyzer import MetadataViewAnalyzer
except ImportError:
    # Fallback - use enhanced analyzer for views
    MetadataViewAnalyzer = None


class MetadataLineageOrchestrator:
    """
    Main orchestrator for metadata-based lineage analysis in Teradata.

    Uses database connection instead of SQL files:
    1. Extracts metadata via enhanced_metadata_extractor
    2. Analyzes views and query history with traditional parsing
    3. Analyzes procedures/functions/macros with LLM
    4. Outputs in same format as file-based analysis
    """

    def __init__(
        self,
        # Teradata connection parameters
        host: str,
        user: str,
        password: str = "",
        database: str = "",
        logmech: str = "TD2",
        encryptdata: str = "ON",
        # Output configuration
        output_directory: str = "./lineage_output",
        dialect: str = "teradata",
        debug: bool = False,
        # LLM Configuration
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:14b",
        openai_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
        batch_size: int = 10,
        timeout: int = 300,
        # Optional: Pre-loaded metadata
        preloaded_metadata: Optional[Dict] = None,
        # Optional: Metadata file path
        metadata_file_path: Optional[str] = None,
    ):
        """
        Initialize the metadata-based lineage orchestrator for Teradata.

        Args:
            host: Teradata server hostname or IP address
            user: Database username
            password: Database password
            database: Default database name (optional, uses user's default if not specified)
            logmech: Authentication mechanism (default: TD2)
            encryptdata: Data encryption setting (default: ON)
            output_directory: Output directory for reports
            dialect: SQL dialect (default: teradata)
            debug: Enable debug mode
            ollama_url: Ollama API endpoint
            ollama_model: Ollama model name
            openai_api_key: OpenAI API key
            openai_model: OpenAI model name
            batch_size: Parallel processing batch size
            timeout: Request timeout in seconds
            preloaded_metadata: Pre-extracted metadata dictionary
            metadata_file_path: Path to metadata JSON file
        """
        # Teradata connection params
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.logmech = logmech
        self.encryptdata = encryptdata

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
        self.macro_results = []

        # LLM analyzed results
        self.llm_analyzed_procedures = []
        self.llm_analyzed_functions = []
        self.llm_analyzed_macros = []

        # Statistics
        self.stats = defaultdict(int)

    def extract_metadata(self, force_refresh: bool = False) -> Dict:
        """
        Extract metadata from Teradata database connection.

        Args:
            force_refresh: Force re-extraction even if metadata exists

        Returns:
            Extracted metadata dictionary
        """
        if self.metadata and not force_refresh:
            print(f"Using existing metadata ({len(self.metadata.get('tables', []))} tables)")
            return self.metadata

        if extract_enhanced_database_metadata is None:
            raise ImportError(
                "enhanced_metadata_extractor module not found. "
                "Please ensure enhanced_metadata_extractor.py is created in the same directory."
            )

        print("\n" + "="*80)
        print("EXTRACTING TERADATA DATABASE METADATA")
        print("="*80)
        print(f"Host: {self.host}")
        print(f"Database: {self.database or '(using user default)'}")
        print(f"User: {self.user}")

        self.metadata, metadata_path = extract_enhanced_database_metadata(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            logmech=self.logmech,
            encryptdata=self.encryptdata,
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
        print(f"   Macros: {summary.get('macro_count', 0)}")
        print(f"   Triggers: {summary.get('trigger_count', 0)}")
        if summary.get('query_history_count'):
            print(f"   Query History: {summary.get('query_history_count', 0)}")

        return self.metadata

    def run_full_analysis(self) -> Dict:
        """
        Run complete lineage analysis pipeline using database metadata.

        Returns:
            Complete analysis results dictionary
        """
        print("\n" + "="*80)
        print("TERADATA METADATA-BASED LINEAGE ANALYSIS PIPELINE")
        print("="*80)

        start_time = datetime.now()

        # Step 1: Ensure metadata is extracted
        print("\n[1/6] Extracting/Loading database metadata...")
        metadata = self.extract_metadata()
        self.stats['metadata_extracted'] = 1

        # Step 2: Separate tabular vs executable SQL
        print("\n[2/6] Separating tabular and executable SQL components...")
        tabular_sql, executable_sql = self._separate_sql_components()
        print(f"   ✓ Tabular SQL (views, query history): {len(tabular_sql)}")
        print(f"   ✓ Executable SQL (procedures, functions, macros): {len(executable_sql)}")

        # Step 3: Analyze tabular SQL
        print("\n[3/6] Analyzing tabular SQL components...")
        self._analyze_tabular_sql(tabular_sql)
        print(f"   ✓ Analyzed {len(self.view_results)} views")
        if self.query_history_results:
            print(f"   ✓ Analyzed {len(self.query_history_results)} query history entries")

        # Step 4: Initialize LLM analyzer
        print("\n[4/6] Initializing LLM analyzer with table metadata context...")
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
        print("\n[5/6] Analyzing executable SQL with LLM...")
        if executable_sql:
            llm_results = llm_analyzer.analyze_statements(executable_sql)

            # Separate results by type
            for result in llm_results:
                stmt_type = (result.get('type') or 'UNKNOWN').upper()
                if stmt_type in ['PROCEDURE', 'STORED_PROCEDURE', 'EXTERNAL_PROCEDURE']:
                    self.llm_analyzed_procedures.append(result)
                elif 'FUNCTION' in stmt_type or stmt_type in ['UDF']:
                    self.llm_analyzed_functions.append(result)
                elif stmt_type == 'MACRO':
                    self.llm_analyzed_macros.append(result)
                else:
                    print(f"   ⚠ Warning: Unknown statement type '{stmt_type}' for {result.get('name', 'unknown')}")

            llm_analyzer.print_statistics()
        else:
            print("   ⚠ No executable SQL found to analyze")

        # Step 6: Build output reports
        print("\n[6/6] Building lineage reports...")

        # Build statement lineage JSON
        statement_report = self._build_statement_report()
        statement_output = self.output_directory / f"statement_lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(statement_output, 'w', encoding='utf-8') as f:
            json.dump(statement_report, f, indent=2, ensure_ascii=False, default=str)
        print(f"   ✓ Statement lineage saved to: {statement_output.name}")

        # Build procedure lineage JSON
        all_llm_results = self.llm_analyzed_procedures + self.llm_analyzed_functions + self.llm_analyzed_macros
        procedure_report = self._build_procedure_report(all_llm_results)
        procedure_output = self.output_directory / f"procedure_lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(procedure_output, 'w', encoding='utf-8') as f:
            json.dump(procedure_report, f, indent=2, ensure_ascii=False, default=str)
        print(f"   ✓ Procedure lineage saved to: {procedure_output.name}")

        # Build combined summary
        combined_summary = self._build_combined_summary(statement_report, procedure_report)
        summary_output = self.output_directory / f"lineage_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_output, 'w', encoding='utf-8') as f:
            json.dump(combined_summary, f, indent=2, ensure_ascii=False, default=str)
        print(f"   ✓ Summary saved to: {summary_output.name}")

        # Calculate elapsed time
        elapsed = datetime.now() - start_time

        # Print final summary
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        print(f"Total time: {elapsed.total_seconds():.2f} seconds")
        print(f"\nMetadata source: Teradata ({self.host}/{self.database or 'default'})")
        print(f"\nOutput files:")
        print(f"  1. Statement lineage: {statement_output.name}")
        print(f"  2. Procedure lineage: {procedure_output.name}")
        print(f"  3. Combined summary:  {summary_output.name}")
        if self.metadata_file_path:
            print(f"  4. Metadata cache:    {self.metadata_file_path.name}")
        print("="*80 + "\n")

        return {
            'statement_report': statement_report,
            'procedure_report': procedure_report,
            'combined_summary': combined_summary,
            'metadata': self.metadata,
            'output_files': {
                'statements': str(statement_output),
                'procedures': str(procedure_output),
                'summary': str(summary_output),
                'metadata': str(self.metadata_file_path) if self.metadata_file_path else None,
            },
            'elapsed_time': elapsed.total_seconds(),
            'statistics': {
                'total_tables': len(self.metadata.get('tables', [])),
                'total_views': len(self.view_results),
                'total_query_history': len(self.query_history_results),
                'total_procedures': len(self.llm_analyzed_procedures),
                'total_functions': len(self.llm_analyzed_functions),
                'total_macros': len(self.llm_analyzed_macros),
                'llm_success_rate': self._calculate_llm_success_rate()
            }
        }

    def _separate_sql_components(self) -> Tuple[List[Dict], List[Dict]]:
        """Separate metadata into tabular SQL and executable SQL."""
        tabular_sql = []
        executable_sql = []

        # Views go to tabular SQL
        for view in self.metadata.get('views', []):
            if view.get('definition') or view.get('view_definition'):
                definition = view.get('definition') or view.get('view_definition')
                database_name = view.get('database_name') or view.get('database') or self.database or 'DBC'
                view_name = view.get('view_name') or view.get('name')

                tabular_sql.append({
                    'type': 'VIEW',
                    'name': f"{database_name}.{view_name}",
                    'database_name': database_name,
                    'object_name': view_name,
                    'definition': definition,
                    'original_sql': definition,
                    'modified_sql': definition,
                    'create_date': view.get('create_date') or view.get('created_timestamp'),
                    'modify_date': view.get('modify_date') or view.get('last_altered_timestamp'),
                    'description': view.get('description') or view.get('comment'),
                    'check_option': view.get('check_option'),
                    'is_updatable': view.get('is_updatable')
                })

        # Query history goes to tabular SQL (if available)
        for query in self.metadata.get('query_history', []):
            if query.get('query_text'):
                tabular_sql.append({
                    'type': 'QUERY_HISTORY',
                    'name': f"query_{query.get('query_id', 'unknown')}",
                    'query_id': query.get('query_id'),
                    'definition': query.get('query_text'),
                    'original_sql': query.get('query_text'),
                    'modified_sql': query.get('query_text'),
                    'query_type': query.get('query_type'),
                    'user_name': query.get('user_name'),
                    'start_time': query.get('start_time'),
                    'duration_ms': query.get('duration_ms')
                })

        # Procedures go to executable SQL
        for proc in self.metadata.get('procedures', []):
            if proc.get('definition') or proc.get('procedure_definition'):
                definition = proc.get('definition') or proc.get('procedure_definition')
                database_name = proc.get('database_name') or proc.get('database') or self.database or 'DBC'
                proc_name = proc.get('procedure_name') or proc.get('name')

                executable_sql.append({
                    'type': 'PROCEDURE',
                    'name': f"{database_name}.{proc_name}",
                    'database_name': database_name,
                    'object_name': proc_name,
                    'definition': definition,
                    'original_sql': definition,
                    'modified_sql': definition,
                    'language': proc.get('language', 'SQL'),
                    'parameter_signature': proc.get('parameter_signature'),
                    'create_date': proc.get('create_date') or proc.get('created_timestamp'),
                    'modify_date': proc.get('modify_date') or proc.get('last_altered_timestamp'),
                    'description': proc.get('description') or proc.get('comment')
                })

        # Functions go to executable SQL
        for func in self.metadata.get('functions', []):
            if func.get('definition') or func.get('function_definition'):
                definition = func.get('definition') or func.get('function_definition')
                database_name = func.get('database_name') or func.get('database') or self.database or 'DBC'
                func_name = func.get('function_name') or func.get('name')

                executable_sql.append({
                    'type': 'FUNCTION',
                    'name': f"{database_name}.{func_name}",
                    'database_name': database_name,
                    'object_name': func_name,
                    'definition': definition,
                    'original_sql': definition,
                    'modified_sql': definition,
                    'language': func.get('language', 'SQL'),
                    'return_type': func.get('return_type'),
                    'parameter_signature': func.get('parameter_signature'),
                    'function_type': func.get('function_type'),
                    'create_date': func.get('create_date') or func.get('created_timestamp'),
                    'modify_date': func.get('modify_date') or func.get('last_altered_timestamp'),
                    'description': func.get('description') or func.get('comment')
                })

        # Macros go to executable SQL (Teradata-specific)
        for macro in self.metadata.get('macros', []):
            if macro.get('definition') or macro.get('macro_definition'):
                definition = macro.get('definition') or macro.get('macro_definition')
                database_name = macro.get('database_name') or macro.get('database') or self.database or 'DBC'
                macro_name = macro.get('macro_name') or macro.get('name')

                executable_sql.append({
                    'type': 'MACRO',
                    'name': f"{database_name}.{macro_name}",
                    'database_name': database_name,
                    'object_name': macro_name,
                    'definition': definition,
                    'original_sql': definition,
                    'modified_sql': definition,
                    'parameter_signature': macro.get('parameter_signature'),
                    'create_date': macro.get('create_date') or macro.get('created_timestamp'),
                    'modify_date': macro.get('modify_date') or macro.get('last_altered_timestamp'),
                    'description': macro.get('description') or macro.get('comment')
                })

        # If nothing was discovered, synthesize simple SELECT statements from base tables
        if not tabular_sql and not executable_sql:
            tables = self.metadata.get('tables', [])
            if tables:
                print("   ⚠ No view/procedure/query history definitions found. Generating synthetic table statements for visualization.")
                max_tables = 250
                for table in tables[:max_tables]:
                    database = table.get('database') or table.get('database_name') or self.database or 'DBC'
                    name = table.get('name') or table.get('table_name')
                    if not name:
                        continue
                    qualified_name = f"{database}.{name}"
                    synthetic_sql = f"SELECT * FROM {qualified_name};"
                    tabular_sql.append({
                        'type': 'TABLE_METADATA',
                        'name': qualified_name,
                        'database_name': database,
                        'object_name': name,
                        'definition': synthetic_sql,
                        'original_sql': synthetic_sql,
                        'modified_sql': synthetic_sql,
                        'description': table.get('description') or table.get('comment'),
                        'generated_from_metadata': True
                    })
                if len(tables) > max_tables:
                    print(f"     (Showing first {max_tables} tables out of {len(tables)} for visualization)")

        return tabular_sql, executable_sql

    def _analyze_tabular_sql(self, tabular_sql: List[Dict]):
        """Analyze tabular SQL using traditional parsing."""
        # Try to use MetadataViewAnalyzer if available, otherwise use EnhancedSQLAnalyzer
        if MetadataViewAnalyzer:
            view_analyzer = MetadataViewAnalyzer(
                dialect=self.dialect,
                metadata=self.metadata,
                debug=self.debug
            )
            use_view_analyzer = True
        else:
            # Fallback to EnhancedSQLAnalyzer
            view_analyzer = EnhancedSQLAnalyzer(
                dialect=self.dialect,
                debug=self.debug
            )
            use_view_analyzer = False

        for item in tabular_sql:
            sql_type = item.get('type', 'UNKNOWN')
            definition = item.get('definition', '')

            if not definition:
                continue

            try:
                if use_view_analyzer:
                    result = view_analyzer.analyze_sql(
                        sql=definition,
                        name=item.get('name'),
                        sql_type=sql_type
                    )
                else:
                    # Use file analyzer for single statement
                    file_result = view_analyzer.analyze_file(
                        file_path=item.get('name', 'unknown'),
                        statements=[definition]
                    )

                    # Convert to expected format
                    lineages = file_result.get('lineages', [])
                    if lineages:
                        lineage = lineages[0]
                        result = {
                            'name': item.get('name'),
                            'type': sql_type,
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
                                    'is_calculated': cl.is_calculated
                                }
                                for cl in lineage.column_lineage
                            ],
                            'cte_definitions': lineage.cte_definitions,
                            'teradata_features': lineage.teradata_features,
                            'analysis_success': lineage.parse_error is None
                        }
                    else:
                        result = {
                            'name': item.get('name'),
                            'type': sql_type,
                            'analysis_success': False
                        }

                result['metadata'] = {
                    'database_name': item.get('database_name'),
                    'object_name': item.get('object_name'),
                    'create_date': item.get('create_date'),
                    'modify_date': item.get('modify_date'),
                    'description': item.get('description')
                }

                if sql_type == 'QUERY_HISTORY':
                    result['query_stats'] = {
                        'query_id': item.get('query_id'),
                        'query_type': item.get('query_type'),
                        'user_name': item.get('user_name'),
                        'start_time': str(item.get('start_time')),
                        'duration_ms': item.get('duration_ms')
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
        total = len(self.llm_analyzed_procedures) + len(self.llm_analyzed_functions) + len(self.llm_analyzed_macros)
        if total == 0:
            return "N/A"

        successful = sum(
            1 for result in (self.llm_analyzed_procedures + self.llm_analyzed_functions + self.llm_analyzed_macros)
            if result.get('analysis_success', False)
        )

        return f"{(successful / total * 100):.1f}%"

    def _build_statement_report(self) -> Dict:
        """Build statement lineage report."""
        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_type": "teradata_metadata",
                "host": self.host,
                "database": self.database or "(user default)",
                "dialect": self.dialect
            },
            "summary": {
                "total_views": len(self.view_results),
                "total_queries": len(self.query_history_results),
                "successful_parses": sum(1 for r in self.view_results + self.query_history_results if r.get('analysis_success'))
            },
            "views": self.view_results,
            "query_history": self.query_history_results
        }

    def _build_procedure_report(self, all_llm_results: List[Dict]) -> Dict:
        """Build procedure lineage report."""
        procedures = {}
        functions = {}
        macros = {}

        for result in all_llm_results:
            stmt_type = (result.get('type') or 'UNKNOWN').upper()
            name = result.get('name', 'unknown')

            entry = {
                'name': name,
                'type': stmt_type,
                'language': result.get('language', 'SQL'),
                'analysis_success': result.get('analysis_success', False),
                'analyzed_at': result.get('analyzed_at'),
                'llm_provider': result.get('llm_provider'),
                'lineage_analysis': result.get('lineage_analysis', {}),
                'table_context_used': result.get('table_context_used', []),
                'original_sql': result.get('original_sql', '')
            }

            if stmt_type in ['PROCEDURE', 'STORED_PROCEDURE', 'EXTERNAL_PROCEDURE']:
                procedures[name] = entry
            elif stmt_type == 'MACRO':
                macros[name] = entry
            else:
                functions[name] = entry

        total = len(all_llm_results)
        successful = sum(1 for r in all_llm_results if r.get('analysis_success', False))

        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_type": "teradata_metadata",
                "host": self.host,
                "database": self.database or "(user default)",
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
                "macros_count": len(macros)
            },
            "procedures": procedures,
            "functions": functions,
            "macros": macros
        }

    def _build_combined_summary(self, statement_report: Dict, procedure_report: Dict) -> Dict:
        """Build a combined summary report."""
        s = statement_report.get('summary', {})
        p = procedure_report.get('summary', {})
        metadata_summary = self.metadata.get('summary', {})

        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_type": "teradata_connection",
                "host": self.host,
                "database": self.database or "(user default)",
                "dialect": self.dialect,
                "analysis_method": "Metadata-Based with LLM-Enhanced Procedure Analysis"
            },
            "database_summary": {
                "extraction_timestamp": metadata_summary.get('extraction_timestamp'),
                "total_tables": metadata_summary.get('table_count', 0),
                "total_views": metadata_summary.get('view_count', 0),
                "total_procedures": metadata_summary.get('procedure_count', 0),
                "total_functions": metadata_summary.get('function_count', 0),
                "total_macros": metadata_summary.get('macro_count', 0),
                "total_triggers": metadata_summary.get('trigger_count', 0),
                "total_columns": metadata_summary.get('column_count', 0),
                "query_history_count": metadata_summary.get('query_history_count', 0)
            },
            "analysis_summary": {
                "views_analyzed": s.get('total_views', 0),
                "query_history_analyzed": s.get('total_queries', 0),
                "procedures_analyzed": p.get('procedures_count', 0),
                "functions_analyzed": p.get('functions_count', 0),
                "macros_analyzed": p.get('macros_count', 0),
                "llm_success_rate": p.get('success_rate', 'N/A')
            },
            "teradata_features": {
                "volatile_tables_supported": True,
                "macros_supported": True,
                "qualify_clause_supported": True,
                "sample_clause_supported": True,
                "collect_statistics_supported": True,
                "multiset_tables_supported": True
            }
        }


def main():
    """Main entry point with command-line interface."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Teradata Metadata-Based Lineage Analyzer with LLM Enhancement'
    )

    # Teradata connection arguments
    parser.add_argument('--host', '-H', required=True, help='Teradata server hostname or IP')
    parser.add_argument('--user', '-u', required=True, help='Database username')
    parser.add_argument('--password', '-p', default='', help='Database password')
    parser.add_argument('--database', '-db', default='', help='Default database (optional)')
    parser.add_argument('--logmech', default='TD2', help='Authentication mechanism (default: TD2)')
    parser.add_argument('--encryptdata', default='ON', help='Data encryption (default: ON)')

    # Output configuration
    parser.add_argument('--output', '-o', default='./lineage_output', help='Output directory')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    # LLM configuration
    parser.add_argument('--ollama-url', default='http://localhost:11434', help='Ollama API URL')
    parser.add_argument('--ollama-model', default='qwen2.5-coder:14b', help='Ollama model name')
    parser.add_argument('--openai-key', help='OpenAI API key')
    parser.add_argument('--openai-model', default='gpt-4o-mini', help='OpenAI model name')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size')
    parser.add_argument('--timeout', type=int, default=300, help='Request timeout')

    # Metadata options
    parser.add_argument('--metadata-file', help='Path to pre-extracted metadata JSON file')

    args = parser.parse_args()

    # Prompt for password if not provided
    if not args.password and not args.metadata_file:
        import getpass
        args.password = getpass.getpass(f"Enter password for {args.user}@{args.host}: ")

    # Run analysis
    orchestrator = MetadataLineageOrchestrator(
        host=args.host,
        user=args.user,
        password=args.password,
        database=args.database,
        logmech=args.logmech,
        encryptdata=args.encryptdata,
        output_directory=args.output,
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
        stats = results['statistics']
        print(f"\nStatistics:")
        print(f"  Tables in database: {stats['total_tables']}")
        print(f"  Views analyzed: {stats['total_views']}")
        print(f"  Query history analyzed: {stats['total_query_history']}")
        print(f"  Procedures: {stats['total_procedures']}")
        print(f"  Functions: {stats['total_functions']}")
        print(f"  Macros: {stats['total_macros']}")
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
