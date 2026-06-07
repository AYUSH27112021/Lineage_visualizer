"""
Re-export postgres_procedure_analyzer from conn directory for easier imports.
This allows using:
    from .postgres_procedure_analyzer import PostgreSQLProcedureAnalyzer
instead of:
    from .conn.postgres_procedure_analyzer import PostgreSQLProcedureAnalyzer
"""

from .conn.postgres_procedure_analyzer import PostgreSQLProcedureAnalyzer

__all__ = ['PostgreSQLProcedureAnalyzer']
