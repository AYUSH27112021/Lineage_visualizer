# Oracle Lineage Analyzer

Complete Oracle lineage analysis package with file-based and metadata-based analysis.

## Directory Structure

```
oracle/
├── __init__.py
├── oracle_analyzer.py                   # Wrapper (imports from conn/)
├── oracle_cleaner.py                    # Wrapper (imports from conn/)
├── json_builder.py                      # Wrapper (imports from conn/)
├── enhanced_json_builder.py             # Wrapper (imports from conn/)
├── enhanced_procedure_analyzer.py       # Wrapper (imports from conn/)
├── oracle_main.py                       # Main entry point for file-based analysis
└── conn/                                # Implementation files
    ├── __init__.py
    ├── oracle_analyzer.py                 # Oracle SQL analyzer
    ├── oracle_cleaner.py                 # Oracle SQL cleaner
    ├── json_builder.py                  # Basic lineage JSON builder
    ├── enhanced_json_builder.py         # LLM-optimized JSON builder
    ├── enhanced_metadata_extractor.py   # Database metadata extractor
    ├── metadata_view_analyzer.py        # View analyzer (uses metadata)
    ├── metadata_statement_builder.py     # Metadata-based lineage builder
    ├── metadata_lineage_main.py         # Metadata analysis orchestrator
    └── example_usage.py                 # Usage examples
```

## Two Analysis Modes

### File-Based Analysis (No Database Connection)
Analyze Oracle SQL files directly without connecting to a database.

**Entry Point:** `oracle_main.py`

```bash
python oracle_main.py --input-dir ./sql_files --output-dir ./lineage --debug
```

**What it does:**
- Discovers all `*.sql` files in a directory
- Cleans and parses Oracle SQL
- Extracts table/column lineage
- Generates JSON lineage report

### Metadata-Based Analysis (Requires Database Connection)
Extract metadata from Oracle database and analyze views/objects.

**Entry Point:** `conn/metadata_lineage_main.py`

```bash
cd conn/
python metadata_lineage_main.py \
    --host oracle-server \
    --service-name ORCL \
    --username user \
    --password pass \
    --schemas APP_SCHEMA \
    --output-dir ./output
```

**What it does:**
- Connects to Oracle database
- Extracts comprehensive metadata (tables, views, procedures, packages)
- Analyzes view definitions
- Builds complete lineage with metadata enrichment

## Installation

```bash
pip install oracledb sqlglot
```

## Quick Start Examples

### Example 1: Analyze SQL Files
```python
from oracle.oracle_cleaner import OracleSQLCleaner
from oracle.oracle_analyzer import EnhancedSQLAnalyzer
from oracle.json_builder import EnhancedLineageJSONBuilder

cleaner = OracleSQLCleaner()
statements = cleaner.clean_file("my_script.sql")

analyzer = EnhancedSQLAnalyzer(dialect="oracle")
results = analyzer.analyze_file("my_script.sql", statements)

builder = EnhancedLineageJSONBuilder("oracle", "./sql_files")
report = builder.build_lineage_report([results])
builder.save_report(report, "lineage.json")
```

### Example 2: Extract Database Metadata
```python
from oracle.conn.enhanced_metadata_extractor import extract_enhanced_database_metadata

metadata, stats = extract_enhanced_database_metadata(
    host="oracle-server",
    service_name="ORCL",
    username="user",
    password="pass",
    target_schemas=["APP_SCHEMA"]
)

print(f"Extracted {stats['table_count']} tables")
print(f"Extracted {stats['view_count']} views")
print(f"Extracted {stats['package_count']} packages")
```

### Example 3: Complete Metadata Analysis
```python
from oracle.conn.metadata_lineage_main import MetadataLineageOrchestrator

orchestrator = MetadataLineageOrchestrator(
    host="oracle-server",
    service_name="ORCL",
    username="user",
    password="pass",
    target_schemas=["APP_SCHEMA"],
    debug=True
)

report = orchestrator.run()
```

## Oracle-Specific Features

