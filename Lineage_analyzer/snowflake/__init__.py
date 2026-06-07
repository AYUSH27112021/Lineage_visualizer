"""
Snowflake Column-Level Lineage Analyzer Package

This package provides tools for extracting and analyzing column-level data lineage
from Snowflake databases. It supports:

- Metadata extraction from Snowflake INFORMATION_SCHEMA
- SQL parsing with Snowflake dialect support
- View and query history analysis
- LLM-based procedure and function analysis
- JSON report generation for visualization

Snowflake-specific features:
- Variant/JSON column access (column:path::TYPE)
- LATERAL FLATTEN for array/object expansion
- Time Travel queries (AT/BEFORE)
- Streams and Tasks
- Multi-language stored procedures (SQL, JavaScript, Python, Java, Scala)
- External browser authentication (SSO)

Usage:
    from snowflake import MetadataLineageOrchestrator

    orchestrator = MetadataLineageOrchestrator(
        account="your-account.snowflakecomputing.com",
        database="YOUR_DATABASE",
        username="your_username",
        password="your_password",
        warehouse="COMPUTE_WH",
        output_directory="./lineage_output",
        ollama_model="qwen2.5-coder:14b"
    )

    results = orchestrator.run_full_analysis()
"""

# Version
__version__ = "1.0.0"

# Core components
from .conn.enhanced_metadata_extractor import (
    extract_enhanced_database_metadata,
    build_connection_params,
    save_metadata_to_file
)

from .conn.snowflake_analyzer import (
    EnhancedSQLAnalyzer,
    ColumnLineage
)

from .conn.snowflake_cleaner import (
    EnhancedSQLCleaner,
    SQLBatch
)

from .conn.metadata_view_analyzer import (
    MetadataViewAnalyzer
)

from .conn.metadata_statement_builder import (
    MetadataStatementBuilder,
    ColumnInfo,
    TableInfo,
    CTEInfo
)

from .conn.enhanced_procedure_analyzer import (
    EnhancedLLMLineageAnalyzer
)

from .conn.json_builder import (
    EnhancedLineageJSONBuilder
)

from .conn.enhanced_json_builder import (
    EnhancedProcedureJSONBuilder
)

from .conn.metadata_lineage_main import (
    MetadataLineageOrchestrator
)

# Public API
__all__ = [
    # Version
    "__version__",

    # Metadata extraction
    "extract_enhanced_database_metadata",
    "build_connection_params",
    "save_metadata_to_file",

    # SQL analysis
    "EnhancedSQLAnalyzer",
    "ColumnLineage",

    # SQL cleaning
    "EnhancedSQLCleaner",
    "SQLBatch",

    # View analysis
    "MetadataViewAnalyzer",

    # Statement building
    "MetadataStatementBuilder",
    "ColumnInfo",
    "TableInfo",
    "CTEInfo",

    # Procedure analysis
    "EnhancedLLMLineageAnalyzer",

    # JSON building
    "EnhancedLineageJSONBuilder",
    "EnhancedProcedureJSONBuilder",

    # Main orchestrator
    "MetadataLineageOrchestrator",
]
