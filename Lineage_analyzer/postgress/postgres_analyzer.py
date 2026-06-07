"""
Re-export postgres_analyzer from conn directory for easier imports.
This allows using:
    from .postgres_analyzer import PostgreSQLAnalyzer
instead of:
    from .conn.postgres_analyzer import PostgreSQLAnalyzer
"""

from .conn.postgres_analyzer import PostgreSQLAnalyzer, ColumnLineage, StatementLineage

__all__ = ['PostgreSQLAnalyzer', 'ColumnLineage', 'StatementLineage']
