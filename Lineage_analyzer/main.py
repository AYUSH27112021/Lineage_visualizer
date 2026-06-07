"""
Unified entry point for lineage analysis across SQL dialects.

Routes to the appropriate dialect-specific driver (currently T-SQL) while
preserving the same CLI options as the T-SQL tool.
"""

import sys
from pathlib import Path
import runpy


def _run_module(entry_module: str, fake_script: Path, forwarded_argv: list[str]) -> int:
    """Run a module as __main__ with controlled argv and sys.path.

    This uses the fully-qualified package path to preserve relative imports
    inside the target module (e.g., `.tsql_cleaner`).
    """
    project_root = Path(__file__).resolve().parents[1]

    old_argv = list(sys.argv)
    sys.argv = forwarded_argv

    # Ensure project root is importable so `Lineage_analyzer.*` resolves
    added_path = False
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
        added_path = True

    try:
        runpy.run_module(entry_module, run_name="__main__")
        return 0
    except SystemExit as e:
        return int(e.code) if e.code is not None else 0
    finally:
        sys.argv = old_argv
        if added_path:
            try:
                sys.path.remove(str(project_root))
            except ValueError:
                pass


def run_tsql(sql_directory: str, output: str, dialect: str, max_files: int | None, debug: bool, openai_key: str | None = None) -> int:
    """Execute the T-SQL analyzer entrypoint via package-qualified module path."""
    tsql_entry = Path(__file__).parent / "tsql" / "tsql_main.py"
    forwarded_argv: list[str] = [str(tsql_entry), sql_directory, "--output", output, "--dialect", dialect]
    if max_files is not None:
        forwarded_argv += ["--max-files", str(max_files)]
    if debug:
        forwarded_argv += ["--debug"]
    if openai_key:
        forwarded_argv += ["--openai-key", openai_key]

    return _run_module("Lineage_analyzer.tsql.tsql_main", tsql_entry, forwarded_argv)


def run_postgres(sql_directory: str, output: str, dialect: str, max_files: int | None, debug: bool) -> int:
    """Execute the PostgreSQL analyzer entrypoint via package-qualified module path."""
    pg_entry = Path(__file__).parent / "postgress" / "postgres_main.py"
    forwarded_argv: list[str] = [str(pg_entry), sql_directory, "--output", output, "--dialect", dialect]
    if max_files is not None:
        forwarded_argv += ["--max-files", str(max_files)]
    if debug:
        forwarded_argv += ["--debug"]

    return _run_module("Lineage_analyzer.postgress.postgres_main", pg_entry, forwarded_argv)


def run_oracle(
    sql_directory: str,
    output: str,
    dialect: str,
    max_files: int | None,
    debug: bool,
    openai_key: str | None = None,
) -> int:
    """Execute the Oracle analyzer with LLM-based procedure analysis."""
    from .oracle.oracle_main import LineageOrchestrator

    orchestrator = LineageOrchestrator(
        sql_directory=sql_directory,
        output_directory=output,
        dialect=dialect,
        debug=debug,
        openai_api_key=openai_key,
    )

    orchestrator.run_full_analysis(max_files=max_files)
    return 0


def run_teradata(
    sql_directory: str,
    output: str,
    dialect: str,
    max_files: int | None,
    debug: bool,
    openai_key: str | None = None,
) -> int:
    """Execute the Teradata analyzer entrypoint via package-qualified module path."""
    teradata_entry = Path(__file__).parent / "teradata" / "teradata_main.py"
    forwarded_argv: list[str] = [str(teradata_entry), sql_directory, "--output", output, "--dialect", dialect]
    if max_files is not None:
        forwarded_argv += ["--max-files", str(max_files)]
    if debug:
        forwarded_argv += ["--debug"]
    if openai_key:
        forwarded_argv += ["--openai-key", openai_key]

    return _run_module("Lineage_analyzer.teradata.teradata_main", teradata_entry, forwarded_argv)


def run_snowflake(
    sql_directory: str,
    output: str,
    dialect: str,
    max_files: int | None,
    debug: bool,
    openai_key: str | None = None,
) -> int:
    """Execute the Snowflake analyzer entrypoint via package-qualified module path."""
    snowflake_entry = Path(__file__).parent / "snowflake" / "snowflake_main.py"
    forwarded_argv: list[str] = [str(snowflake_entry), sql_directory, "--output", output, "--dialect", dialect]
    if max_files is not None:
        forwarded_argv += ["--max-files", str(max_files)]
    if debug:
        forwarded_argv += ["--debug"]
    if openai_key:
        forwarded_argv += ["--openai-key", openai_key]

    return _run_module("Lineage_analyzer.snowflake.snowflake_main", snowflake_entry, forwarded_argv)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Database Lineage Analyzer (multi-dialect entry)")
    parser.add_argument("sql_directory", help="Directory containing SQL files")
    parser.add_argument("--output", "-o", default="./lineage_output", help="Output directory for reports")
    parser.add_argument("--dialect", "-d", default="tsql", help="SQL dialect (e.g., tsql)")
    parser.add_argument("--max-files", "-m", type=int, help="Maximum number of files to process")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--openai-key", help="OpenAI API key for LLM-based procedure analysis")

    args = parser.parse_args()

    # Validate input directory
    if not Path(args.sql_directory).exists():
        print(f"Error: Directory '{args.sql_directory}' does not exist")
        return 1

    dialect = str(args.dialect).strip().lower()

    # Route based on dialect
    if dialect in {"tsql", "mssql", "mysql", "sqlite"}:
        return run_tsql(
            sql_directory=args.sql_directory,
            output=args.output,
            dialect=args.dialect,
            max_files=args.max_files,
            debug=args.debug,
        )
    if dialect in {"postgres", "postgresql", "pgsql", "postgress"}:
        return run_postgres(
            sql_directory=args.sql_directory,
            output=args.output,
            dialect=args.dialect,
            max_files=args.max_files,
            debug=args.debug,
        )
    if dialect in {"oracle"}:
        return run_oracle(
            sql_directory=args.sql_directory,
            output=args.output,
            dialect=args.dialect,
            max_files=args.max_files,
            debug=args.debug,
            openai_key=getattr(args, 'openai_key', None),
        )
    if dialect in {"teradata"}:
        return run_teradata(
            sql_directory=args.sql_directory,
            output=args.output,
            dialect=args.dialect,
            max_files=args.max_files,
            debug=args.debug,
        )
    if dialect in {"snowflake"}:
        return run_snowflake(
            sql_directory=args.sql_directory,
            output=args.output,
            dialect=args.dialect,
            max_files=args.max_files,
            debug=args.debug,
        )

    print(f"Error: Dialect '{args.dialect}' is not supported yet.")
    print("Supported dialects: tsql, postgres, oracle, teradata, snowflake")
    return 1


if __name__ == "__main__":
    sys.exit(main())

