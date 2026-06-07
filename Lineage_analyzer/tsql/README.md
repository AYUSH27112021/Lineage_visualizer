# Metadata-Based T-SQL Lineage Analyzer

A comprehensive data lineage analysis system that uses database connections instead of SQL files. This system extracts metadata directly from SQL Server and analyzes data flow through views, stored procedures, functions, and triggers.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MetadataLineageOrchestrator                             │
│                     (metadata_lineage_main.py)                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                ┌───────────────────┴───────────────────┐
                │                                       │
                ▼                                       ▼
┌───────────────────────────────┐       ┌───────────────────────────────────┐
│   Metadata Extraction         │       │   Lineage Analysis                │
│   enhanced_metadata_extractor │       │                                   │
│                               │       │   ┌───────────────────────────┐   │
│   Extracts from SQL Server:   │       │   │  Tabular SQL              │   │
│   • Tables & Columns          │       │   │  (Views, Query History)   │   │
│   • Views (with definitions)  │       │   │                           │   │
│   • Procedures                │       │   │  metadata_view_analyzer   │   │
│   • Functions                 │       │   │  metadata_statement_builder│  │
│   • Triggers                  │       │   │                           │   │
│   • Query History             │       │   │  Uses: sqlglot (parsing)  │   │
│   • Dependencies              │       │   └───────────────────────────┘   │
│   • Indexes, FKs, etc.        │       │                                   │
│                               │       │   ┌───────────────────────────┐   │
│   Filters out system objects  │       │   │  Executable SQL           │   │
│   and schemas automatically   │       │   │  (Procedures, Functions,  │   │
│                               │       │   │   Triggers)               │   │
│                               │       │   │                           │   │
│                               │       │   │  enhanced_procedure_      │   │
│                               │       │   │  analyzer                 │   │
│                               │       │   │                           │   │
│                               │       │   │  Uses: LLM (Ollama/OpenAI)│   │
│                               │       │   └───────────────────────────┘   │
└───────────────────────────────┘       └───────────────────────────────────┘
                │                                       │
                │                                       │
                ▼                                       ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                      JSON Output Files                        │
        │                                                               │
        │  • statement_lineage_*.json      - View/query lineage         │
        │  • procedure_lineage_*.json      - Procedure/function lineage │
        │  • *_column_lineage_*.json       - Column-level mappings      │
        │  • *_dependency_graph_*.json     - For visualization          │
        │  • *_tabular_components_*.json   - Table usage report         │
        │  • lineage_summary_*.json        - Combined summary           │
        │  • enhanced_metadata_*.json      - Cached metadata            │
        └───────────────────────────────────────────────────────────────┘
```

## Key Differences from File-Based Analysis

| Aspect | File-Based (tsql_main.py) | Metadata-Based (metadata_lineage_main.py) |
|--------|---------------------------|-------------------------------------------|
| **Source** | SQL files on disk | Database connection |
| **Metadata** | Inferred from SQL | Extracted directly from sys tables |
| **Schema Context** | Limited | Full (tables, columns, types, FKs) |
| **Views** | Parsed from CREATE VIEW files | Extracted from sys.views with definitions |
| **Query History** | Not available | From Query Store (if enabled) |
| **Table Validation** | Best effort | Against actual schema |
| **Column Resolution** | Alias-based | Schema-aware with disambiguation |

## File Structure

```
metadata_lineage_analyzer/
├── __init__.py
├── metadata_lineage_main.py         # Main orchestrator
├── metadata_view_analyzer.py        # View/query parsing
├── metadata_statement_builder.py    # Statement lineage builder
├── example_metadata_test.py         # Example/test script
├── enhanced_metadata_extractor.py   # Database metadata extraction
├── enhanced_procedure_analyzer.py   # LLM-based procedure analysis
├── enhanced_json_builder.py         # Procedure JSON builder
├── tsql_analyzer.py                 # SQL statement analyzer
├── json_builder.py                  # Statement JSON builder
└── tsql_cleaner.py                  # SQL file cleaner
```

## Installation

### Dependencies

```bash
pip install sqlglot sqlalchemy pyodbc aiohttp openai
```

### ODBC Driver

For SQL Server connectivity, install the appropriate ODBC driver:

**Linux (Ubuntu/Debian):**
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

**Windows:**
Download from [Microsoft ODBC Driver for SQL Server](https://docs.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)

## Usage

### 1. Basic Usage with Database Connection

```python
from metadata_lineage_main import MetadataLineageOrchestrator

