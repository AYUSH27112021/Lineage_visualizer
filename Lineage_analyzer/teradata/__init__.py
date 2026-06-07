"""
Teradata Column-Level Lineage Analyzer Package

This package provides tools for extracting and analyzing column-level data lineage
from Teradata databases. It supports:

- SQL parsing with Teradata dialect support
- File-based analysis of SQL scripts
- LLM-based procedure, function, and macro analysis
- JSON report generation for visualization

Teradata-specific features:
- MACRO definitions (parameterized SQL)
- Stored Procedures (REPLACE PROCEDURE syntax)
- User-Defined Functions (UDF)
- Triggers
- Multi-statement requests (semicolon-separated)
- BTEQ commands and scripts
- Volatile and Global Temporary Tables
- Collect Statistics statements
- FastLoad, MultiLoad, TPump utility scripts

Usage (File-based analysis):
    from teradata import LineageOrchestrator

    orchestrator = LineageOrchestrator(
        sql_directory="./sql_files",
        output_directory="./lineage_output",
        dialect="teradata",
        ollama_model="qwen2.5-coder:14b"
    )

    results = orchestrator.run_full_analysis()
"""

# Version
__version__ = "1.0.0"

# Import from teradata_main (file-based analysis)
from .teradata_main import LineageOrchestrator

# Re-export core components for backward compatibility
from .teradata_cleaner import EnhancedSQLCleaner
from .teradata_analyzer import EnhancedSQLAnalyzer
from .json_builder import EnhancedLineageJSONBuilder
from .enhanced_procedure_analyzer import EnhancedLLMLineageAnalyzer
from .enhanced_json_builder import EnhancedProcedureJSONBuilder

# Public API
__all__ = [
    # Version
    "__version__",

    # Main orchestrator (file-based)
    "LineageOrchestrator",

    # Core components
    "EnhancedSQLCleaner",
    "EnhancedSQLAnalyzer",
    "EnhancedLineageJSONBuilder",
    "EnhancedLLMLineageAnalyzer",
    "EnhancedProcedureJSONBuilder",
]
