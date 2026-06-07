"""
Metadata-Based T-SQL Lineage Analyzer Package

This package provides lineage analysis using database connection metadata
instead of SQL files. It supports:

1. Extracting metadata from SQL Server via enhanced_metadata_extractor
2. Analyzing views and query history with traditional parsing (sqlglot)
3. Analyzing procedures, functions, and triggers with LLM (Ollama/OpenAI)
4. Producing output compatible with existing frontend

Main Components:
- MetadataLineageOrchestrator: Main entry point for analysis
- MetadataViewAnalyzer: Traditional parsing for views/queries
- MetadataStatementBuilder: Builds lineage reports from view analysis
- enhanced_metadata_extractor: Extracts metadata from SQL Server
- enhanced_procedure_analyzer: LLM-based procedure analysis
"""

from .metadata_lineage_main import MetadataLineageOrchestrator
from .metadata_view_analyzer import MetadataViewAnalyzer
from .metadata_statement_builder import MetadataStatementBuilder

# Re-export from original modules (if they exist in the same package)
try:
    from .enhanced_metadata_extractor import (
        extract_enhanced_database_metadata,
        build_connection_url
    )
except ImportError:
    pass

try:
    from .enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer
except ImportError:
    pass

try:
    from .enhanced_json_builder import EnhancedProcedureJSONBuilder
except ImportError:
    pass

__all__ = [
    'MetadataLineageOrchestrator',
    'MetadataViewAnalyzer', 
    'MetadataStatementBuilder',
    'extract_enhanced_database_metadata',
    'build_connection_url',
    'EnhancedLLMLineageAnalyzer',
    'EnhancedProcedureJSONBuilder',
]

__version__ = '2.0.0'
__author__ = 'T-SQL Lineage Analyzer'
