"""
Metadata-Based Lineage Analysis Orchestrator for Snowflake
Uses database connection via enhanced_metadata_extractor instead of SQL files.

This module:
1. Extracts metadata from Snowflake database using enhanced_metadata_extractor
2. Separates tabular SQL (views, query history) from executable SQL (procedures, functions)
3. Uses MetadataViewAnalyzer for tabular SQL
4. Uses EnhancedLLMLineageAnalyzer for executable SQL
5. Produces output compatible with frontend visualization
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
    build_connection_params
)

# Import SQL analysis components
from .snowflake_analyzer import EnhancedSQLAnalyzer

# Import LLM-based procedure analyzer
from .enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer

# Import the metadata-based builders
from .metadata_view_analyzer import MetadataViewAnalyzer
from .metadata_statement_builder import MetadataStatementBuilder


class MetadataLineageOrchestrator:
    """
    Main orchestrator for metadata-based lineage analysis in Snowflake.

    Uses database connection instead of SQL files:
    1. Extracts metadata via enhanced_metadata_extractor
    2. Analyzes views and query history with traditional parsing
    3. Analyzes procedures/functions with LLM
    4. Outputs in same format as file-based analysis
    """

    def __init__(
        self,
        # Snowflake connection parameters
        account: str,
        database: str,
        username: str,
        password: str = "",
        warehouse: str = "",
        role: str = "",
        authenticator: str = "externalbrowser",
        schema_filter: str = "",
        # Output configuration
        output_directory: str = "./lineage_output",
        dialect: str = "snowflake",
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
        Initialize the metadata-based lineage orchestrator.

        Args:
            account: Snowflake account identifier
            database: Database name
            username: Login username
            password: Login password
            warehouse: Compute warehouse name
            role: Role to use
            authenticator: Authentication method
            schema_filter: Optional schema name to filter
            output_directory: Output directory for reports
            dialect: SQL dialect (default: snowflake)
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
        # Snowflake connection params
        self.account = account
        self.database = database
        self.username = username
        self.password = password
        self.warehouse = warehouse
        self.role = role
        self.authenticator = authenticator
        self.schema_filter = schema_filter

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

        # LLM analyzed results
        self.llm_analyzed_procedures = []
        self.llm_analyzed_functions = []

        # Statistics
        self.stats = defaultdict(int)

    def extract_metadata(self, force_refresh: bool = False) -> Dict:
        """
        Extract metadata from Snowflake database connection.

        Args:
            force_refresh: Force re-extraction even if metadata exists

        Returns:
            Extracted metadata dictionary
        """
        if self.metadata and not force_refresh:
            print(f"Using existing metadata ({len(self.metadata.get('tables', []))} tables)")
            return self.metadata

        print("\n" + "="*80)
        print("EXTRACTING SNOWFLAKE DATABASE METADATA")
        print("="*80)
        print(f"Account: {self.account}")
        print(f"Database: {self.database}")

        self.metadata, metadata_path = extract_enhanced_database_metadata(
            account=self.account,
            database=self.database,
            username=self.username,
            password=self.password,
            warehouse=self.warehouse,
            role=self.role,
            authenticator=self.authenticator,
            schema_filter=self.schema_filter,
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
        print(f"   Streams: {summary.get('stream_count', 0)}")
        print(f"   Tasks: {summary.get('task_count', 0)}")
        print(f"   Query History: {summary.get('query_history_count', 0)}")

        return self.metadata

    def run_full_analysis(self) -> Dict:
        """
        Run complete lineage analysis pipeline using database metadata.

        Returns:
            Complete analysis results dictionary
        """
        print("\n" + "="*80)
        print("SNOWFLAKE METADATA-BASED LINEAGE ANALYSIS PIPELINE")
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
        print(f"   ✓ Executable SQL (procedures, functions): {len(executable_sql)}")

        # Step 3: Analyze tabular SQL
        print("\n[3/6] Analyzing tabular SQL components...")
        self._analyze_tabular_sql(tabular_sql)
        print(f"   ✓ Analyzed {len(self.view_results)} views")
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
                if stmt_type in ['PROCEDURE', 'STORED_PROCEDURE']:
                    self.llm_analyzed_procedures.append(result)
                elif 'FUNCTION' in stmt_type or stmt_type in ['UDF', 'UDTF']:
                    self.llm_analyzed_functions.append(result)
                else:
                    print(f"   ⚠ Warning: Unknown statement type '{stmt_type}' for {result.get('name', 'unknown')}")

            llm_analyzer.print_statistics()
        else:
            print("   ⚠ No executable SQL found to analyze")

        # Step 6: Build output reports
        print("\n[6/6] Building lineage reports...")

        # Build statement lineage JSON
        statement_report = self._build_statement_report()
        self._augment_statement_report_with_llm(statement_report)
        statement_output = self.output_directory / f"statement_lineage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(statement_output, 'w', encoding='utf-8') as f:
            json.dump(statement_report, f, indent=2, ensure_ascii=False, default=str)
        print(f"   ✓ Statement lineage saved to: {statement_output.name}")

        # Build procedure lineage JSON
        all_llm_results = self.llm_analyzed_procedures + self.llm_analyzed_functions
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
        print(f"\nMetadata source: Snowflake ({self.account}/{self.database})")
        print(f"\nOutput files:")
        print(f"  1. Statement lineage: {statement_output.name}")
        print(f"  2. Procedure lineage: {procedure_output.name}")
        print(f"  3. Combined summary:  {summary_output.name}")
        if self.metadata_file_path:
            print(f"  4. Metadata cache:    {self.metadata_file_path}")
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
                'llm_success_rate': self._calculate_llm_success_rate()
            }
        }

    def _separate_sql_components(self) -> Tuple[List[Dict], List[Dict]]:
        """Separate metadata into tabular SQL and executable SQL."""
        tabular_sql = []
        executable_sql = []

        # Views go to tabular SQL
        for view in self.metadata.get('views', []):
            if view.get('definition'):
                tabular_sql.append({
                    'type': 'VIEW',
                    'name': f"{view.get('schema_name', 'PUBLIC')}.{view.get('view_name')}",
                    'schema_name': view.get('schema_name', 'PUBLIC'),
                    'object_name': view.get('view_name'),
                    'definition': view.get('definition'),
                    'original_sql': view.get('definition'),
                    'modified_sql': view.get('definition'),
                    'create_date': view.get('create_date'),
                    'modify_date': view.get('modify_date'),
                    'description': view.get('description'),
                    'is_secure': view.get('is_secure'),
                    'is_materialized': view.get('is_materialized')
                })

        # Query history goes to tabular SQL
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
                    'avg_duration_ms': query.get('avg_duration_ms'),
                    'last_execution_time': query.get('last_execution_time')
                })

        # Procedures go to executable SQL
        for proc in self.metadata.get('procedures', []):
            if proc.get('definition'):
                executable_sql.append({
                    'type': 'PROCEDURE',
                    'name': f"{proc.get('schema_name', 'PUBLIC')}.{proc.get('procedure_name')}",
                    'schema_name': proc.get('schema_name', 'PUBLIC'),
                    'object_name': proc.get('procedure_name'),
                    'definition': proc.get('definition'),
                    'original_sql': proc.get('definition'),
                    'modified_sql': proc.get('definition'),
                    'language': proc.get('language', 'SQL'),
                    'argument_signature': proc.get('argument_signature'),
                    'create_date': proc.get('create_date'),
                    'modify_date': proc.get('modify_date'),
                    'description': proc.get('description')
                })

        # Functions go to executable SQL
        for func in self.metadata.get('functions', []):
            if func.get('definition'):
                executable_sql.append({
                    'type': 'FUNCTION',
                    'name': f"{func.get('schema_name', 'PUBLIC')}.{func.get('function_name')}",
                    'schema_name': func.get('schema_name', 'PUBLIC'),
                    'object_name': func.get('function_name'),
                    'definition': func.get('definition'),
                    'original_sql': func.get('definition'),
                    'modified_sql': func.get('definition'),
                    'language': func.get('language', 'SQL'),
                    'return_type': func.get('return_type'),
                    'argument_signature': func.get('argument_signature'),
                    'is_aggregate': func.get('is_aggregate'),
                    'create_date': func.get('create_date'),
                    'modify_date': func.get('modify_date'),
                    'description': func.get('description')
                })

        # If nothing was discovered, synthesize simple SELECT statements from base tables
        if not tabular_sql and not executable_sql:
            tables = self.metadata.get('tables', [])
            if tables:
                print("   ⚠ No view/procedure/query history definitions found. Generating synthetic table statements for visualization.")
                max_tables = 250
                for table in tables[:max_tables]:
                    schema = table.get('schema', 'PUBLIC')
                    name = table.get('name')
                    if not name:
                        continue
                    qualified_name = f"{schema}.{name}"
                    synthetic_sql = f"SELECT * FROM {qualified_name};"
                    tabular_sql.append({
                        'type': 'TABLE_METADATA',
                        'name': qualified_name,
                        'schema_name': schema,
                        'object_name': name,
                        'definition': synthetic_sql,
                        'original_sql': synthetic_sql,
                        'modified_sql': synthetic_sql,
                        'description': table.get('description'),
                        'generated_from_metadata': True
                    })
                if len(tables) > max_tables:
                    print(f"     (Showing first {max_tables} tables out of {len(tables)} for visualization)")

        return tabular_sql, executable_sql

    def _analyze_tabular_sql(self, tabular_sql: List[Dict]):
        """Analyze tabular SQL using traditional parsing."""
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
                result = view_analyzer.analyze_sql(
                    sql=definition,
                    name=item.get('name'),
                    sql_type=sql_type
                )

                result['metadata'] = {
                    'schema_name': item.get('schema_name'),
                    'object_name': item.get('object_name'),
                    'create_date': item.get('create_date'),
                    'modify_date': item.get('modify_date'),
                    'description': item.get('description')
                }

                if sql_type == 'QUERY_HISTORY':
                    result['query_stats'] = {
                        'query_id': item.get('query_id'),
                        'query_type': item.get('query_type'),
                        'avg_duration_ms': item.get('avg_duration_ms'),
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
        total = len(self.llm_analyzed_procedures) + len(self.llm_analyzed_functions)
        if total == 0:
            return "N/A"

        successful = sum(
            1 for result in (self.llm_analyzed_procedures + self.llm_analyzed_functions)
            if result.get('analysis_success', False)
        )

        return f"{(successful / total * 100):.1f}%"

    def _build_statement_report(self) -> Dict:
        """Build statement lineage report compatible with frontend expectations."""
        builder = MetadataStatementBuilder(
            dialect=self.dialect,
            database_name=self.database,
            metadata=self.metadata
        )

        statement_report = builder.build_lineage_report(
            self.view_results,
            self.query_history_results
        )

        metadata_summary = self.metadata.get('summary', {})

        # Ensure metadata block includes connection context for UI badges
        statement_report.setdefault("metadata", {})
        statement_report["metadata"].update({
            "generated_at": datetime.now().isoformat(),
            "source_type": "snowflake_metadata",
            "account": self.account,
            "database": self.database,
            "dialect": self.dialect
        })

        # Provide aggregated counts to match legacy format expectations
        summary = statement_report.setdefault("summary", {})
        summary.setdefault("total_tables", metadata_summary.get('table_count', 0))
        summary.setdefault("total_columns", metadata_summary.get('column_count', 0))
        summary.setdefault("total_views", len(self.view_results))
        summary.setdefault("total_queries", len(self.query_history_results))
        summary.setdefault(
            "successful_parses",
            sum(
                1
                for result in (self.view_results + self.query_history_results)
                if result.get('analysis_success')
            )
        )

        return statement_report

    def _build_procedure_report(self, all_llm_results: List[Dict]) -> Dict:
        """Build procedure lineage report."""
        procedures = {}
        functions = {}

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

            if stmt_type in ['PROCEDURE', 'STORED_PROCEDURE']:
                procedures[name] = entry
            else:
                functions[name] = entry

        total = len(all_llm_results)
        successful = sum(1 for r in all_llm_results if r.get('analysis_success', False))

        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_type": "snowflake_metadata",
                "account": self.account,
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
                "functions_count": len(functions)
            },
            "procedures": procedures,
            "functions": functions
        }

    def _normalize_table_key(self, name: Optional[str]) -> str:
        """Normalize a table identifier for matching."""
        if not name:
            return ""
        cleaned = (
            name.replace('"', "")
            .replace("[", "")
            .replace("]", "")
            .replace("`", "")
            .replace("\\", "")
            .strip()
        )
        return cleaned.lower()

    def _build_table_lookup(self, tables: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """Build lookup from normalized identifiers to canonical table keys."""
        lookup = {}
        for key in tables.keys():
            variants = {
                key,
                key.replace('"', "").replace("[", "").replace("]", ""),
            }

            parts = key.replace('"', "").replace("[", "").replace("]", "").split(".")
            if len(parts) >= 3:
                variants.add(".".join(parts[-2:]))  # schema.table
            if len(parts) >= 2:
                variants.add(parts[-1])  # table only

            for variant in variants:
                normalized = self._normalize_table_key(variant)
                if normalized and normalized not in lookup:
                    lookup[normalized] = key
        return lookup

    def _resolve_table_key(self, lookup: Dict[str, str], raw_name: Optional[str]) -> Optional[str]:
        """Resolve raw table name to existing metadata table key."""
        if not raw_name:
            return None

        cleaned = raw_name.replace('"', "").replace("[", "").replace("]", "")
        candidates = {raw_name, cleaned}

        parts = cleaned.split(".")
        if len(parts) >= 3:
            candidates.add(".".join(parts[-2:]))
        if len(parts) >= 2:
            candidates.add(parts[-1])

        for candidate in candidates:
            normalized = self._normalize_table_key(candidate)
            if normalized in lookup:
                return lookup[normalized]
        return None

    def _augment_statement_report_with_llm(self, statement_report: Dict):
        """
        Enrich statement report tables with dependencies discovered via LLM procedure analysis.
        """
        if not statement_report:
            return

        tables = statement_report.get("tables") or {}
        if not tables:
            return

        lookup = self._build_table_lookup(tables)
        updated_tables = set()

        for result in (self.llm_analyzed_procedures + self.llm_analyzed_functions):
            lineage = result.get("lineage_analysis") or {}
            if not lineage or "error" in lineage:
                continue

            target = lineage.get("target") or {}
            target_name = target.get("name")
            table_key = self._resolve_table_key(lookup, target_name)
            if not table_key:
                continue

            depends_on = set(tables.get(table_key, {}).get("depends_on", []))

            for dep in (lineage.get("dependencies") or {}).get("tables", []):
                resolved = self._resolve_table_key(lookup, dep) or dep
                if resolved:
                    depends_on.add(resolved)

            for source in lineage.get("source_tables") or []:
                src = source.get("table_list")
                resolved = self._resolve_table_key(lookup, src) or src
                if resolved:
                    depends_on.add(resolved)

            if depends_on:
                tables[table_key]["depends_on"] = sorted(depends_on)
                updated_tables.add(table_key)

        if updated_tables:
            summary = statement_report.setdefault("summary", {})
            summary["total_dependencies"] = sum(
                len(tables.get(tbl, {}).get("depends_on", [])) for tbl in tables
            )
            metadata_block = statement_report.setdefault("metadata", {})
            metadata_block["llm_dependency_enrichment"] = {
                "tables_updated": len(updated_tables),
                "timestamp": datetime.now().isoformat(),
            }

    def _build_combined_summary(self, statement_report: Dict, procedure_report: Dict) -> Dict:
        """Build a combined summary report."""
        s = statement_report.get('summary', {})
        p = procedure_report.get('summary', {})
        metadata_summary = self.metadata.get('summary', {})

        return {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "source_type": "snowflake_connection",
                "account": self.account,
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
                "total_streams": metadata_summary.get('stream_count', 0),
                "total_tasks": metadata_summary.get('task_count', 0),
                "total_columns": metadata_summary.get('column_count', 0),
                "query_history_count": metadata_summary.get('query_history_count', 0)
            },
            "analysis_summary": {
                "views_analyzed": s.get('total_views', 0),
                "query_history_analyzed": s.get('total_queries', 0),
                "procedures_analyzed": p.get('procedures_count', 0),
                "functions_analyzed": p.get('functions_count', 0),
                "llm_success_rate": p.get('success_rate', 'N/A')
            }
        }


def main():
    """Main entry point with command-line interface."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Snowflake Metadata-Based Lineage Analyzer with LLM Enhancement'
    )

    # Snowflake connection arguments
    parser.add_argument('--account', '-a', required=True, help='Snowflake account identifier')
    parser.add_argument('--database', '-db', required=True, help='Database name')
    parser.add_argument('--username', '-u', required=True, help='Login username')
    parser.add_argument('--password', '-p', default='', help='Login password')
    parser.add_argument('--warehouse', '-w', default='', help='Compute warehouse')
    parser.add_argument('--role', '-r', default='', help='Role to use')
    parser.add_argument('--authenticator', default='externalbrowser', help='Authentication method')

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

    # Run analysis
    orchestrator = MetadataLineageOrchestrator(
        account=args.account,
        database=args.database,
        username=args.username,
        password=args.password,
        warehouse=args.warehouse,
        role=args.role,
        authenticator=args.authenticator,
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
