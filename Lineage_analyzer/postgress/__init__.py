"""
PostgreSQL Column-Level Lineage Analyzer Package

This package provides tools for extracting and analyzing column-level data lineage
from PostgreSQL databases. It supports:

- SQL file-based analysis
- Direct database connection-based metadata extraction (future)
- SQL parsing with PostgreSQL dialect support
- View and query analysis
- Procedure and function analysis
- JSON report generation for visualization

PostgreSQL-specific features:
- Dollar-quoted strings ($$...$$ and $tag$...$tag$)
- CTEs (Common Table Expressions) with RECURSIVE support
- UPSERT (INSERT ... ON CONFLICT DO UPDATE)
- RETURNING clauses
- Array operations and unnest
- JSONB/JSON operations (-> and ->>)
- Window functions
- Materialized views
- Multi-language stored procedures (PL/pgSQL, PL/Python, etc.)
- Inheritance and partitioning

Usage:
    from postgress import LineageOrchestrator

    orchestrator = LineageOrchestrator(
        sql_directory="./sql_files",
        output_directory="./lineage_output",
        dialect="postgres",
        debug=False
    )

    results = orchestrator.run_full_analysis()
"""

# Version
__version__ = "1.0.0"

# Core components from conn directory
from .conn.postgres_analyzer import (
    PostgreSQLAnalyzer,
    ColumnLineage,
    StatementLineage
)

from .conn.postgres_cleaner import (
    PostgreSQLCleaner,
    SQLBatch
)

from .conn.postgres_procedure_analyzer import (
    PostgreSQLProcedureAnalyzer
)

from .conn.postgres_json_builder import (
    PostgreSQLLineageJSONBuilder
)

from .conn.postgres_procedure_json_builder import (
    PostgreSQLProcedureJSONBuilder
)

# Main orchestrator
from .postgres_main import (
    LineageOrchestrator
)

# Public API
__all__ = [
    # Version
    "__version__",

    # SQL analysis
    "PostgreSQLAnalyzer",
    "ColumnLineage",
    "StatementLineage",

    # SQL cleaning
    "PostgreSQLCleaner",
    "SQLBatch",

    # Procedure analysis
    "PostgreSQLProcedureAnalyzer",

    # JSON building
    "PostgreSQLLineageJSONBuilder",
    "PostgreSQLProcedureJSONBuilder",

    # Main orchestrator
    "LineageOrchestrator",
]
