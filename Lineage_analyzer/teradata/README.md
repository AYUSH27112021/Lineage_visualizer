# Teradata Lineage Analyzer

Comprehensive column-level data lineage analysis for Teradata databases with LLM-enhanced procedure analysis.

## Overview

This package provides two modes of analysis for Teradata databases:

1. **File-Based Analysis** (`teradata_main.py`) - Analyze SQL files directly
2. **Database Connection-Based Analysis** (`conn/metadata_lineage_main.py`) - Connect to live Teradata database

Both modes support LLM-based analysis of procedures, functions, macros, and triggers for accurate column-level lineage.

## Architecture

```
teradata/
├── __init__.py
├── README.md
├── teradata_main.py                     # File-based analysis orchestrator
├── teradata_cleaner.py                  # Re-export wrapper
├── teradata_analyzer.py                 # Re-export wrapper
├── json_builder.py                      # Re-export wrapper
├── enhanced_procedure_analyzer.py       # Re-export wrapper
├── enhanced_json_builder.py             # Re-export wrapper
│
└── conn/                                # Database connection-based analysis
    ├── teradata_cleaner.py              # SQL file cleaner (BTEQ, macros)
    ├── teradata_analyzer.py             # SQL statement analyzer
    ├── json_builder.py                  # Basic lineage JSON builder
    ├── enhanced_procedure_analyzer.py   # LLM-based procedure analyzer
    ├── enhanced_json_builder.py         # Enhanced JSON builder
    ├── enhanced_metadata_extractor.py   # Database metadata extractor
    ├── metadata_lineage_main.py         # Database connection orchestrator
    ├── metadata_view_analyzer.py        # View-specific analyzer
    ├── metadata_statement_builder.py    # Statement builder with metadata
    ├── example_usage.py                 # Usage examples
    └── test_metadata_view_analyzer.py   # Test suite
```

## Teradata-Specific Features

### Supported Object Types
- **Tables** - Standard, Multiset, Set, No Primary Index
- **Views** - Standard views with complex queries
- **Procedures** - Stored procedures (SQL, Java, C)
- **Functions** - User-Defined Functions (UDF)
- **Macros** - Teradata's parameterized SQL templates
- **Triggers** - Before/After row/statement triggers
- **Volatile Tables** - Session-specific temporary tables
- **Global Temporary Tables** - Persistent temporary tables

### Teradata SQL Syntax
- **QUALIFY** - Window function filtering
- **SAMPLE** - Data sampling
- **TOP N** - Row limiting
- **TD Outer Joins** - Legacy `(+)` syntax
- **COLLECT STATISTICS** - Statistics collection
- **MULTISET/SET** - Table specifications
- **BTEQ Commands** - `.LOGON`, `.RUN FILE`, etc.
- **Named Expressions** - NAMED, TITLE, FORMAT keywords

### Teradata Data Types
All standard Teradata types supported:
- Numeric: BYTEINT, SMALLINT, INTEGER, BIGINT, DECIMAL, NUMBER
- Character: CHAR, VARCHAR, CLOB
- Binary: BYTE, VARBYTE, BLOB
- Date/Time: DATE, TIME, TIMESTAMP
- Period: PERIOD(DATE), PERIOD(TIME), PERIOD(TIMESTAMP)
- Structured: JSON, XML, ARRAY, VARRAY

## Installation

### Prerequisites

```bash
# Required Python packages
pip install sqlglot teradatasql requests openai

# Optional (for local LLM)
# Install Ollama from https://ollama.ai
ollama pull qwen2.5-coder:14b
```

### Database Requirements

For connection-based analysis, you need:
- Teradata database access (TD2, LDAP, or Kerberos authentication)
- SELECT privileges on DBC system tables
- Network connectivity to Teradata server

## Usage

### 1. File-Based Analysis

Analyze SQL files from a directory without database connection:

