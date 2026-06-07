"""
Re-export postgres_json_builder from conn directory for easier imports.
This allows using:
    from .postgres_json_builder import PostgreSQLLineageJSONBuilder
instead of:
    from .conn.postgres_json_builder import PostgreSQLLineageJSONBuilder
"""

from .conn.postgres_json_builder import PostgreSQLLineageJSONBuilder

__all__ = ['PostgreSQLLineageJSONBuilder']
