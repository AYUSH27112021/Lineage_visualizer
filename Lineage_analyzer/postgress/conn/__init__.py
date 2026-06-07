"""
PostgreSQL Connection-Based Lineage Analysis Components

This package contains the core implementation files for PostgreSQL lineage analysis,
supporting both SQL file-based and direct database connection-based extraction.
"""

from .postgres_analyzer import PostgreSQLAnalyzer, ColumnLineage, StatementLineage
from .postgres_cleaner import PostgreSQLCleaner, SQLBatch
from .postgres_procedure_analyzer import PostgreSQLProcedureAnalyzer
from .postgres_json_builder import PostgreSQLLineageJSONBuilder
from .postgres_procedure_json_builder import PostgreSQLProcedureJSONBuilder

# Metadata-based analysis components (new) - optional imports
try:
    from .enhanced_metadata_extractor import extract_enhanced_database_metadata, build_connection_url
    from .metadata_view_analyzer import MetadataViewAnalyzer
    from .metadata_statement_builder import MetadataStatementBuilder
    from .enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer
    from .enhanced_json_builder import EnhancedProcedureJSONBuilder
    from .metadata_lineage_main import MetadataLineageOrchestrator
    _METADATA_AVAILABLE = True
except ImportError as e:
    # Metadata-based components require psycopg2/sqlalchemy
    _METADATA_AVAILABLE = False
    _METADATA_IMPORT_ERROR = str(e)
    # Set placeholders
    extract_enhanced_database_metadata = None
    build_connection_url = None
    MetadataViewAnalyzer = None
    MetadataStatementBuilder = None
    EnhancedLLMLineageAnalyzer = None
    EnhancedProcedureJSONBuilder = None
    MetadataLineageOrchestrator = None

__all__ = [
    # File-based Analyzer
    'PostgreSQLAnalyzer',
    'ColumnLineage',
    'StatementLineage',

    # Cleaner
    'PostgreSQLCleaner',
    'SQLBatch',

    # Procedure Analyzer
    'PostgreSQLProcedureAnalyzer',

    # JSON Builders
    'PostgreSQLLineageJSONBuilder',
    'PostgreSQLProcedureJSONBuilder',

    # Metadata-based components (NEW)
    'extract_enhanced_database_metadata',
    'build_connection_url',
    'MetadataViewAnalyzer',
    'MetadataStatementBuilder',
    'EnhancedLLMLineageAnalyzer',
    'EnhancedProcedureJSONBuilder',
    'MetadataLineageOrchestrator',
]
