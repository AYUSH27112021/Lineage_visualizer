# Snowflake Lineage Analyzer

File-based SQL lineage analysis for Snowflake databases with LLM-enhanced procedure analysis.

## Overview

This analyzer processes SQL files from a directory and extracts complete data lineage, including:
- Table-to-table dependencies
- Column-level lineage with transformations
- Procedure/function/task analysis using LLM
- Snowflake-specific features (streams, tasks, semi-structured data)

## Directory Structure

```
snowflake/
├── snowflake_main.py              # Main orchestrator (file-based analysis)
├── snowflake_cleaner.py           # SQL file cleaner (re-exports from conn/)
├── snowflake_analyzer.py          # Statement analyzer (re-exports from conn/)
├── json_builder.py                # Statement lineage builder (re-exports from conn/)
├── enhanced_procedure_analyzer.py # LLM-based analyzer (re-exports from conn/)
├── enhanced_json_builder.py       # Procedure lineage builder (re-exports from conn/)
├── example_test.py                # Example usage with sample SQL files
└── conn/                          # Database connection-based analysis
    ├── metadata_lineage_main.py   # Connection-based orchestrator
    ├── snowflake_cleaner.py       # SQL cleaner implementation
    ├── snowflake_analyzer.py      # Statement analyzer implementation
    ├── json_builder.py            # JSON builder implementation
    ├── enhanced_procedure_analyzer.py  # LLM analyzer implementation
    ├── enhanced_json_builder.py   # Enhanced JSON builder
    └── enhanced_metadata_extractor.py  # Database metadata extractor
```

## Two Analysis Modes

### 1. File-Based Analysis (snowflake_main.py)
Analyzes SQL files from a directory structure.

**Use when:**
- You have SQL scripts in files
- Working with version-controlled SQL code
- Analyzing development/test environments

**Usage:**
```bash
# Basic usage
python -m Lineage_analyzer.snowflake.snowflake_main ./sql_files

# With output directory
python -m Lineage_analyzer.snowflake.snowflake_main ./sql_files --output ./reports

# With LLM (Ollama)
python -m Lineage_analyzer.snowflake.snowflake_main ./sql_files \
  --ollama-url http://localhost:11434 \
  --ollama-model qwen2.5-coder:14b

# With LLM (OpenAI)
python -m Lineage_analyzer.snowflake.snowflake_main ./sql_files \
  --openai-key sk-your-key \
  --openai-model gpt-4o-mini

# With metadata context
python -m Lineage_analyzer.snowflake.snowflake_main ./sql_files \
  --metadata ./metadata.json \
  --debug
```

### 2. Database Connection-Based Analysis (conn/metadata_lineage_main.py)
Connects directly to Snowflake and extracts metadata.

**Use when:**
- Analyzing production databases
- Need real-time schema information
- Want to include query history

**Usage:**
```bash
python -m Lineage_analyzer.snowflake.conn.metadata_lineage_main \
  --account your-account \
  --database your-db \
  --username your-user \
  --authenticator externalbrowser
```

## Features

### Snowflake-Specific Support

#### 1. Semi-Structured Data
- VARIANT column access (`col:path::TYPE`)
- LATERAL FLATTEN operations
- PARSE_JSON, OBJECT_CONSTRUCT, ARRAY_CONSTRUCT
- Array and object manipulation

#### 2. Time Travel & Versioning
- AT(TIMESTAMP => ...)
- BEFORE(STATEMENT => ...)
- CHANGES clause for CDC

#### 3. Streams & Tasks
- Stream creation and usage
- Task scheduling and dependencies
- SYSTEM$STREAM_HAS_DATA detection

#### 4. Advanced SQL Features
- QUALIFY clause
- MATCH_RECOGNIZE
- PIVOT/UNPIVOT
- Window functions with complex frames
- Hierarchical queries (CONNECT BY)

#### 5. Object Types
- Procedures (SQL, JavaScript, Python)
- Functions (Scalar, Table-valued)
- Tasks (scheduled and event-driven)
- Streams (change data capture)
- Materialized views
- Secure views

### LLM-Enhanced Analysis

The analyzer uses LLM (via Ollama or OpenAI) for deep analysis of:
- **Procedures**: Input/output parameters, table dependencies, column lineage
- **Functions**: UDFs with transformation logic
- **Tasks**: Scheduled data processing workflows
- **Complex Logic**: Dynamic SQL, conditional branching, loops

**Benefits:**
- Handles complex procedural code that traditional parsing can't
- Extracts column-level transformations
- Identifies business logic and calculations
- Provides confidence scores for lineage

## Output Files

The analyzer generates multiple output files:

1. **statement_lineage_<timestamp>.json**
   - Tables, views, queries
   - Column-level lineage for SELECT/INSERT/UPDATE
   - CTE tracking
   - Temp table tracking

2. **procedure_lineage_<timestamp>.json**
   - Procedures, functions, tasks
   - LLM-analyzed lineage
   - Parameter information
   - Procedure call chains

3. **procedure_catalog_<timestamp>.json**
   - Complete catalog of executable components
   - Metadata and signatures
   - Dependencies

