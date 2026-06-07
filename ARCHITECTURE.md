# Lineage Analyzer Architecture

## Overview

The Lineage Analyzer is a multi-dialect SQL lineage analysis system with a dual-mode architecture supporting both file-based and metadata-based analysis. The system is designed with a modular connector pattern that allows easy extension to new database dialects.

---

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                         │
│  - File Upload UI                                                │
│  - Database Connection UI                                       │
│  - Lineage Visualization                                        │
└────────────────────────────┬────────────────────────────────────┘
                              │
                              │ HTTP/REST API
                              │
┌─────────────────────────────▼────────────────────────────────────┐
│                    FastAPI Server (server.py)                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Route Handlers:                                         │  │
│  │  - /api/analyze (file-based)                             │  │
│  │  - /api/analyze/metadata/{dialect} (metadata-based)      │  │
│  │  - /api/metadata/{dialect} (metadata extraction)         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────┬───────────────────────────────┬───────────────────┘
              │                               │
              │                               │
    ┌─────────▼─────────┐         ┌──────────▼──────────┐
    │  File-based Path  │         │ Metadata-based Path │
    │  (main.py)        │         │ (conn/ modules)     │
    └─────────┬─────────┘         └──────────┬──────────┘
              │                               │
              │                               │
    ┌─────────▼───────────────────────────────▼──────────┐
    │         Dialect-Specific Analyzers                 │
    │  - T-SQL, PostgreSQL, Oracle, Teradata, Snowflake │
    └────────────────────────────────────────────────────┘
```

---

## Dual-Mode Architecture

### Mode 1: File-based Analysis

**Purpose**: Analyze SQL files uploaded by users or from a directory.

**Flow**:
```
SQL Files
    ↓
Cleaner (removes noise, splits batches)
    ↓
Statement Analyzer (parses SQL, extracts lineage)
    ↓
Procedure Analyzer (analyzes stored procedures/functions)
    ↓
JSON Builders (aggregates, deduplicates, calculates metrics)
    ↓
Three JSON Reports
```

**Entry Points**:
- **API**: `POST /api/analyze?dialect={dialect}`
- **CLI**: `python3 -m Lineage_analyzer.main /path/to/sql --dialect {dialect}`

**Components**:
- `main.py` - Unified dispatcher
- `{dialect}/{dialect}_main.py` - Dialect-specific entry points
- `{dialect}/{dialect}_cleaner.py` - File cleaning and normalization
- `{dialect}/{dialect}_analyzer.py` - SQL parsing and lineage extraction
- `{dialect}/{dialect}_json_builder.py` - Report generation

### Mode 2: Metadata-based Analysis (Recommended)

**Purpose**: Connect directly to databases to extract and analyze lineage from live database objects.

**Flow**:
```
Database Connection
    ↓
Enhanced Metadata Extractor (extracts schema metadata)
    ↓
    ├─→ Metadata View Analyzer (analyzes views/queries with traditional parsing)
    └─→ Enhanced Procedure Analyzer (analyzes procedures/functions with LLM)
    ↓
Metadata Statement Builder (builds statement lineage)
    ↓
Enhanced JSON Builder (generates reports)
    ↓
Three JSON Reports (same format as file-based)
```

**Entry Points**:
- **API**: `POST /api/analyze/metadata/{dialect}`
- **CLI**: Direct instantiation of `MetadataLineageOrchestrator`

**Components**:
- `{dialect}/conn/metadata_lineage_main.py` - `MetadataLineageOrchestrator` class
- `{dialect}/conn/enhanced_metadata_extractor.py` - Database metadata extraction
- `{dialect}/conn/metadata_view_analyzer.py` - View/query analysis
- `{dialect}/conn/enhanced_procedure_analyzer.py` - LLM-based procedure analysis
- `{dialect}/conn/metadata_statement_builder.py` - Statement lineage builder
- `{dialect}/conn/enhanced_json_builder.py` - Final JSON report builder

---

## Server Routing Pattern

### Request Flow

The FastAPI server (`server.py`) routes requests based on endpoint and dialect:

#### 1. File-based Analysis Routing

```python
POST /api/analyze?dialect={dialect}
    ↓
server.py: analyze_directory()
    ↓
main.py dispatcher:
    - run_tsql() → tsql/tsql_main.py
    - run_postgres() → postgress/postgres_main.py
    - run_oracle() → oracle/oracle_main.py
    - run_teradata() → teradata/teradata_main.py
    - run_snowflake() → snowflake/snowflake_main.py
```

#### 2. Metadata-based Analysis Routing

```python
POST /api/analyze/metadata/{dialect}
    ↓
