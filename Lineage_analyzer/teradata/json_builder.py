"""
Re-export json_builder from conn directory for easier imports.
This allows using:
    from .json_builder import EnhancedLineageJSONBuilder
instead of:
    from .conn.json_builder import EnhancedLineageJSONBuilder
"""

from .conn.json_builder import EnhancedLineageJSONBuilder

__all__ = ['EnhancedLineageJSONBuilder']
