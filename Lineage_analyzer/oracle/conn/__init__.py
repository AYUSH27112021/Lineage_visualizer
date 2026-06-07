"""
Oracle Lineage Analysis Package

This package provides comprehensive lineage analysis for Oracle databases
using both metadata extraction and SQL parsing.

Main Components:
- enhanced_metadata_extractor: Extract metadata from Oracle database
- oracle_cleaner: Clean Oracle SQL files
- oracle_analyzer: Analyze Oracle SQL statements
- metadata_view_analyzer: Analyze views from metadata
- metadata_statement_builder: Build lineage reports
- metadata_lineage_main: Main orchestrator for metadata-based analysis

Oracle-Specific Features:
- PL/SQL packages and package bodies
- Hierarchical queries (CONNECT BY)
- PIVOT/UNPIVOT transformations
- MODEL clause
- Flashback queries
- Materialized views
- Database links
- Global temporary tables
"""

from .enhanced_metadata_extractor import (
    extract_enhanced_database_metadata,
    build_connection_url
)

from .oracle_cleaner import (
    OracleSQLCleaner,
    clean_oracle_sql_directory
)

from .oracle_analyzer import (
    EnhancedSQLAnalyzer,
    ColumnLineage,
    StatementLineage
)

from .metadata_view_analyzer import (
    MetadataViewAnalyzer,
    ViewLineage
)

from .metadata_statement_builder import (
    MetadataStatementBuilder,
    ColumnInfo,
    TableInfo,
    PackageInfo
)

from .metadata_lineage_main import (
    MetadataLineageOrchestrator
)

__all__ = [
    # Metadata extraction
    'extract_enhanced_database_metadata',
    'build_connection_url',

    # SQL cleaning
    'OracleSQLCleaner',
    'clean_oracle_sql_directory',

    # SQL analysis
    'EnhancedSQLAnalyzer',
    'ColumnLineage',
    'StatementLineage',

    # Metadata-based analysis
    'MetadataViewAnalyzer',
    'ViewLineage',

    # Report building
    'MetadataStatementBuilder',
    'ColumnInfo',
    'TableInfo',
    'PackageInfo',

    # Main orchestrator
    'MetadataLineageOrchestrator',
]

__version__ = '1.0.0'
