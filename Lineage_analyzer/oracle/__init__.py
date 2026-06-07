"""
Oracle Lineage Analyzer Package

This package provides comprehensive lineage analysis for Oracle databases.
Supports both file-based SQL analysis and metadata-based analysis.
"""

__version__ = "1.0.0"

# Re-export main components for easier imports
from .oracle_analyzer import EnhancedSQLAnalyzer
from .oracle_cleaner import OracleSQLCleaner
from .json_builder import EnhancedLineageJSONBuilder
from .enhanced_json_builder import EnhancedProcedureJSONBuilder

__all__ = [
    'EnhancedSQLAnalyzer',
    'OracleSQLCleaner',
    'EnhancedLineageJSONBuilder',
    'EnhancedProcedureJSONBuilder',
]