server.py: analyze_metadata_dynamic() or dialect-specific handler
    ↓
Import from {dialect}/conn/metadata_lineage_main:
    - TsqlMetadataLineageOrchestrator
    - PostgresMetadataLineageOrchestrator
    - OracleMetadataLineageOrchestrator
    - TeradataMetadataLineageOrchestrator
    - SnowflakeMetadataLineageOrchestrator
    ↓
orchestrator.run_full_analysis()
```

#### 3. Metadata Extraction Routing

```python
POST /api/metadata/{dialect}
    ↓
server.py: extract_{dialect}_metadata()
    ↓
Import from {dialect}/conn/enhanced_metadata_extractor:
    - extract_tsql_enhanced_metadata()
    - extract_postgres_enhanced_metadata()
    - extract_oracle_enhanced_metadata()
    - extract_teradata_enhanced_metadata()
    ↓
Extract and cache metadata to metadata_cache/ directory
```

---

## Connector Pattern

### Directory Structure

Each database dialect follows a consistent structure:

```
Lineage_analyzer/
├── main.py                          # Unified file-based dispatcher
├── server.py                        # FastAPI server with routing
│
├── {dialect}/                       # Dialect-specific modules
│   ├── {dialect}_main.py           # File-based entry point
│   ├── {dialect}_cleaner.py        # File cleaning
│   ├── {dialect}_analyzer.py       # SQL parsing
│   ├── {dialect}_json_builder.py   # Report generation
│   │
│   └── conn/                       # Metadata-based connector
│       ├── metadata_lineage_main.py      # MetadataLineageOrchestrator
│       ├── enhanced_metadata_extractor.py # Database metadata extraction
│       ├── enhanced_procedure_analyzer.py # LLM-based procedure analysis
│       ├── metadata_view_analyzer.py     # View/query analysis
│       ├── metadata_statement_builder.py # Statement lineage builder
│       └── enhanced_json_builder.py       # Final JSON builder
│
├── tsql/
│   ├── tsql_main.py
│   └── conn/
│       └── mssql_conn/
│           └── metadata_lineage_main.py
│
├── postgress/
│   ├── postgres_main.py
│   └── conn/
│       └── metadata_lineage_main.py
│
├── oracle/
│   ├── oracle_main.py
│   └── conn/
│       └── metadata_lineage_main.py
│
├── teradata/
│   ├── teradata_main.py
│   └── conn/
│       └── metadata_lineage_main.py
│
└── snowflake/
    ├── snowflake_main.py
    └── conn/ (or root level)
        └── metadata_lineage_main.py
```

### MetadataLineageOrchestrator Pattern

Each dialect implements a `MetadataLineageOrchestrator` class with a consistent interface:

```python
class MetadataLineageOrchestrator:
    def __init__(
        self,
        # Database connection parameters (dialect-specific)
        # Output configuration
        output_directory: str,
        dialect: str,
        debug: bool,
        # LLM Configuration
        ollama_url: str,
        ollama_model: str,
        openai_api_key: Optional[str],
        openai_model: str,
        batch_size: int,
        timeout: int,
        # Optional: Pre-loaded metadata
        metadata_file_path: Optional[str],
    ):
        # Initialize components
        
    def run_full_analysis(self) -> Dict:
        """
        Main orchestration method:
        1. Extract or load metadata
        2. Analyze views/queries (traditional parsing)
        3. Analyze procedures/functions (LLM)
        4. Build statement lineage
        5. Generate JSON reports
        6. Return results
        """
        pass
```

---

## Component Interactions

### File-based Analysis Flow

```
┌──────────────┐
│   .sql file  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────┐
│  Cleaner                 │  Reads file, removes noise
│  • Splits batches        │  Separates object types
│  • Removes comments      │
└──────┬───────────────────┘
       │
       ├──────────────────────────────┬──────────────────────────────┐
       │                              │                              │
       ▼                              ▼                              ▼
┌──────────────┐            ┌──────────────┐            ┌──────────────┐
│ Statements   │            │ Procedures   │            │ Functions    │
└──────┬───────┘            └──────┬───────┘            └──────┬───────┘
       │                           │                           │
       ▼                           ▼                           ▼
