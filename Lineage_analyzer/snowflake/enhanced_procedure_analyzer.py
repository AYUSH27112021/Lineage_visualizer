"""
Re-export enhanced_procedure_analyzer from conn directory for easier imports.
This allows using:
    from .enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer
instead of:
    from .conn.enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer
"""

from .conn.enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer

__all__ = ['EnhancedLLMLineageAnalyzer']