### Supported Oracle Features:
- ✅ **PL/SQL blocks** (DECLARE, BEGIN...END)
- ✅ **Hierarchical queries** (CONNECT BY, START WITH, PRIOR, LEVEL)
- ✅ **PIVOT/UNPIVOT** operations
- ✅ **MODEL clause**
- ✅ **Flashback queries** (AS OF SCN/TIMESTAMP, VERSIONS BETWEEN)
- ✅ **MERGE statements**
- ✅ **Analytic functions** (KEEP, WITHIN GROUP)
- ✅ **Oracle functions** (DECODE, NVL, NVL2)
- ✅ **Database links** (@dblink)
- ✅ **DUAL table**
- ✅ **Oracle outer join** ((+))
- ✅ **Global temporary tables**
- ✅ **Packages** (PACKAGE, PACKAGE BODY)
- ✅ **SYS_CONNECT_BY_PATH**

## Output Format

### File-Based Analysis Output:
```json
{
  "metadata": {
    "dialect": "oracle",
    "source_directory": "./sql_files",
    "version": "2.0"
  },
  "summary": {
    "total_scripts": 10,
    "total_tables": 25,
    "total_columns": 150,
    "global_temp_tables": 3,
    "ctes": 5
  },
  "tables": { ... },
  "columns": { ... },
  "execution_order": { ... }
}
```

### Metadata-Based Analysis Output:
```json
{
  "metadata": {
    "database_name": "ORCL",
    "source_type": "database_metadata"
  },
  "summary": {
    "total_views": 50,
    "total_tables": 100,
    "total_columns": 800
  },
  "tables": { ... },
  "columns": { ... },
  "execution_order": { ... }
}
```

## Wrapper Pattern

The parent `oracle/` folder contains wrapper files that re-export from `conn/`:

```python
# oracle/oracle_analyzer.py (wrapper)
from .conn.oracle_analyzer import EnhancedSQLAnalyzer
__all__ = ['EnhancedSQLAnalyzer']

# Allows importing as:
from oracle.oracle_analyzer import EnhancedSQLAnalyzer
# Instead of:
from oracle.conn.oracle_analyzer import EnhancedSQLAnalyzer
```

**Why?** This structure:
- ✅ Keeps implementation files organized in `conn/`
- ✅ Provides clean import paths for users
- ✅ Separates connection-capable code (in `conn/`) from wrapper code
- ✅ Matches Teradata and MSSQL structure

## Usage Scenarios

### Scenario 1: Migrate SQL Files to Another Database
```bash
python oracle_main.py --input-dir ./legacy_sql --output-dir ./analysis
```

### Scenario 2: Document Existing Database
```bash
cd conn/
python metadata_lineage_main.py \
    --host prod-db \
    --service-name PROD \
    --username readonly \
    --schemas APP,FINANCE,HR \
    --output-dir ./documentation
```

### Scenario 3: Impact Analysis
```python
from oracle.json_builder import EnhancedLineageJSONBuilder
import json

with open('lineage.json') as f:
    report = json.load(f)

target_table = "CUSTOMERS"
dependencies = report['execution_order']['execution_order']
affected = [t for t in dependencies if target_table in report['tables'][t]['depends_on']]
print(f"Tables affected by changing {target_table}: {affected}")
```

## Additional Resources

- **Full Documentation:** See `conn/IMPLEMENTATION_SUMMARY.md`
- **Usage Examples:** See `conn/example_usage.py`

## Important Notes

1. **Database Connection:**
   - File-based analysis: No connection needed
   - Metadata-based analysis: Requires `oracledb` and database credentials

2. **Performance:**
   - File-based: Fast, no network overhead
   - Metadata-based: Depends on database size and network

3. **Accuracy:**
   - File-based: Limited to SQL file content
   - Metadata-based: Complete with actual column types, constraints

## Troubleshooting

### Import Error
```python
# Wrong
from oracle_analyzer import EnhancedSQLAnalyzer  # ❌

# Correct
from oracle.oracle_analyzer import EnhancedSQLAnalyzer  # ✅
# or
from oracle.conn.oracle_analyzer import EnhancedSQLAnalyzer  # ✅
```

### Connection Error
```bash
pip install oracledb
python -c "import oracledb; print('OK')"
```