4. **column_lineage_<timestamp>.json**
   - Detailed column-to-column mappings
   - Transformation types
   - Source columns for each target

5. **dependency_graph_<timestamp>.json**
   - Object dependency graph
   - Call hierarchy
   - Topological ordering

6. **table_usage_<timestamp>.json**
   - Table read/write statistics
   - Most referenced tables
   - Usage patterns

7. **lineage_summary_<timestamp>.json**
   - Combined summary report
   - Overall statistics
   - Warnings and issues

## Command-Line Options

```
positional arguments:
  sql_directory         Directory containing SQL files

optional arguments:
  -h, --help            Show help message
  --output, -o          Output directory for reports (default: ./lineage_output)
  --dialect, -d         SQL dialect (default: snowflake)
  --max-files, -m       Maximum number of files to process
  --debug               Enable debug mode

LLM Configuration:
  --ollama-url          Ollama API URL (default: http://localhost:11434)
  --ollama-model        Ollama model name (default: qwen2.5-coder:14b)
  --openai-key          OpenAI API key (uses OpenAI if provided)
  --openai-model        OpenAI model name (default: gpt-4o-mini)
  --batch-size          Parallel processing batch size (default: 10)
  --timeout             Request timeout in seconds (default: 300)

Metadata:
  --metadata            Path to metadata JSON file
```

## Example Usage

### Run Example Test
```bash
python -m Lineage_analyzer.snowflake.example_test
```

This will:
1. Create sample Snowflake SQL files
2. Run complete lineage analysis
3. Display results and statistics
4. Generate all output files

### Analyze Real Project
```bash
# Analyze your Snowflake SQL project
python -m Lineage_analyzer.snowflake.snowflake_main \
  /path/to/your/snowflake/sql \
  --output ./lineage_reports \
  --openai-key $OPENAI_API_KEY \
  --debug

# With custom metadata (table schemas)
python -m Lineage_analyzer.snowflake.snowflake_main \
  /path/to/sql \
  --metadata ./table_metadata.json \
  --output ./reports
```

## Metadata File Format

Provide table/column metadata to improve analysis accuracy:

```json
{
  "tables": [
    {
      "schema": "PUBLIC",
      "name": "CUSTOMERS",
      "columns": [
        {"name": "CUSTOMER_ID", "type": "NUMBER"},
        {"name": "CUSTOMER_NAME", "type": "VARCHAR"},
        {"name": "EMAIL", "type": "VARCHAR"},
        {"name": "METADATA", "type": "VARIANT"}
      ]
    }
  ],
  "procedures": [...],
  "functions": [...]
}
```

## Integration with Frontend

The output JSON files are designed to be consumed by visualization frontends:

- **statement_lineage_*.json**: Table and column lineage graphs
- **procedure_lineage_*.json**: Procedure dependency graphs
- **dependency_graph_*.json**: Interactive dependency visualization
- **column_lineage_*.json**: Column-level flow diagrams

## Architecture

```
┌─────────────────────────────────────────────────────┐
│         LineageOrchestrator (snowflake_main.py)     │
└─────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Cleaner    │  │   Analyzer   │  │ LLM Analyzer │
│ (Extract)    │  │ (Parse AST)  │  │ (Deep Logic) │
└──────────────┘  └──────────────┘  └──────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                ┌──────────────────┐
                │  JSON Builders   │
                │ (Generate Output)│
                └──────────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │  Output Files (7 types) │
              └────────────────────────┘
```

## Performance

- **Small projects** (<100 files): < 1 minute
- **Medium projects** (100-500 files): 2-5 minutes
- **Large projects** (>500 files): 5-15 minutes

LLM analysis adds overhead:
- Ollama (local): +0.5-2s per procedure
- OpenAI (cloud): +0.2-1s per procedure

## Limitations

1. **Dynamic SQL**: Limited analysis of EXECUTE IMMEDIATE
2. **External References**: Can't resolve external database references
3. **Python/JavaScript UDFs**: Limited parsing of non-SQL code
4. **Complex VARIANT**: Some semi-structured patterns may be missed

## Troubleshooting

### Import Errors
```python
# If you get import errors, try:
import sys
sys.path.append('/path/to/Lineage_visualizer')
from Lineage_analyzer.snowflake.snowflake_main import LineageOrchestrator
```

### LLM Timeouts
```bash
# Increase timeout for complex procedures
python -m Lineage_analyzer.snowflake.snowflake_main ./sql \
  --timeout 600  # 10 minutes
```

### Memory Issues
```bash
# Process files in batches
python -m Lineage_analyzer.snowflake.snowflake_main ./sql \
  --max-files 100
```

## Contributing

To extend the analyzer:

1. **Add new SQL patterns**: Update `conn/snowflake_analyzer.py`
2. **Improve cleaning**: Modify `conn/snowflake_cleaner.py`
3. **Enhance LLM prompts**: Edit `conn/enhanced_procedure_analyzer.py`
4. **Add output formats**: Extend `conn/enhanced_json_builder.py`

## Related Files

- T-SQL version: `../tsql/tsql_main.py`
- Core utilities: `../utils/`
- Frontend integration: See main project README
