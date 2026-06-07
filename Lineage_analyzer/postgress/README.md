# PostgreSQL Lineage Analyzer - Database Connection Module

This module provides comprehensive lineage analysis for PostgreSQL databases through direct database connection and metadata extraction.

## Overview

The PostgreSQL lineage analyzer has feature parity with T-SQL and Teradata implementations, supporting:

- Direct database connection via `psycopg2` and `SQLAlchemy`
- Comprehensive metadata extraction from PostgreSQL system catalogs
- Traditional parsing for views and queries (sqlglot)
- LLM-enhanced analysis for procedures and functions (Ollama/OpenAI)
- PostgreSQL-specific features (JSONB, arrays, RETURNING, materialized views, etc.)

## Files Added

### Core Metadata Components

1. **`enhanced_metadata_extractor.py`**
   - Connects to PostgreSQL database
   - Extracts comprehensive metadata from `information_schema` and `pg_catalog`
   - Captures tables, views, materialized views, procedures, functions, triggers, sequences
   - Optional query statistics via `pg_stat_statements` extension

2. **`metadata_view_analyzer.py`**
   - Analyzes views and queries using traditional sqlglot parsing
   - Utilizes metadata context for better table/column resolution
   - Extracts column-level lineage with transformation types

3. **`metadata_statement_builder.py`**
   - Builds comprehensive lineage reports from analysis results
   - Aggregates column lineage across multiple statements
   - Calculates dependencies and execution order

4. **`enhanced_procedure_analyzer.py`**
   - LLM-based analysis for stored procedures and functions
   - Supports both Ollama (local) and OpenAI (cloud)
   - Automatic table context injection for better accuracy
   - Parallel batch processing for efficiency

5. **`enhanced_json_builder.py`**
   - Generates comprehensive JSON output for procedures/functions
   - Multiple output formats: catalog, column lineage, dependency graph, table usage
   - Frontend-compatible format

6. **`metadata_lineage_main.py`**
   - Main orchestrator that coordinates the entire pipeline
   - Separates tabular SQL from executable SQL
   - Produces unified lineage reports

## Quick Start

### Installation Requirements

```bash
# Install PostgreSQL drivers
pip install psycopg2-binary sqlalchemy

# For LLM analysis (optional)
pip install requests  # For Ollama
# OR
pip install openai    # For OpenAI
```

### Basic Usage

```python
from Lineage_analyzer.postgress.conn import MetadataLineageOrchestrator

# Create orchestrator
orchestrator = MetadataLineageOrchestrator(
    host='localhost',
    database='mydb',
    username='postgres',
    password='mypassword',
    port=5432,
    output_directory='./lineage_output'
)

# Run full analysis
results = orchestrator.run_full_analysis()
```

### Command-Line Usage

```bash
# Basic analysis
python -m Lineage_analyzer.postgress.conn.metadata_lineage_main \
  --host localhost \
  --database mydb \
  --username postgres \
  --password mypassword \
  --output ./lineage_output

# With Ollama LLM for procedure analysis
python -m Lineage_analyzer.postgress.conn.metadata_lineage_main \
  --host localhost \
  --database mydb \
  --username postgres \
  --ollama-url http://localhost:11434 \
  --ollama-model qwen2.5-coder:14b

# With OpenAI
python -m Lineage_analyzer.postgress.conn.metadata_lineage_main \
  --host localhost \
  --database mydb \
  --username postgres \
  --openai-key sk-your-api-key \
  --openai-model gpt-4o-mini
```

## PostgreSQL-Specific Features

### Supported Features

- **Materialized Views**: Full analysis with refresh tracking
- **RETURNING Clauses**: Captured in INSERT/UPDATE/DELETE operations
- **ON CONFLICT (UPSERT)**: Detected and tracked
- **Array Operations**: `ARRAY[]`, `array_agg()`, `unnest()`
- **JSONB Operations**: `jsonb_*`, `json_*`, `->`, `->>`
- **Recursive CTEs**: Full support with cycle detection
- **Temporary Tables**: `pg_temp` schema detection
- **Multiple Languages**: SQL, PL/pgSQL, PL/Python, etc.
- **Extensions**: Detects and uses `pg_stat_statements` if available

### Metadata Extracted

**Tables & Views:**
- Table/view definitions and row counts
- Column names, data types, nullability
- Primary keys, foreign keys, unique constraints
- Check constraints
- Indexes with usage statistics
- Triggers and their definitions

**Functions & Procedures:**
- Function/procedure definitions (all languages)
- Parameter signatures
- Return types
- Descriptions from COMMENT statements

**Query Statistics** (if `pg_stat_statements` enabled):
- Query text and execution counts
- Average/min/max execution times
- Buffer hit/read/write statistics

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           metadata_lineage_main.py (Orchestrator)           │
└────────┬────────────────────────────────────────────┬───────┘
         │                                            │
         ▼                                            ▼