┌──────────────┐            ┌──────────────────────────────────────────┐
│ Statement    │            │ Procedure/Function Analyzer             │
│ Analyzer     │            │ • Parse proc body                        │
│ • Parse SQL  │      |---->│ • Extract params                         │
│ • Extract    │      |     │ • Analyze statements                     │
│   lineage    │      |     │ • Build call graph                       │
└──────┬───────┘      |     └──────┬───────────────────────────────────┘
       │              |            │
       └──────────┬───|─────────────┘
                  │
                  ▼
       ┌──────────────────────┐
       │  JSON Builders       │
       │  • Aggregate         │
       │  • Deduplicate       │
       │  • Calculate metrics │
       └──────────┬───────────┘
                  │
                  ▼
       ┌──────────────────────┐
       │  JSON Reports        │
       │  (3 files generated) │
       └──────────────────────┘
```

### Metadata-based Analysis Flow

```
┌──────────────────────┐
│  Database Connection │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────────────────┐
│  Enhanced Metadata Extractor      │
│  • Tables, views, procedures      │
│  • Columns, constraints, indexes   │
│  • Query history (if available)  │
│  • Saves to metadata_cache/       │
└──────────┬────────────────────────┘
           │
           ├──────────────────────────────┬──────────────────────────────┐
           │                              │                              │
           ▼                              ▼                              ▼
┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
│ Metadata View Analyzer    │  │ Enhanced Procedure        │  │ Metadata Statement       │
│ • Views                   │  │ Analyzer (LLM)           │  │ Builder                  │
│ • Materialized views      │  │ • Procedures             │  │ • Combines view + proc    │
│ • Query history           │  │ • Functions               │  │   lineage                │
│ • Traditional parsing     │  │ • Triggers                │  │ • Resolves references    │
│   (sqlglot)               │  │ • Packages                │  │ • Builds column lineage   │
└──────────┬─────────────────┘  └──────────┬───────────────┘  └──────────┬───────────────┘
           │                                │                            │
           └────────────────────────────────┴────────────────────────────┘
                                          │
                                          ▼
                           ┌──────────────────────────────┐
                           │  Enhanced JSON Builder       │
                           │  • Aggregates results        │
                           │  • Deduplicates              │
                           │  • Calculates metrics        │
                           │  • Generates 3 JSON reports  │
                           └──────────┬───────────────────┘
                                      │
                                      ▼
                           ┌──────────────────────────────┐
                           │  JSON Reports                │
                           │  (same format as file-based) │
                           └──────────────────────────────┘
```

---

## Data Flow Example

### Example: Customer Analysis Procedure

**Input**: T-SQL procedure `usp_GetCustomerStats`

```sql
CREATE PROCEDURE usp_GetCustomerStats (@CustomerID INT OUTPUT)
AS
BEGIN
    INSERT INTO summary_stats
    SELECT 
        customer_id,
        SUM(amount) as total_amount
    FROM orders
    WHERE customer_id = @CustomerID
    GROUP BY customer_id;