orchestrator = MetadataLineageOrchestrator(
    # Database connection
    server="your-server.database.windows.net",
    database="YourDatabase",
    username="your_username",
    password="your_password",
    driver="{ODBC Driver 18 for SQL Server}",
    
    # Output configuration
    output_directory="./lineage_output",
    dialect="tsql",
    
    # LLM configuration (for procedure analysis)
    ollama_url="http://localhost:11434",
    ollama_model="qwen2.5-coder:14b",
    # OR use OpenAI:
    # openai_api_key="your-openai-key",
    # openai_model="gpt-4o-mini",
)

results = orchestrator.run_full_analysis()

# Access results
print(f"Views analyzed: {results['statistics']['total_views']}")
print(f"Procedures analyzed: {results['statistics']['total_procedures']}")
print(f"LLM success rate: {results['statistics']['llm_success_rate']}")
```

### 2. Using Pre-Extracted Metadata

If you've already extracted metadata (useful for repeated analysis):

```python
import json

# Load previously extracted metadata
with open("./metadata_cache/enhanced_metadata_MyDB.json") as f:
    metadata = json.load(f)

orchestrator = MetadataLineageOrchestrator(
    server="localhost",
    database="MyDB",
    username="",
    password="",
    preloaded_metadata=metadata,
    output_directory="./lineage_output",
)

results = orchestrator.run_full_analysis()
```

### 3. Using Metadata File Path

```python
orchestrator = MetadataLineageOrchestrator(
    server="localhost",
    database="MyDB",
    username="",
    password="",
    metadata_file_path="./metadata_cache/enhanced_metadata_MyDB.json",
    output_directory="./lineage_output",
)

results = orchestrator.run_full_analysis()
```

### 4. Command Line Usage

```bash
# Full analysis with database connection
python metadata_lineage_main.py \
    --server your-server.database.windows.net \
    --database YourDatabase \
    --username your_username \
    --password your_password \
    --driver "{ODBC Driver 18 for SQL Server}" \
    --output ./lineage_output \
    --ollama-model qwen2.5-coder:14b

# Using OpenAI instead of Ollama
python metadata_lineage_main.py \
    --server your-server.database.windows.net \
    --database YourDatabase \
    --username your_username \
    --password your_password \
    --output ./lineage_output \
    --openai-key sk-your-openai-key \
    --openai-model gpt-4o-mini

# Using pre-extracted metadata file
python metadata_lineage_main.py \
    --server localhost \
    --database YourDatabase \
    --username dummy \
    --password dummy \
    --metadata-file ./metadata_cache/enhanced_metadata_MyDB.json \
    --output ./lineage_output
