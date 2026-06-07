"""
Re-export snowflake_analyzer from conn directory for easier imports.
This allows using:
    from .snowflake_analyzer import EnhancedSQLAnalyzer
instead of:
    from .conn.snowflake_analyzer import EnhancedSQLAnalyzer
"""

from .conn.snowflake_analyzer import EnhancedSQLAnalyzer

__all__ = ['EnhancedSQLAnalyzer']
