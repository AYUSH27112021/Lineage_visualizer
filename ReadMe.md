# Lineage Analyzer

A SQL data-lineage analysis system that traces table- and column-level dependencies across multiple database dialects. It can analyze raw SQL files or connect directly to a live database to extract and analyze lineage, and ships with a React UI for interactive visualization.

Supported dialects: **T-SQL (SQL Server)**, **PostgreSQL**, **Oracle**, **Teradata**, and **Snowflake**.

## Roadmap

Planned and in-progress work:

- [ ] **Broader dialect support** — extend coverage to additional engines (for example MySQL/MariaDB, BigQuery, Redshift, Databricks/Spark SQL, and DuckDB) using the existing connector pattern.
- [ ] **Stronger static analysis** — improve the parser-based pipeline with more accurate column-level resolution, deeper CTE and subquery handling, better dynamic-SQL inference, and richer transform classification, reducing reliance on best-effort fallbacks.
- [ ] **LLM-assisted static analysis** — use an LLM to complement traditional parsing where static parsing is ambiguous: resolving dynamic SQL, inferring lineage through complex expressions, and validating or enriching parser output rather than replacing it.
- [ ] **Improved stored-procedure analysis** — more reliable extraction of reads/writes, control flow, and call graphs across procedures, functions, and triggers; better handling of nested calls, parameters, and cross-object dependencies.

Contributions toward any of these are welcome.

## Features

- Two analysis modes: upload SQL files, or connect directly to a database for metadata-based analysis.
- Statement-level lineage: table-to-table dependencies, column lineage, CTEs, temp tables, and transform classification.
- Procedure-level lineage: stored procedures, functions, and triggers, including parameters, reads/writes, and call graphs.
- LLM-assisted procedure analysis via a local model (Ollama) or OpenAI.
- JSON reports plus an interactive React-based lineage visualizer.
- Command-line interface for batch and large-codebase analysis.

## Architecture

The project has three parts:

- **Backend** — a FastAPI server (`Lineage_analyzer/server.py`) exposing the analysis API.
- **Frontend** — a React application (`frontend/`) for uploading SQL, configuring connections, and viewing lineage.
- **Analyzer** — the core Python package (`Lineage_analyzer/`) usable directly from the CLI.

### Analysis modes

**File-based analysis** — SQL files are cleaned, parsed, and converted into lineage reports.
Flow: `SQL files -> Cleaner -> Analyzer -> JSON Builder -> Reports`. Entry point: `/api/analyze` or the CLI.

**Metadata-based analysis (recommended)** — connects to a database, extracts metadata, analyzes views and queries with traditional parsing, and analyzes procedures and functions with an LLM.
Flow: `Database -> Metadata Extractor -> View Analyzer + Procedure Analyzer (LLM) -> JSON Builder -> Reports`.
Entry point: `/api/analyze/metadata/{dialect}`, backed by a per-dialect `MetadataLineageOrchestrator`.

### Connector layout

Each dialect follows a consistent structure:

