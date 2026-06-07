"""
Metadata-Based Lineage Analysis Orchestrator for Oracle
Uses database connection via enhanced_metadata_extractor instead of SQL files.

This module:
1. Extracts metadata from Oracle database using enhanced_metadata_extractor
2. Separates tabular SQL (views, query history) from executable SQL (procedures, functions, packages)
3. Uses MetadataViewAnalyzer for tabular SQL
4. Uses LLM-based analyzer for PL/SQL procedures and functions (if available)
5. Produces output compatible with frontend visualization

Oracle-specific features:
- Packages (package specs and bodies)
- Materialized views and materialized view logs
- Global temporary tables
- Hierarchical queries (CONNECT BY)
- PIVOT/UNPIVOT transformations
- MODEL clauses
- Flashback queries
- Database links
- Object types
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

# Import the metadata extractor
try:
    from .enhanced_metadata_extractor import (
        extract_enhanced_database_metadata,
        build_connection_url
    )
except ImportError:
    extract_enhanced_database_metadata = None
    build_connection_url = None

# Import SQL analysis components
from .oracle_analyzer import EnhancedSQLAnalyzer

# Import the metadata-based builders
try:
    from .metadata_view_analyzer import MetadataViewAnalyzer
except ImportError:
    MetadataViewAnalyzer = None

try:
    from .metadata_statement_builder import MetadataStatementBuilder
except ImportError:
    MetadataStatementBuilder = None


class MetadataLineageOrchestrator:
    """
    Main orchestrator for metadata-based lineage analysis in Oracle.

    Uses database connection instead of SQL files:
    1. Extracts metadata via enhanced_metadata_extractor
    2. Analyzes views and query history with traditional parsing
    3. Analyzes procedures/functions/packages with LLM (optional)
    4. Outputs in same format as file-based analysis
    """

    def __init__(
        self,
        # Oracle connection parameters
        host: str,
        service_name: str,
        username: str,
        password: str,
        port: int = 1521,
        # Output configuration
        output_directory: str = "./lineage_output",
        dialect: str = "oracle",
        debug: bool = False,
        # LLM Configuration (optional)
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
        # Optional: Target schemas
        target_schemas: Optional[List[str]] = None,
    ):
        """
        Initialize the metadata-based lineage orchestrator for Oracle.

        Args:
            host: Oracle server hostname
            service_name: Oracle service name
            username: Database username
            password: Database password
            port: Oracle port (default: 1521)
            output_directory: Output directory for reports
            dialect: SQL dialect (default: oracle)
            debug: Enable debug output
            ollama_url: Ollama API URL for LLM analysis
            ollama_model: Ollama model name
            openai_api_key: OpenAI API key (alternative to Ollama)
            openai_model: OpenAI model name
            batch_size: Batch size for LLM processing
            timeout: Timeout for LLM requests
            preloaded_metadata: Pre-loaded metadata dictionary
            metadata_file_path: Path to pre-extracted metadata JSON file
            target_schemas: List of schemas to analyze (None = user's schema only)
        """
        self.host = host
        self.service_name = service_name
        self.username = username
        self.password = password
        self.port = port
        self.target_schemas = target_schemas

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

        # Metadata handling
        self.metadata: Optional[Dict] = preloaded_metadata
        self.metadata_file_path = metadata_file_path

        # Statistics
        self.stats = defaultdict(int)

    def extract_metadata(self) -> Dict:
        """
        Extract metadata from Oracle database.

        Returns:
            Metadata dictionary
        """
        if self.metadata:
            print("Using pre-loaded metadata")
            return self.metadata

        if self.metadata_file_path:
            print(f"Loading metadata from file: {self.metadata_file_path}")
            with open(self.metadata_file_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
            return self.metadata

        if not extract_enhanced_database_metadata:
            raise ImportError(
                "enhanced_metadata_extractor module not available. "
                "Please provide preloaded_metadata or metadata_file_path."
            )

        print(f"Extracting metadata from Oracle database: {self.service_name}")
        print(f"  Host: {self.host}:{self.port}")
        print(f"  User: {self.username}")
        if self.target_schemas:
            print(f"  Target schemas: {', '.join(self.target_schemas)}")

        metadata, metadata_file = extract_enhanced_database_metadata(
            host=self.host,
            service_name=self.service_name,
            username=self.username,
            password=self.password,
            port=self.port,
            output_dir=self.output_directory / "metadata_cache",
            target_schemas=self.target_schemas,
        )

        self.metadata = metadata
        self.metadata_file_path = str(metadata_file)

        print(f"\nMetadata extracted successfully:")
        print(f"  Tables: {metadata['summary']['table_count']}")
        print(f"  Views: {metadata['summary']['view_count']}")
        print(f"  Materialized Views: {metadata['summary'].get('materialized_view_count', 0)}")
        print(f"  Procedures: {metadata['summary']['procedure_count']}")
        print(f"  Functions: {metadata['summary']['function_count']}")
        print(f"  Packages: {metadata['summary'].get('package_count', 0)}")

        return metadata

    def analyze_views(self) -> List[Any]:
        """
        Analyze all views using MetadataViewAnalyzer.

        Returns:
            List of ViewLineage objects
        """
        if not MetadataViewAnalyzer:
            print("Warning: MetadataViewAnalyzer not available, skipping view analysis")
            return []

        print("\nAnalyzing views...")

        analyzer = MetadataViewAnalyzer(
            dialect=self.dialect,
            metadata=self.metadata,
            debug=self.debug
        )

        views = self.metadata.get('views', [])
        print(f"  Found {len(views)} views to analyze")

        view_lineages = analyzer.analyze_views(views)

        stats = analyzer.get_stats()
        print(f"  Successfully parsed: {stats.get('successful_parses', 0)}")
        print(f"  Parse errors: {stats.get('parse_errors', 0)}")

        self.stats['views_analyzed'] = len(view_lineages)
        self.stats['views_parse_success'] = stats.get('successful_parses', 0)
        self.stats['views_parse_errors'] = stats.get('parse_errors', 0)

        return view_lineages

    def analyze_materialized_views(self) -> List[Any]:
        """
        Analyze materialized views.

        Returns:
            List of ViewLineage objects
        """
        if not MetadataViewAnalyzer:
            print("Warning: MetadataViewAnalyzer not available, skipping materialized view analysis")
            return []

        print("\nAnalyzing materialized views...")

        analyzer = MetadataViewAnalyzer(
            dialect=self.dialect,
            metadata=self.metadata,
            debug=self.debug
        )

        mviews = self.metadata.get('materialized_views', [])
        print(f"  Found {len(mviews)} materialized views to analyze")

        # Convert materialized view metadata to view format
        mview_as_views = []
        for mv in mviews:
            mview_as_views.append({
                'view_name': mv.get('mview_name', ''),
                'owner': mv.get('owner', ''),
                'definition': mv.get('definition', ''),
            })

        mview_lineages = analyzer.analyze_views(mview_as_views)

        # Mark as materialized views
        for lineage in mview_lineages:
            lineage.sql_type = "MATERIALIZED_VIEW"

        stats = analyzer.get_stats()
        print(f"  Successfully parsed: {stats.get('successful_parses', 0)}")
        print(f"  Parse errors: {stats.get('parse_errors', 0)}")

        self.stats['mviews_analyzed'] = len(mview_lineages)

        return mview_lineages

    def analyze_procedures_and_functions(self) -> Dict[str, Any]:
        """
        Analyze procedures and functions using LLM (if available).

        Returns:
            Dictionary with procedure/function analysis results
        """
        print("\nAnalyzing procedures and functions...")

        procedures = self.metadata.get('procedures', [])
        functions = self.metadata.get('functions', [])

        print(f"  Found {len(procedures)} procedures")
        print(f"  Found {len(functions)} functions")

        # For now, we'll just collect basic information
        # Full LLM-based analysis would require the enhanced_procedure_analyzer module
        results = {
            'procedures': procedures,
            'functions': functions,
            'analyzed_count': 0,
            'note': 'Full PL/SQL lineage analysis requires LLM integration'
        }

        self.stats['procedures_found'] = len(procedures)
        self.stats['functions_found'] = len(functions)

        return results

    def analyze_packages(self) -> List[Dict]:
        """
        Analyze Oracle packages.

        Returns:
            List of package information
        """
        print("\nAnalyzing packages...")

        packages = self.metadata.get('packages', [])
        print(f"  Found {len(packages)} packages")

        self.stats['packages_found'] = len(packages)

        return packages

    def build_lineage_report(
        self,
        view_lineages: List[Any],
        mview_lineages: List[Any],
        procedure_results: Dict,
        packages: List[Dict]
    ) -> Dict:
        """
        Build comprehensive lineage report.

        Args:
            view_lineages: View lineage results
            mview_lineages: Materialized view lineage results
            procedure_results: Procedure/function analysis results
            packages: Package information

        Returns:
            Complete lineage report
        """
        if not MetadataStatementBuilder:
            print("Warning: MetadataStatementBuilder not available")
            return {}

        print("\nBuilding lineage report...")

        builder = MetadataStatementBuilder(
            dialect=self.dialect,
            database_name=self.service_name,
            metadata=self.metadata
        )

        # Add view lineages
        for lineage in view_lineages:
            builder.add_view_lineage(lineage)
            builder.stats['views_added'] += 1

        # Add materialized view lineages
        for lineage in mview_lineages:
            builder.add_view_lineage(lineage)
            builder.stats['mviews_added'] += 1

        # Add package information
        for package in packages:
            builder.add_package_info(package)

        # Build the report
        report = builder.build_report()

        print(f"  Report built successfully")
        print(f"  Total tables in report: {report['metadata']['total_tables']}")
        print(f"  Total columns in report: {report['metadata']['total_columns']}")

        return report

    def run(self) -> Dict:
        """
        Run complete metadata-based lineage analysis.

        Returns:
            Complete lineage report
        """
        print("=" * 70)
        print("Oracle Metadata-Based Lineage Analysis")
        print("=" * 70)

        # Step 1: Extract metadata
        self.extract_metadata()

        # Step 2: Analyze views
        view_lineages = self.analyze_views()

        # Step 3: Analyze materialized views
        mview_lineages = self.analyze_materialized_views()

        # Step 4: Analyze procedures and functions
        procedure_results = self.analyze_procedures_and_functions()

        # Step 5: Analyze packages
        packages = self.analyze_packages()

        # Step 6: Build lineage report
        report = self.build_lineage_report(
            view_lineages,
            mview_lineages,
            procedure_results,
            packages
        )

        # Step 7: Save report
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        report_file = self.output_directory / f"oracle_lineage_report_{timestamp}.json"

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str)

        print(f"\n{'=' * 70}")
        print(f"Lineage report saved to: {report_file}")
        print(f"{'=' * 70}")

        # Print summary statistics
        print("\nSummary Statistics:")
        print(f"  Views analyzed: {self.stats.get('views_analyzed', 0)}")
        print(f"  Materialized views analyzed: {self.stats.get('mviews_analyzed', 0)}")
        print(f"  Procedures found: {self.stats.get('procedures_found', 0)}")
        print(f"  Functions found: {self.stats.get('functions_found', 0)}")
        print(f"  Packages found: {self.stats.get('packages_found', 0)}")

        return report


def main():
    """Main entry point for command-line usage"""
    import argparse
    import getpass

    parser = argparse.ArgumentParser(
        description="Oracle Metadata-Based Lineage Analysis"
    )

    # Connection parameters
    parser.add_argument("--host", required=True, help="Oracle server hostname")
    parser.add_argument("--service-name", required=True, help="Oracle service name")
    parser.add_argument("--username", required=True, help="Database username")
    parser.add_argument("--password", help="Database password (prompted if not provided)")
    parser.add_argument("--port", type=int, default=1521, help="Oracle port (default: 1521)")

    # Target schemas
    parser.add_argument("--schemas", help="Comma-separated list of schemas to analyze")

    # Output configuration
    parser.add_argument(
        "--output-dir",
        default="./lineage_output",
        help="Output directory (default: ./lineage_output)"
    )

    # Optional: Use pre-extracted metadata
    parser.add_argument(
        "--metadata-file",
        help="Path to pre-extracted metadata JSON file"
    )

    # Debug mode
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    # Get password if not provided
    password = args.password
    if not password and not args.metadata_file:
        password = getpass.getpass("Database Password: ")

    # Parse target schemas
    target_schemas = None
    if args.schemas:
        target_schemas = [s.strip() for s in args.schemas.split(",")]

    # Create orchestrator
    orchestrator = MetadataLineageOrchestrator(
        host=args.host,
        service_name=args.service_name,
        username=args.username,
        password=password,
        port=args.port,
        output_directory=args.output_dir,
        metadata_file_path=args.metadata_file,
        target_schemas=target_schemas,
        debug=args.debug
    )

    # Run analysis
    try:
        report = orchestrator.run()
        print("\nAnalysis completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