┌──────────────────────┐                  ┌──────────────────────┐
│ Metadata Extraction  │                  │   LLM Analysis       │
│                      │                  │                      │
│ enhanced_metadata_   │                  │ enhanced_procedure_  │
│ extractor.py         │                  │ analyzer.py          │
│                      │                  │                      │
│ • Connects to DB     │                  │ • Ollama/OpenAI      │
│ • Extracts metadata  │                  │ • Table context      │
│ • Caches results     │                  │ • Batch processing   │
└──────────┬───────────┘                  └──────────┬───────────┘
           │                                         │
           ▼                                         ▼
┌──────────────────────┐                  ┌──────────────────────┐
│ Tabular SQL Analysis │                  │   JSON Builders      │
│                      │                  │                      │
│ metadata_view_       │                  │ enhanced_json_       │
│ analyzer.py          │                  │ builder.py           │
│                      │                  │                      │
│ • Views/queries      │                  │ • Catalog            │
│ • Traditional parse  │                  │ • Column lineage     │
│ • Column lineage     │                  │ • Dependencies       │
└──────────┬───────────┘                  │ • Table usage        │
           │                              └──────────────────────┘
           ▼
┌──────────────────────┐
│ Statement Builder    │
│                      │
│ metadata_statement_  │
│ builder.py           │
│                      │
│ • Aggregates results │
│ • Builds reports     │
│ • Calculates stats   │
└──────────────────────┘
```

## Output Files

The analyzer generates the following output files:

1. **`statement_lineage_YYYYMMDD_HHMMSS.json`**
   - Lineage for views and query history
   - Column-level transformations
   - Source-target relationships

2. **`procedure_lineage_YYYYMMDD_HHMMSS.json`**
   - LLM-analyzed procedures and functions
   - Tables read/written
   - Column-level lineage
   - Complexity metrics

3. **`lineage_summary_YYYYMMDD_HHMMSS.json`**
   - Combined summary report
   - Statistics and metrics
   - Database summary

4. **`enhanced_metadata_<database>_YYYYMMDDTHHMMSSZ.json`**
   - Cached metadata for reuse
   - Table/column definitions
   - Parser support maps

## Configuration Options

### Connection Parameters

- `host`: PostgreSQL server hostname/IP
- `database`: Database name
- `username`: Database user
- `password`: Password (optional for trust auth)
- `port`: Port number (default: 5432)

### LLM Configuration

- `ollama_url`: Ollama API endpoint (default: http://localhost:11434)
- `ollama_model`: Ollama model name (default: qwen2.5-coder:14b)
- `openai_api_key`: OpenAI API key (uses OpenAI if provided)
- `openai_model`: OpenAI model name (default: gpt-4o-mini)
- `batch_size`: Parallel processing batch size (default: 10)
- `timeout`: Request timeout in seconds (default: 300)

### Output Configuration

- `output_directory`: Output directory path (default: ./lineage_output)
- `dialect`: SQL dialect (default: postgres)
- `debug`: Enable debug output

## Comparison with Other Databases

| Feature | PostgreSQL | T-SQL | Teradata |
|---------|-----------|-------|----------|
| Database Connection | Yes | Yes | Yes |
| Metadata Extraction | Yes | Yes | Yes |
| View Analysis | Yes | Yes | Yes |
| Procedure Analysis (LLM) | Yes | Yes | Yes |
| Query History | Yes* | Yes | Yes |
| Materialized Views | Yes | No | No |
| RETURNING Clause | Yes | No | No |
| JSONB Operations | Yes | No | No |
| Array Operations | Yes | No | No |

*Requires `pg_stat_statements` extension

## Troubleshooting

### Connection Issues

```python
# If using SSL/TLS
conn_str = build_connection_url(
    host='myserver.com',
    database='mydb',
    username='user',
    password='pass',
    port=5432
)
# Connection string includes SSL parameters
```

### Query Statistics Not Available

Enable `pg_stat_statements` extension:

```sql
-- As superuser
CREATE EXTENSION pg_stat_statements;

-- In postgresql.conf
shared_preload_libraries = 'pg_stat_statements'
```

### LLM Analysis Timeout

Increase timeout or reduce batch size:

```python
orchestrator = MetadataLineageOrchestrator(
    # ... other params ...
    timeout=600,  # 10 minutes
    batch_size=5  # Smaller batches
)
```

## Dependencies

Required:
- `sqlalchemy` - Database connection
- `psycopg2-binary` - PostgreSQL driver
- `sqlglot` - SQL parsing

Optional:
- `requests` - For Ollama support
- `openai` - For OpenAI support