```
{dialect}/
  {dialect}_main.py                  # File-based entry point
  conn/                              # Metadata-based connector
    metadata_lineage_main.py         # MetadataLineageOrchestrator
    enhanced_metadata_extractor.py   # Database metadata extraction
    enhanced_procedure_analyzer.py   # LLM-based procedure analysis
    metadata_view_analyzer.py        # View/query analysis (traditional parsing)
    metadata_statement_builder.py    # Statement lineage builder
    enhanced_json_builder.py         # Final JSON report builder
```

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer (for the frontend)
- Optional, for LLM-assisted analysis:
  - [Ollama](https://ollama.com) running locally with a code model (default: `qwen2.5-coder:14b`), or
  - An OpenAI API key
- Dialect-specific database drivers (see [Dependency notes](#dependency-notes))

## Backend

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r Lineage_analyzer/requirements.txt
```

### Run

```bash
uvicorn Lineage_analyzer.server:app --host 0.0.0.0 --port 8000
```

### API endpoints

**Health**
- `GET /api/health` — health check.

**File-based analysis**
- `POST /api/analyze` — upload SQL files and analyze.
  - Query: `dialect` (`tsql` | `teradata` | `postgres` | `oracle` | `snowflake`)
  - Form data: `files` (one or more), `openai_key` (optional)
  - Returns: `statement_report`, `procedure_report`, `combined_summary`

**Metadata extraction**
- `POST /api/metadata/tsql`
- `POST /api/metadata/teradata`
- `POST /api/metadata/postgres`
- `POST /api/metadata/oracle`

  These extract database metadata and cache it in a persistent `metadata_cache/` directory for reuse.

**Metadata-based analysis (recommended)**
- `POST /api/analyze/metadata/tsql`
- `POST /api/analyze/metadata/teradata`
- `POST /api/analyze/metadata/postgres`
- `POST /api/analyze/metadata/oracle`
- `POST /api/analyze/metadata/snowflake`
- `POST /api/analyze/metadata/{dialect}` — dynamic routing by dialect

### Example request (T-SQL metadata analysis)

```json
{
  "server": "localhost",
  "database": "mydb",
  "username": "user",
  "password": "pass",
  "driver": "ODBC Driver 18 for SQL Server",
  "dialect": "tsql",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "qwen2.5-coder:14b",
  "openai_api_key": null,
  "openai_model": "gpt-4o-mini",
  "batch_size": 10,
  "timeout": 300,
  "metadata_file_path": null
}
```

## Frontend

### Setup and run

```bash
cd frontend
npm ci          # first install only
npm start
```

The UI runs on `http://localhost:3000` and expects the backend at `http://localhost:8000` by default.

### Configuration

Override the backend URL with an environment variable:

```bash
REACT_APP_BACKEND_URL=http://my-host:8000 npm start
```

### Production build

```bash
npm run build
```

The static output in `frontend/build/` can be served by any static host or reverse-proxied to the backend.

## Command-line usage

### Unified entry point

```bash
python3 -m Lineage_analyzer.main /path/to/sql \
  --output ./lineage_output \
  --dialect tsql \
  --max-files 100 \
  --debug \
  --openai-key YOUR_KEY
```

Supported dialects: `tsql`, `postgres`, `oracle`, `teradata`, `snowflake`.

### Dialect-specific entry points

```bash
python3 -m Lineage_analyzer.tsql.tsql_main           /path/to/sql --output ./out --dialect tsql
python3 -m Lineage_analyzer.postgress.postgres_main  /path/to/sql --output ./out --dialect postgres
python3 -m Lineage_analyzer.oracle.oracle_main       /path/to/sql --output ./out --dialect oracle
python3 -m Lineage_analyzer.teradata.teradata_main   /path/to/sql --output ./out --dialect teradata
python3 -m Lineage_analyzer.snowflake.snowflake_main /path/to/sql --output ./out --dialect snowflake
```

## Usage examples

### Via the UI

1. Start the backend: `uvicorn Lineage_analyzer.server:app --port 8000`
2. Start the frontend: `cd frontend && npm start`
3. In the UI, select a dialect, choose a mode (file upload or database connection), and run the analysis to view the lineage visualization.

### Via the API

File-based:

```bash
curl -X POST "http://localhost:8000/api/analyze?dialect=tsql" \
  -F "files=@script1.sql" \
  -F "files=@script2.sql"
```

Metadata-based:

```bash
curl -X POST "http://localhost:8000/api/analyze/metadata/tsql" \
  -H "Content-Type: application/json" \
  -d '{
    "server": "localhost",
    "database": "mydb",
    "username": "user",
    "password": "pass",
    "driver": "ODBC Driver 18 for SQL Server"
  }'
```

## Output reports

Each successful analysis produces three timestamped JSON reports.

**`statement_lineage_*.json`**
- Table-to-table dependencies and per-statement column lineage
- CTE definitions and references
- Temp table detection and usage
- Transform classification (aggregates, casts, calculations, window functions)
- Parse and processing statistics

**`procedure_lineage_*.json`**
- Stored procedures, functions, and triggers
- Parameters and return metadata
- Reads and writes per object
- Column references by operation (READ/WRITE/UPDATE) with statement type
- Procedure call graph and complexity metrics

**`lineage_summary_*.json`** (also emitted as `combined_summary_*.json` for file-based runs)
- High-level summary combining statement and procedure reports
- Totals for statements, tables, columns, procedures, functions, and triggers
- Temp table and CTE counts
- Derived metrics such as parse success rate
- Top referenced tables and most active procedures

## Performance and limits

- Throughput: roughly 100–500 files/min depending on complexity and dialect.
- For large codebases, use `--max-files` to sample.
- Metadata-based analysis is typically faster for databases with many objects, since it avoids file parsing overhead.
- Procedure and function analysis uses an LLM (Ollama or OpenAI) with batch processing for efficiency.

## Troubleshooting

- **Enable debug output**: pass `--debug` on the CLI, or set `"debug": true` in metadata analysis requests.
- **Connection errors**: verify database credentials and network connectivity.
- **Parse warnings**: check the summary JSON for dynamic SQL and parse fallbacks.
- **Missing objects**: ensure `CREATE` statements are present for referenced objects where possible.
- **LLM errors**: confirm Ollama is running at `http://localhost:11434`, or provide a valid OpenAI API key.

### Dependency notes

- **T-SQL**: requires an ODBC driver (for example, "ODBC Driver 18 for SQL Server").
- **PostgreSQL**: requires `psycopg2` or `psycopg2-binary`.
- **Oracle**: requires `cx_Oracle` or `oracledb`.
- **Teradata**: requires `teradatasql`.
- **Snowflake**: requires `snowflake-connector-python` (included in `requirements.txt`).

## Dialect-specific notes

- **T-SQL**: temp tables (`#temp`, `##global_temp`), `GO` batch separator, best-effort parsing of `EXEC` dynamic SQL.
- **PostgreSQL**: JSONB and arrays recognized in transforms, `pg_temp.*` temp schema, materialized views.
- **Oracle**: `DUAL` ignored as a source; supports packages, procedures, functions, triggers, materialized views, and materialized view logs.
- **Teradata**: macros, stored procedures, volatile tables, and Teradata-specific SQL extensions.
- **Snowflake**: external tables and stages, Snowflake-specific functions, and warehouse/role handling.

## General notes

- **Large uploads**: for very large folders, prefer the CLI over the API for best performance.
- **Case sensitivity**: table and column matching follows each dialect's conventions.
- **Dynamic SQL**: parsed best-effort when statically resolvable; otherwise flagged in warnings.
- **Metadata caching**: extraction results are cached in `metadata_cache/` for reuse.

For deeper details, see `ARCHITECTURE.md` and `HOW_TO_EXTEND.md`.

## License

This project is licensed under the GNU General Public License v3.0. See the [LICENSE](LICENSE) file for the full text.

Copyright (C) 2026