END
```

**Processing**:

1. **Metadata Extraction**:
   - Extracts procedure definition
   - Extracts table schemas: `orders`, `summary_stats`
   - Extracts column metadata

2. **Procedure Analysis (LLM)**:
   - Analyzes procedure body
   - Identifies: `INSERT INTO summary_stats`
   - Identifies: `SELECT FROM orders`
   - Extracts column mappings:
     - `summary_stats.customer_id ← orders.customer_id`
     - `summary_stats.total_amount ← orders.amount` (aggregate: SUM)

3. **Statement Lineage Building**:
   - Creates edge: `orders → summary_stats`
   - Creates column edges with transform information

4. **JSON Output**:
   ```json
   {
     "procedures": [{
       "name": "usp_GetCustomerStats",
       "parameters": [{"name": "@CustomerID", "type": "INT", "direction": "OUTPUT"}],
       "writes_tables": ["summary_stats"],
       "reads_tables": ["orders"],
       "column_references": [
         {"table": "orders", "column": "customer_id", "operation": "READ"},
         {"table": "orders", "column": "amount", "operation": "READ"},
         {"table": "summary_stats", "column": "customer_id", "operation": "WRITE"},
         {"table": "summary_stats", "column": "total_amount", "operation": "WRITE"}
       ]
     }],
     "edges": [{
       "source": "orders.customer_id",
       "target": "summary_stats.customer_id",
       "transform": "direct"
     }, {
       "source": "orders.amount",
       "target": "summary_stats.total_amount",
       "transform": "aggregate",
       "aggregate_function": "SUM"
     }]
   }
   ```

---

## API Endpoint Summary

### File-based Endpoints

| Endpoint | Method | Purpose | Input |
|----------|--------|---------|-------|
| `/api/analyze` | POST | Analyze uploaded SQL files | `files`, `dialect` (query param) |

### Metadata Extraction Endpoints

| Endpoint | Method | Purpose | Input |
|----------|--------|---------|-------|
| `/api/metadata/tsql` | POST | Extract SQL Server metadata | Connection info |
| `/api/metadata/teradata` | POST | Extract Teradata metadata | Connection info |
| `/api/metadata/postgres` | POST | Extract PostgreSQL metadata | Connection info |
| `/api/metadata/oracle` | POST | Extract Oracle metadata | Connection info |

### Metadata-based Analysis Endpoints

| Endpoint | Method | Purpose | Input |
|----------|--------|---------|-------|
| `/api/analyze/metadata/tsql` | POST | Analyze SQL Server database | Connection info + LLM config |
| `/api/analyze/metadata/teradata` | POST | Analyze Teradata database | Connection info + LLM config |
| `/api/analyze/metadata/postgres` | POST | Analyze PostgreSQL database | Connection info + LLM config |
| `/api/analyze/metadata/oracle` | POST | Analyze Oracle database | Connection info + LLM config |
| `/api/analyze/metadata/snowflake` | POST | Analyze Snowflake database | Connection info + LLM config |
| `/api/analyze/metadata/{dialect}` | POST | Dynamic routing by dialect | Connection info + LLM config |

### Utility Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Health check |

---

## Output JSON Structure

### Common Format (Both Modes)

All analysis modes produce the same three JSON reports:

1. **`statement_lineage_*.json`**:
   - `nodes`: Tables, views, temp tables
   - `columns`: Per-table column lists
   - `edges`: Column-level lineage with transforms
   - `metadata`: Dialect, stats, warnings

2. **`procedure_lineage_*.json`**:
   - `procedures`: Stored procedures, functions, triggers
   - `parameters`: Procedure/function parameters
   - `reads_tables`, `writes_tables`: Table access
   - `column_references`: Column-level operations (READ/WRITE/UPDATE)
   - `call_graph`: Procedure dependencies

3. **`lineage_summary_*.json`** (or `combined_summary_*.json`):
   - `totals`: Counts of objects
   - `top_tables`: Most referenced tables
   - `top_procedures`: Most active procedures
   - `metrics`: Parse success rate, complexity metrics
   - `warnings`: Parse errors, dynamic SQL flags

---

## Extension Points

### Adding a New Dialect

1. **Create dialect directory structure**:
   ```
   {new_dialect}/
   ├── {new_dialect}_main.py
   ├── {new_dialect}_cleaner.py
   ├── {new_dialect}_analyzer.py
   ├── {new_dialect}_json_builder.py
   └── conn/
       ├── metadata_lineage_main.py
       ├── enhanced_metadata_extractor.py
       ├── enhanced_procedure_analyzer.py
       ├── metadata_view_analyzer.py
       ├── metadata_statement_builder.py
       └── enhanced_json_builder.py
   ```

2. **Implement file-based components**:
   - Cleaner, analyzer, JSON builder

3. **Implement metadata-based components**:
   - `MetadataLineageOrchestrator` class
   - Metadata extractor
   - View analyzer
   - Procedure analyzer (LLM-based)

4. **Register in server.py**:
   - Add request models
   - Add metadata extraction endpoint
   - Add metadata analysis endpoint
   - Add routing logic

5. **Register in main.py**:
   - Add `run_{new_dialect}()` function
   - Add routing in `main()`

See `HOW_TO_EXTEND.md` for detailed extension guidelines.

---

## Performance Considerations

### File-based Analysis
- **Throughput**: ~100-500 files/min
- **Bottlenecks**: File I/O, SQL parsing
- **Optimization**: Parallel file processing, caching parsed results

### Metadata-based Analysis
- **Throughput**: Depends on database size and LLM processing
- **Bottlenecks**: Database queries, LLM API calls
- **Optimization**: 
  - Metadata caching (saved to `metadata_cache/`)
  - Batch LLM processing
  - Parallel view analysis

### LLM Processing
- **Models**: Ollama (local) or OpenAI (cloud)
- **Batch Size**: Configurable (default: 10)
- **Timeout**: Configurable (default: 300s)
- **Use Case**: Procedures, functions, packages, triggers

---

## Security Considerations

- **Credentials**: Never logged or exposed in responses
- **Connection Strings**: Passed securely to database drivers
- **File Uploads**: Stored in temporary directories, cleaned after processing
- **Metadata Cache**: Contains schema information only (no data)

---

## Future Enhancements

- Additional database dialects (MySQL, DB2, etc.)
- Incremental analysis (track changes over time)
- Real-time lineage updates
- Advanced visualization features
- Integration with data catalog tools
