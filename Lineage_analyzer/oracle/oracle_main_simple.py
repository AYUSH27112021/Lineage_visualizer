"""
Oracle File-Based Lineage Analyzer - Main Entry Point

This module provides the main workflow for analyzing Oracle SQL files
and generating comprehensive lineage reports without requiring database connection.

Usage:
    python oracle_main.py --input-dir ./sql_files --output-dir ./lineage_output

    Or programmatically:
    from oracle_main import OracleFileLineageAnalyzer
    analyzer = OracleFileLineageAnalyzer(input_dir="./sql", output_dir="./output")
    analyzer.run()
"""

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
from datetime import datetime

# Import from conn directory
from .conn.oracle_cleaner import OracleSQLCleaner
from .conn.oracle_analyzer import EnhancedSQLAnalyzer
from .conn.json_builder import EnhancedLineageJSONBuilder


class OracleFileLineageAnalyzer:
    """
    Main orchestrator for file-based Oracle SQL lineage analysis.

    This class coordinates the entire workflow:
    1. File discovery and cleaning
    2. SQL parsing and analysis
    3. Lineage report generation
    """

    def __init__(
        self,
        input_dir: str,
        output_dir: str = "./lineage_output",
        file_pattern: str = "*.sql",
        dialect: str = "oracle",
        debug: bool = False
    ):
        """
        Initialize the analyzer.

        Args:
            input_dir: Directory containing Oracle SQL files
            output_dir: Directory for output files
            file_pattern: File pattern to match (default: *.sql)
            dialect: SQL dialect (default: oracle)
            debug: Enable debug output
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.file_pattern = file_pattern
        self.dialect = dialect
        self.debug = debug

        # Initialize components
        self.cleaner = OracleSQLCleaner(sql_directory=str(input_dir), debug=debug)
        self.analyzer = EnhancedSQLAnalyzer(dialect=dialect, debug=debug)
        self.builder = EnhancedLineageJSONBuilder(dialect, str(input_dir))

        # Statistics
        self.stats = {
            'files_found': 0,
            'files_processed': 0,
            'files_failed': 0,
            'total_statements': 0,
            'successful_parses': 0,
            'parse_errors': 0
        }

    def discover_sql_files(self) -> List[Path]:
        """Discover SQL files in input directory."""
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {self.input_dir}")

        files = list(self.input_dir.glob(f"**/{self.file_pattern}"))
        self.stats['files_found'] = len(files)

        if self.debug:
            print(f"\n{'='*80}")
            print(f"ORACLE FILE-BASED LINEAGE ANALYSIS")
            print(f"{'='*80}")
            print(f"Input Directory: {self.input_dir}")
            print(f"Files Found: {len(files)}")
            print(f"{'='*80}\n")

        return files

    def process_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Process a single SQL file.

        Args:
            file_path: Path to SQL file

        Returns:
            List of analysis results (one per statement category)
        """
        try:
            if self.debug:
                print(f"Processing: {file_path.name}")

            # Step 1: Clean the SQL file (returns structured dict)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            cleaned = self.cleaner.clean_sql(content)

            # Step 2: Analyze statements
            results = []

            # Analyze regular statements
            if cleaned.get('statements'):
                stmt_result = self.analyzer.analyze_file(str(file_path), cleaned['statements'])
                results.append(stmt_result)
                self.stats['total_statements'] += len(cleaned['statements'])

            # Analyze views (add to results so they appear in lineage - like Snowflake fix)
            if cleaned.get('views'):
                for view in cleaned['views']:
                    view_result = self.analyzer.analyze_file(
                        str(file_path),
                        [view['content']]
                    )
                    results.append(view_result)
                self.stats['total_views'] = self.stats.get('total_views', 0) + len(cleaned['views'])

            self.stats['files_processed'] += 1

            if self.debug:
                print(f"  ✓ Analyzed {len(cleaned.get('statements', []))} statements, "
                      f"{len(cleaned.get('views', []))} views")

            return results

        except Exception as e:
            self.stats['files_failed'] += 1
            if self.debug:
                print(f"  ✗ Error processing {file_path.name}: {str(e)}")
            return []

    def run(self) -> Dict[str, Any]:
        """
        Execute the full lineage analysis workflow.

        Returns:
            Complete lineage report
        """
        start_time = datetime.now()

        # Step 1: Discover files
        sql_files = self.discover_sql_files()

        if not sql_files:
            print(f"No SQL files found in {self.input_dir}")
            return {}

        # Step 2: Process each file
        all_results = []
        for file_path in sql_files:
            results = self.process_file(file_path)
            if results:
                all_results.extend(results)  # Extend, not append, since process_file returns a list

        # Step 3: Build lineage report
        if self.debug:
            print(f"\n{'='*80}")
            print("BUILDING LINEAGE REPORT")
            print(f"{'='*80}")

        report = self.builder.build_lineage_report(all_results)

        # Add execution statistics
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        report['execution_info'] = {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'execution_time_seconds': execution_time,
            'input_directory': str(self.input_dir),
            'files_found': self.stats['files_found'],
            'files_processed': self.stats['files_processed'],
            'files_failed': self.stats['files_failed']
        }

        # Step 4: Save report
        self.output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"statement_lineage_{timestamp}.json"

        self.builder.save_report(report, str(output_file))

        # Print summary
        if self.debug:
            self._print_summary(report, output_file)

        return report

    def _print_summary(self, report: Dict[str, Any], output_file: Path):
        """Print analysis summary."""
        summary = report.get('summary', {})

        print(f"\n{'='*80}")
        print("ANALYSIS SUMMARY")
        print(f"{'='*80}")
        print(f"Files Processed:     {self.stats['files_processed']}/{self.stats['files_found']}")
        print(f"Total Tables:        {summary.get('total_tables', 0)}")
        print(f"Total Columns:       {summary.get('total_columns', 0)}")
        print(f"Total Dependencies:  {summary.get('total_dependencies', 0)}")
        print(f"Global Temp Tables:  {summary.get('global_temp_tables', 0)}")
        print(f"CTEs:                {summary.get('ctes', 0)}")
        print(f"Parse Errors:        {summary.get('parse_errors', 0)}")
        print(f"\nOutput File:         {output_file}")
        print(f"{'='*80}\n")


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Oracle File-Based Lineage Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze all SQL files in a directory
  python oracle_main.py --input-dir ./sql_files

  # Specify output directory
  python oracle_main.py --input-dir ./sql --output-dir ./lineage

  # Enable debug mode
  python oracle_main.py --input-dir ./sql --debug

  # Custom file pattern
  python oracle_main.py --input-dir ./sql --pattern "*.pls"
        """
    )

    parser.add_argument(
        '--input-dir',
        required=True,
        help='Directory containing Oracle SQL files'
    )

    parser.add_argument(
        '--output-dir',
        default='./lineage_output',
        help='Output directory for lineage reports (default: ./lineage_output)'
    )

    parser.add_argument(
        '--pattern',
        default='*.sql',
        help='File pattern to match (default: *.sql)'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output'
    )

    args = parser.parse_args()

    try:
        analyzer = OracleFileLineageAnalyzer(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            file_pattern=args.pattern,
            debug=args.debug
        )

        analyzer.run()

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