```python
from teradata import LineageOrchestrator

# Using OpenAI (recommended for accuracy)
orchestrator = LineageOrchestrator(
    sql_directory="./teradata_sql_files",
    output_directory="./lineage_output",
    dialect="teradata",
    openai_api_key="sk-...",
    openai_model="gpt-4o-mini"
)

results = orchestrator.run_full_analysis()
```

#### Command Line

```bash
# With OpenAI
python -m teradata.teradata_main \
    ./sql_files \
    --output ./results \
    --openai-key sk-... \
    --openai-model gpt-4o-mini

# With Ollama (local)
python -m teradata.teradata_main \
    ./sql_files \
    --output ./results \
    --ollama-url http://localhost:11434 \
    --ollama-model qwen2.5-coder:14b
```

### 2. Database Connection-Based Analysis

Connect to live Teradata database and extract metadata:

```python
from teradata.conn.metadata_lineage_main import MetadataLineageOrchestrator

# Using OpenAI
orchestrator = MetadataLineageOrchestrator(
    host="teradata.company.com",
    user="analyst",
    password="secure_password",
    database="PROD_DB",
    output_directory="./lineage_output",
    openai_api_key="sk-...",
    openai_model="gpt-4o-mini"
)

results = orchestrator.run_full_analysis()
```

#### Command Line

```bash
# With OpenAI
python -m teradata.conn.metadata_lineage_main \
    --host teradata.company.com \
    --user analyst \
    --database PROD_DB \
    --openai-key sk-... \
    --output ./results

# With LDAP authentication
python -m teradata.conn.metadata_lineage_main \
    --host teradata.company.com \
    --user "DOMAIN\\analyst" \
    --database PROD_DB \
    --logmech LDAP \
    --openai-key sk-... \
    --output ./results
```

## Output Files

Both analysis modes generate comprehensive JSON reports:

### Statement Lineage Report
```json
{
  "metadata": {
    "dialect": "teradata",
    "generated_at": "2025-11-25T14:30:00"
  },
  "summary": {
    "total_tables": 150,
    "total_views": 45,
    "volatile_tables": 12,
    "macros": 8
  },
  "tables": { ... },
  "columns": { ... },
  "views": { ... }
}
```

### Procedure Lineage Report
```json
{
  "summary": {
    "total_procedures": 30,
    "total_functions": 20,
    "total_macros": 15,
    "successful_analyses": 62,
    "llm_success_rate": "95.4%"
  },
  "procedures": { ... },
  "functions": { ... },
  "macros": { ... }
}
```

### Combined Summary
```json
{
  "overall_summary": {
    "total_files_analyzed": 250,
    "total_procedures": 30,
    "total_macros": 15,
    "volatile_tables": 12
  },
  "llm_analysis_details": {
    "column_lineage_extracted": true,
    "transformation_detection": true
  }
}
```

## Key Features

### 1. Intelligent SQL Parsing
- Uses `sqlglot` with Teradata dialect
- Handles complex queries with CTEs, subqueries, window functions
- Supports Teradata-specific syntax (QUALIFY, SAMPLE, etc.)

### 2. LLM-Based Procedure Analysis
- Parallel batch processing for performance
- Column-level lineage extraction
- Transformation detection (calculations, aggregations)
- Dependency mapping (table → procedure → table)

### 3. Comprehensive Metadata Extraction
- Connects to DBC system tables
- Extracts table/column definitions
- Captures foreign keys and indexes
- Retrieves procedure/function/macro source code

### 4. Teradata-Specific Handling
- Volatile table tracking across sessions
- Macro parameter resolution
- BTEQ script parsing
- Multi-statement request handling

## Configuration Options

### LLM Configuration

```python
# OpenAI (recommended)
orchestrator = LineageOrchestrator(
    openai_api_key="sk-...",
    openai_model="gpt-4o-mini",  # or gpt-4o for better accuracy
    timeout=300,                  # 5 minutes per procedure
    batch_size=10                 # parallel processing
)

# Ollama (local, free)
orchestrator = LineageOrchestrator(
    ollama_url="http://localhost:11434",
    ollama_model="qwen2.5-coder:14b",
    timeout=300,
    batch_size=5  # lower for local processing
)
```

