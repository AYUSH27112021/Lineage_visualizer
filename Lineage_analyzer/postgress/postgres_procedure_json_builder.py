"""
Re-export postgres_procedure_json_builder from conn directory for easier imports.
This allows using:
    from .postgres_procedure_json_builder import PostgreSQLProcedureJSONBuilder
instead of:
    from .conn.postgres_procedure_json_builder import PostgreSQLProcedureJSONBuilder
"""

from .conn.postgres_procedure_json_builder import PostgreSQLProcedureJSONBuilder

__all__ = ['PostgreSQLProcedureJSONBuilder']