```

## Analysis Pipeline

The analysis follows this pipeline:

1. **Metadata Extraction**
   - Connects to SQL Server
   - Extracts tables, views, procedures, functions, triggers
   - Captures query history from Query Store (if enabled)
   - Filters out system objects automatically

2. **Component Separation**
   - **Tabular SQL**: Views, Query History → Traditional parsing
   - **Executable SQL**: Procedures, Functions, Triggers → LLM analysis

3. **Tabular SQL Analysis**
   - Uses sqlglot for parsing
   - Extracts source tables and column lineage
   - Handles CTEs, JOINs, subqueries
   - Detects aggregations and transformations

4. **Executable SQL Analysis**
   - Uses LLM (Ollama or OpenAI) with full table metadata context
   - Parallel processing for efficiency
   - Extracts column-level lineage
   - Detects procedure calls and dependencies

5. **Report Generation**
   - Builds JSON reports compatible with existing frontend
   - Generates dependency graphs for visualization
   - Creates column lineage catalogs

## Output Files

| File | Description |
|------|-------------|
| `statement_lineage_*.json` | View and query history lineage |
| `procedure_lineage_*.json` | Legacy format for procedures/functions |
| `procedure_*_complete_*.json` | Complete LLM analysis results |
| `procedure_*_catalog_*.json` | Procedure/function catalog |
| `procedure_*_column_lineage_*.json` | Detailed column mappings |
| `procedure_*_dependency_graph_*.json` | For visualization tools |
| `procedure_*_tabular_components_*.json` | Table usage report |
| `lineage_summary_*.json` | Combined summary |
| `enhanced_metadata_*.json` | Cached metadata |

## Output Format

### Statement Lineage JSON Structure

```json
{
  "metadata": {
    "dialect": "tsql",
    "database_name": "SampleDB",
    "source_type": "database_metadata",
    "version": "2.0"
  },
  "summary": {
    "total_views": 5,
    "total_queries": 10,
    "total_tables": 15,
    "total_columns": 50,
    "total_dependencies": 25
  },
  "tables": {
    "dbo.customers": {
      "columns": ["customer_id", "customer_name"],
      "depends_on": [],
      "is_view": false
    },
    "dbo.vw_customer_orders": {
      "columns": ["customer_id", "order_count", "total_spent"],
      "depends_on": ["dbo.customers", "dbo.orders"],
      "is_view": true
    }
  },
  "columns": {
    "dbo.vw_customer_orders.total_spent": {
      "source_columns": ["dbo.orders.total_amount"],
      "transforms": ["aggregate"],
      "is_aggregate": true,
      "confidence_score": 0.85
    }
  }
}
```

### Procedure Lineage JSON Structure

```json
{
  "metadata": {
    "source_type": "database_metadata",
    "analysis_method": "LLM-based",
    "llm_provider": "Ollama"
  },
  "summary": {
    "total_analyzed": 10,
    "successful": 9,
    "success_rate": "90.0%"
  },
  "procedures": {
    "dbo.usp_GetCustomerStats": {
      "reads_tables": ["dbo.orders", "dbo.customers"],
      "writes_tables": [],
      "columns_read": ["dbo.orders.customer_id", "dbo.orders.total_amount"],
      "column_lineage": [
        {
          "target_column": "@TotalSpent",
          "sources": ["dbo.orders.total_amount"],
          "transformation": {"type": "AGGREGATION"}
        }
      ],
      "calls_procedures": [],
      "analysis_success": true
    }
  }
}
```

## LLM Configuration

### Using Ollama (Default)

1. Install Ollama: https://ollama.ai
2. Pull the model:
   ```bash
   ollama pull qwen2.5-coder:14b
   ```
3. Start Ollama:
   ```bash
   ollama serve
   ```

### Using OpenAI

Simply provide your API key:
```python
orchestrator = MetadataLineageOrchestrator(
    # ... other params ...
    openai_api_key="sk-your-key",
    openai_model="gpt-4o-mini",  # or gpt-4, etc.
)
```

## Error Handling

The system is designed to be resilient:

- **Database Connection Errors**: Automatic retry with exponential backoff for transient errors
- **Parse Errors**: Continues with next item, logs error
- **LLM Errors**: Records error in output, continues with next procedure
- **Timeout Handling**: Dynamic timeout based on SQL complexity

## Performance Considerations

- **Parallel Processing**: LLM requests are batched (default: 10 concurrent)
- **Caching**: Metadata is saved to disk for reuse
- **Query Store**: Leverages SQL Server Query Store for historical query analysis
- **Timeout Configuration**: Adjustable timeout for complex procedures (default: 300s)

## Migrating from File-Based Analysis

If you're currently using `tsql_main.py` with SQL files:

1. The output format is compatible - your frontend should work unchanged
2. Replace `LineageOrchestrator` with `MetadataLineageOrchestrator`
3. Provide database connection params instead of `sql_directory`
4. Consider pre-extracting metadata for development/testing

## Troubleshooting

### Common Issues

1. **"No module named 'pyodbc'"**
   - Install: `pip install pyodbc`
   - Ensure ODBC driver is installed

2. **"Login failed for user"**
   - Check credentials
   - For Azure SQL, ensure firewall allows your IP

3. **"LLM timeout"**
   - Increase timeout: `timeout=600`
   - Simplify complex procedures
   - Use OpenAI for faster responses

4. **"No procedures found"**
   - Check database permissions
   - Verify procedures exist in non-system schemas