### Database Connection

```python
# Basic authentication (TD2)
orchestrator = MetadataLineageOrchestrator(
    host="teradata.company.com",
    user="analyst",
    password="password",
    logmech="TD2"
)

# LDAP authentication
orchestrator = MetadataLineageOrchestrator(
    host="teradata.company.com",
    user="DOMAIN\\analyst",
    password="password",
    logmech="LDAP",
    encryptdata=True
)

# Kerberos authentication
orchestrator = MetadataLineageOrchestrator(
    host="teradata.company.com",
    user="analyst@REALM",
    logmech="KRB5"
)
```

## Performance

### Typical Database (500 objects)
- **Metadata Extraction**: 30-90 seconds
- **View Analysis**: 2-5 seconds
- **Procedure Analysis**: 5-15 minutes (with OpenAI)
- **Total Time**: 10-20 minutes

### Optimization Tips
1. Use OpenAI for faster, more accurate analysis
2. Increase `batch_size` for parallel processing
3. Pre-extract metadata and reuse for multiple analyses
4. Filter to specific schemas/databases to reduce scope

## Comparison with T-SQL and Snowflake

| Feature | T-SQL | Snowflake | Teradata |
|---------|-------|-----------|----------|
| **Batch Separator** | GO | ; | ; |
| **Procedures** | CREATE/ALTER PROCEDURE | CREATE/REPLACE PROCEDURE | CREATE/REPLACE PROCEDURE |
| **Temp Tables** | #temp, ##global | TEMPORARY | VOLATILE, GLOBAL TEMPORARY |
| **Macros** | No | No | Yes MACRO |
| **QUALIFY** | No | Yes | Yes |
| **Outer Join** | *= and =* | ANSI | (+) and ANSI |
| **System Tables** | sys.*, INFORMATION_SCHEMA | INFORMATION_SCHEMA | DBC.* |
| **Authentication** | Windows, SQL | SSO, Key-Pair | TD2, LDAP, Kerberos |

## Troubleshooting

### Common Issues

**1. Connection Timeout**
```python
# Increase timeout
orchestrator = MetadataLineageOrchestrator(
    timeout=600,  # 10 minutes
    ...
)
```

**2. Parse Failures**
- Check SQL syntax for Teradata compatibility
- Verify object names don't use reserved keywords
- Enable debug mode: `debug=True`

**3. LLM Analysis Failures**
- Verify API key is valid
- Check network connectivity
- Try smaller batch sizes
- Increase timeout for complex procedures

**4. Metadata Extraction Errors**
- Verify DBC table permissions
- Check database name is correct
- Ensure user has CONNECT privilege

## Advanced Usage

### Pre-load Metadata

```python
# Extract metadata once
from teradata.conn.enhanced_metadata_extractor import extract_enhanced_database_metadata

metadata, file_path = extract_enhanced_database_metadata(
    host="teradata.company.com",
    database="PROD_DB",
    username="analyst",
    password="password"
)

# Use pre-loaded metadata
orchestrator = MetadataLineageOrchestrator(
    host="teradata.company.com",
    user="analyst",
    metadata_file=file_path,  # Skip extraction step
    ...
)
```

### Analyze Specific Objects

```python
# Analyze only procedures matching pattern
results = orchestrator.run_full_analysis()
procedures = {
    name: proc
    for name, proc in results['procedure_report']['procedures'].items()
    if name.startswith('ETL_')
}
```

## Support and Documentation

- **Package Documentation**: See individual module docstrings
- **Examples**: Check `conn/example_usage.py` for working examples
- **Tests**: Run `conn/test_metadata_view_analyzer.py` for validation
- **Issues**: Report bugs via GitHub issues
