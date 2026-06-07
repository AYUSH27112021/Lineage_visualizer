from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional
import tempfile
from pathlib import Path
import shutil
import os
import json
import logging
import traceback
import subprocess
import sys
from pydantic import BaseModel, Field

"""Server routes that run the analyzer and return JSON results.
"""

# Import main dispatcher helpers
try:
    from . import main as analyzer_entry
    from .tsql.mssql_conn import (
        MetadataLineageOrchestrator as TsqlMetadataLineageOrchestrator,
        extract_enhanced_database_metadata as extract_tsql_enhanced_metadata,
    )
    from .snowflake import MetadataLineageOrchestrator as SnowflakeMetadataLineageOrchestrator
    from .teradata.conn.metadata_lineage_main import (
        MetadataLineageOrchestrator as TeradataMetadataLineageOrchestrator,
    )
    from .teradata.conn.enhanced_metadata_extractor import (
        extract_enhanced_database_metadata as extract_teradata_enhanced_metadata,
    )
    from .postgress.conn.metadata_lineage_main import (
        MetadataLineageOrchestrator as PostgresMetadataLineageOrchestrator,
    )
    from .postgress.conn.enhanced_metadata_extractor import (
        extract_enhanced_database_metadata as extract_postgres_enhanced_metadata,
    )
    from .oracle.conn.metadata_lineage_main import (
        MetadataLineageOrchestrator as OracleMetadataLineageOrchestrator,
    )
    from .oracle.conn.enhanced_metadata_extractor import (
        extract_enhanced_database_metadata as extract_oracle_enhanced_metadata,
    )
except ImportError:
    import sys as _sys
    _sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from Lineage_analyzer import main as analyzer_entry
    from Lineage_analyzer.tsql.mssql_conn import (
        MetadataLineageOrchestrator as TsqlMetadataLineageOrchestrator,
        extract_enhanced_database_metadata as extract_tsql_enhanced_metadata,
    )
    from Lineage_analyzer.snowflake import MetadataLineageOrchestrator as SnowflakeMetadataLineageOrchestrator
    from Lineage_analyzer.teradata.conn.metadata_lineage_main import (
        MetadataLineageOrchestrator as TeradataMetadataLineageOrchestrator,
    )
    from Lineage_analyzer.teradata.conn.enhanced_metadata_extractor import (
        extract_enhanced_database_metadata as extract_teradata_enhanced_metadata,
    )
    from Lineage_analyzer.postgress.conn.metadata_lineage_main import (
        MetadataLineageOrchestrator as PostgresMetadataLineageOrchestrator,
    )
    from Lineage_analyzer.postgress.conn.enhanced_metadata_extractor import (
        extract_enhanced_database_metadata as extract_postgres_enhanced_metadata,
    )
    from Lineage_analyzer.oracle.conn.metadata_lineage_main import (
        MetadataLineageOrchestrator as OracleMetadataLineageOrchestrator,
    )
    from Lineage_analyzer.oracle.conn.enhanced_metadata_extractor import (
        extract_enhanced_database_metadata as extract_oracle_enhanced_metadata,
    )


app = FastAPI(title="SQL Lineage Backend")
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger("lineage_server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TsqlConnectionInfo(BaseModel):
    server: str = Field(..., description="SQL Server host, host:port, or host\\instance")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    driver: str = Field("ODBC Driver 18 for SQL Server", description="ODBC driver name")
    dialect: str | None = Field(default=None, description="Optional dialect override")


class TsqlMetadataAnalysisRequest(BaseModel):
    """Request model for metadata-based lineage analysis with direct database connection."""
    server: str = Field(..., description="SQL Server host, host:port, or host\\instance")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    driver: str = Field("ODBC Driver 18 for SQL Server", description="ODBC driver name")
    dialect: str = Field("tsql", description="SQL dialect (default: tsql)")
    # LLM Configuration
    ollama_url: Optional[str] = Field("http://localhost:11434", description="Ollama API URL")
    ollama_model: Optional[str] = Field("qwen2.5-coder:14b", description="Ollama model name")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key (uses OpenAI if provided)")
    openai_model: Optional[str] = Field("gpt-4o-mini", description="OpenAI model name")
    batch_size: int = Field(10, description="Parallel processing batch size")
    timeout: int = Field(300, description="Request timeout in seconds")
    # Optional: Pre-extracted metadata file path
    metadata_file_path: Optional[str] = Field(None, description="Path to pre-extracted metadata JSON file")


class SnowflakeMetadataAnalysisRequest(BaseModel):
    """Request model for Snowflake metadata-based lineage analysis."""
    account: str = Field(..., description="Snowflake account identifier (with or without domain)")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Login username")
    password: str = Field("", description="Login password (leave blank for externalbrowser)")
    warehouse: Optional[str] = Field("COMPUTE_WH", description="Warehouse to use")
    role: Optional[str] = Field("", description="Role to assume")
    authenticator: str = Field("externalbrowser", description="Authenticator (externalbrowser, snowflake, etc.)")
    dialect: str = Field("snowflake", description="SQL dialect (default: snowflake)")
    output_directory: Optional[str] = Field(None, description="Optional output directory override")
    debug: bool = Field(False, description="Enable debug logs")
    ollama_url: Optional[str] = Field("http://localhost:11434", description="Ollama API URL")
    ollama_model: Optional[str] = Field("qwen2.5-coder:14b", description="Ollama model name")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    openai_model: Optional[str] = Field("gpt-4o-mini", description="OpenAI model name")
    batch_size: int = Field(10, description="Parallel LLM batch size")
    timeout: int = Field(300, description="LLM timeout in seconds")
    metadata_file_path: Optional[str] = Field(None, description="Optional metadata cache file to reuse")


class TeradataConnectionInfo(BaseModel):
    host: str = Field(..., description="Teradata server hostname or IP")
    database: str = Field(..., description="Default database name (user database)")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    logmech: str = Field("TD2", description="Authentication mechanism (TD2, LDAP, etc.)")
    encryptdata: bool = Field(True, description="Enable data encryption")
    charset: str = Field("UTF8", description="Session character set")
    tmode: str = Field("ANSI", description="Transaction mode (ANSI or TERA)")


class TeradataMetadataAnalysisRequest(BaseModel):
    """Request model for Teradata metadata-based lineage analysis."""
    host: str = Field(..., description="Teradata server hostname or IP")
    database: str = Field(..., description="Default database name")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    logmech: str = Field("TD2", description="Authentication mechanism")
    encryptdata: bool = Field(True, description="Enable data encryption")
    charset: str = Field("UTF8", description="Session character set")
    tmode: str = Field("ANSI", description="Transaction mode")
    dialect: str = Field("teradata", description="SQL dialect (default: teradata)")
    debug: bool = Field(False, description="Enable debug logging")
    ollama_url: Optional[str] = Field("http://localhost:11434", description="Ollama API URL")
    ollama_model: Optional[str] = Field("qwen2.5-coder:14b", description="Ollama model name")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    openai_model: Optional[str] = Field("gpt-4o-mini", description="OpenAI model name")
    batch_size: int = Field(10, description="Parallel processing batch size")
    timeout: int = Field(300, description="LLM timeout in seconds")
    metadata_file_path: Optional[str] = Field(None, description="Path to cached metadata JSON file")
    output_directory: Optional[str] = Field(None, description="Optional output directory override")


class PostgresConnectionInfo(BaseModel):
    host: str = Field(..., description="PostgreSQL server hostname or IP")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    port: int = Field(5432, description="PostgreSQL port")


class PostgresMetadataAnalysisRequest(BaseModel):
    host: str = Field(..., description="PostgreSQL server hostname or IP")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    port: int = Field(5432, description="PostgreSQL port")
    dialect: str = Field("postgres", description="SQL dialect (default: postgres)")
    debug: bool = Field(False, description="Enable debug logs")
    ollama_url: Optional[str] = Field("http://localhost:11434", description="Ollama API URL")
    ollama_model: Optional[str] = Field("qwen2.5-coder:14b", description="Ollama model name")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    openai_model: Optional[str] = Field("gpt-4o-mini", description="OpenAI model name")
    batch_size: int = Field(10, description="Parallel processing batch size")
    timeout: int = Field(300, description="LLM timeout in seconds")
    metadata_file_path: Optional[str] = Field(None, description="Path to cached metadata JSON file")
    output_directory: Optional[str] = Field(None, description="Optional output directory override")


class OracleConnectionInfo(BaseModel):
    host: str = Field(..., description="Oracle server hostname or IP")
    service_name: str = Field(..., description="Oracle service name/SID")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    port: int = Field(1521, description="Oracle port")
    target_schemas: Optional[List[str]] = Field(
        None, description="Optional list of schemas to extract (defaults to user schema)"
    )


class OracleMetadataAnalysisRequest(BaseModel):
    host: str = Field(..., description="Oracle server hostname or IP")
    service_name: str = Field(..., description="Oracle service name/SID")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    port: int = Field(1521, description="Oracle port")
    target_schemas: Optional[List[str]] = Field(
        None, description="Optional list of schemas to include in analysis"
    )
    dialect: str = Field("oracle", description="SQL dialect (default: oracle)")
    debug: bool = Field(False, description="Enable debug logging")
    ollama_url: Optional[str] = Field("http://localhost:11434", description="Ollama API URL")
    ollama_model: Optional[str] = Field("qwen2.5-coder:14b", description="Ollama model name")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    openai_model: Optional[str] = Field("gpt-4o-mini", description="OpenAI model name")
    batch_size: int = Field(10, description="Parallel processing batch size")
    timeout: int = Field(300, description="LLM timeout in seconds")
    metadata_file_path: Optional[str] = Field(None, description="Path to cached metadata JSON file")
    output_directory: Optional[str] = Field(None, description="Optional output directory override")


@app.post("/api/metadata/tsql")
async def extract_tsql_metadata(info: TsqlConnectionInfo):
    """Extract database metadata for Microsoft SQL Server and persist it for lineage analysis.
    
    Uses the enhanced metadata extractor which saves to a persistent metadata_cache directory.
    """

    try:
        # Extract metadata using the enhanced extractor
        # output_dir=None uses the default metadata_cache directory (persistent)
        metadata, file_path = extract_tsql_enhanced_metadata(
            server=info.server,
            database=info.database,
            username=info.username,
            password=info.password,
            driver=info.driver,
            output_dir=None,  # Uses default metadata_cache directory
        )
        
        response_payload = {
            "status": "success",
            "saved_to": str(file_path),
            "summary": metadata.get("summary", {}),
            "database": metadata.get("database", {}),
        }
        
        return JSONResponse(response_payload)
            
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - runtime safeguard
        logger.exception("Metadata extraction failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/metadata/teradata")
async def extract_teradata_metadata(info: TeradataConnectionInfo):
    """Extract database metadata for Teradata and persist it for lineage analysis."""
    try:
        metadata, file_path = extract_teradata_enhanced_metadata(
            host=info.host,
            database=info.database,
            username=info.username,
            password=info.password,
            logmech=info.logmech,
            encryptdata=info.encryptdata,
            charset=info.charset,
            tmode=info.tmode,
            output_dir=None,
        )

        response_payload = {
            "status": "success",
            "saved_to": str(file_path),
            "summary": metadata.get("summary", {}),
            "database": metadata.get("database", {}),
        }
        return JSONResponse(response_payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - runtime safeguard
        logger.exception("Teradata metadata extraction failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/metadata/postgres")
async def extract_postgres_metadata(info: PostgresConnectionInfo):
    """Extract database metadata for PostgreSQL and persist it for lineage analysis."""
    try:
        if extract_postgres_enhanced_metadata is None:
            raise HTTPException(status_code=500, detail="PostgreSQL metadata extractor is not available on the server")

        metadata, file_path = extract_postgres_enhanced_metadata(
            host=info.host,
            database=info.database,
            username=info.username,
            password=info.password,
            port=info.port,
            output_dir=None,
        )

        response_payload = {
            "status": "success",
            "saved_to": str(file_path),
            "summary": metadata.get("summary", {}),
            "database": metadata.get("database", {}),
        }
        return JSONResponse(response_payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("PostgreSQL metadata extraction failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/metadata/oracle")
async def extract_oracle_metadata(info: OracleConnectionInfo):
    """Extract database metadata for Oracle and persist it for lineage analysis."""
    try:
        if extract_oracle_enhanced_metadata is None:
            raise HTTPException(status_code=500, detail="Oracle metadata extractor is not available on the server")

        metadata, file_path = extract_oracle_enhanced_metadata(
            host=info.host,
            service_name=info.service_name,
            username=info.username,
            password=info.password,
            port=info.port,
            output_dir=None,
            target_schemas=info.target_schemas,
        )

        response_payload = {
            "status": "success",
            "saved_to": str(file_path),
            "summary": metadata.get("summary", {}),
            "database": metadata.get("database", {}),
        }
        return JSONResponse(response_payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("Oracle metadata extraction failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/analyze")
async def analyze_directory(
    files: List[UploadFile] = File(...),
    dialect: str = Query("tsql", description="SQL dialect: tsql | teradata | postgres | oracle | mysql | sqlite"),
    openai_key: Optional[str] = Form(None, description="OpenAI API key (optional, uses Ollama if not provided)")
):
    """Accept a folder upload (multiple files), run lineage via main, return report JSON.

    Stores analyzer outputs in a dedicated temporary folder and returns the
    parsed JSON content to the frontend.
    """
    # Create a temp directory to reconstruct the uploaded folder
    logger.info("/api/analyze called: dialect=%s, files=%d", dialect, len(files))
    with tempfile.TemporaryDirectory() as tmp_dir:
        base = Path(tmp_dir)
        logger.info("Working directory: %s", base)
        for uf in files:
            rel_path = Path(uf.filename)
            target_path = base / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("wb") as out_f:
                shutil.copyfileobj(uf.file, out_f)
        logger.info("Saved uploaded files to temp directory")

        # Create a specific temp output directory
        output_dir = base / "lineage_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Run analyzer via main dispatcher on the reconstructed directory
        try:
            d = dialect.lower()
            logger.info("Dispatching analyzer for dialect: %s", d)
            if d in {"tsql", "mssql", "mysql", "sqlite"}:
                exit_code = analyzer_entry.run_tsql(
                    sql_directory=str(base),
                    output=str(output_dir),
                    dialect="tsql",
                    max_files=None,
                    debug=False,
                    openai_key=openai_key if openai_key else None,
                )
            elif d in {"teradata"}:
                exit_code = analyzer_entry.run_teradata(
                    sql_directory=str(base),
                    output=str(output_dir),
                    dialect="teradata",
                    max_files=None,
                    debug=False,
                    openai_key=openai_key if openai_key else None,
                )
            elif d in {"postgres", "postgresql", "pgsql", "postgress"}:
                exit_code = analyzer_entry.run_postgres(
                    sql_directory=str(base),
                    output=str(output_dir),
                    dialect="postgres",
                    max_files=None,
                    debug=False,
                )
            elif d in {"oracle"}:
                exit_code = analyzer_entry.run_oracle(
                    sql_directory=str(base),
                    output=str(output_dir),
                    dialect="oracle",
                    max_files=None,
                    debug=False,
                )
            elif d in {"snowflake"}:
                exit_code = analyzer_entry.run_snowflake(
                    sql_directory=str(base),
                    output=str(output_dir),
                    dialect="snowflake",
                    max_files=None,
                    debug=False,
                    openai_key=openai_key if openai_key else None,
                )
            else:
                raise HTTPException(status_code=501, detail=f"Dialect '{dialect}' not implemented on server yet")

            if exit_code != 0:
                logger.error("Analyzer exited with code %s", exit_code)
                raise HTTPException(status_code=500, detail=f"Analyzer exited with code {exit_code}")

            # Load generated JSON reports from output_dir
            def _latest_path(pattern: str) -> Path | None:
                files = sorted(output_dir.glob(pattern))
                return files[-1] if files else None

            def _load_json(path: Path | None) -> dict:
                if not path or not path.exists():
                    return {}
                try:
                    with path.open("r", encoding="utf-8") as f:
                        return json.load(f)
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to parse JSON file %s: %s", path, exc)
                    return {}

            statement_path = _latest_path("statement_lineage_*.json")
            summary_path = _latest_path("combined_summary_*.json")
            procedure_path = _latest_path("procedure_lineage_*.json")
            
            all_files = list(output_dir.glob("*.json"))
            logger.info("Available JSON files in output: %s", [f.name for f in all_files])
            logger.info("Looking for procedure_lineage_*.json, found: %s", procedure_path)

            statement_report = _load_json(statement_path)
            procedure_report = _load_json(procedure_path)
            combined_summary = _load_json(summary_path)

            logger.info(
                "Loaded reports: statements=%s (path: %s), procedures=%s (path: %s), summary=%s (path: %s)",
                bool(statement_report), statement_path,
                bool(procedure_report), procedure_path,
                bool(combined_summary), summary_path,
            )
            
            if not procedure_report and statement_report:
                logger.warning("Procedure report is empty but statement report exists. Procedure lineage may not display.")

            response_files = {
                "statements": str(statement_path or ""),
                "procedures": str(procedure_path or ""),
                "summary": str(summary_path or ""),
            }

            # Include any other notable outputs that the new pipeline emits
            extra_keys = {
                "catalog": "procedure_*_procedure_catalog_*.json",
                "column_lineage": "procedure_*_column_lineage_*.json",
                "dependency_graph": "procedure_*_dependency_graph_*.json",
                "table_usage": "procedure_*_table_usage_*.json",
                "errors": "procedure_*_errors_*.json",
                "complete": "procedure_*_complete_*.json",
            }
            for key, pattern in extra_keys.items():
                path = _latest_path(pattern)
                if path:
                    response_files[key] = str(path)

            return JSONResponse({
                "statement_report": statement_report,
                "procedure_report": procedure_report,
                "combined_summary": combined_summary,
                "output_files": response_files,
            })
        except HTTPException:
            raise
        except ModuleNotFoundError as e:
            logger.exception("Dependency missing: %s", e)
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=f"Dependency missing: {e}. Ensure required packages are installed in the backend venv. Traceback: {tb}")
        except Exception as e:
            logger.exception("Analysis failed: %s", e)
            tb = traceback.format_exc()
            raise HTTPException(status_code=500, detail=f"Analysis failed: {e}. Traceback: {tb}")


@app.post("/api/analyze/enhanced")
async def analyze_directory_enhanced(
    metadata_path: str = Form(..., description="Path or glob to metadata JSON produced by /api/metadata/tsql"),
    files: List[UploadFile] = File(...),
    dialect: str = Form("tsql", description="SQL dialect (currently supports tsql)"),
    openai_key: Optional[str] = Form(None, description="OpenAI API key (optional, uses Ollama if not provided)")
):
    """Run enhanced lineage analysis that integrates metadata with uploaded SQL scripts."""

    logger.info("/api/analyze/enhanced called: dialect=%s, files=%d", dialect, len(files))

    metadata_raw = metadata_path.strip()
    if not metadata_raw:
        raise HTTPException(status_code=400, detail="metadata_path is required")

    metadata_candidate = Path(metadata_raw)
    if any(ch in metadata_candidate.name for ch in {"*", "?", "[", "]"}):
        logger.info("Resolving metadata glob: %s", metadata_candidate)
        search_root = metadata_candidate.parent if metadata_candidate.parent != Path("") else Path.cwd()
        matches = sorted(search_root.glob(metadata_candidate.name))
        if not matches:
            raise HTTPException(status_code=400, detail=f"No metadata files found for pattern: {metadata_raw}")
        metadata_file = matches[-1]
    else:
        metadata_file = metadata_candidate

    metadata_file = metadata_file.expanduser().resolve()
    if not metadata_file.exists():
        logger.error("Metadata file not found: %s", metadata_file)
        raise HTTPException(status_code=400, detail=f"Metadata file not found: {metadata_file}")

    script_path = Path(__file__).parent / "tsql" / "mssql_conn" / "enhanced_tsql_main.py"
    if not script_path.exists():
        logger.error("Enhanced analyzer script missing: %s", script_path)
        raise HTTPException(status_code=500, detail="Enhanced analyzer not available on server")

    with tempfile.TemporaryDirectory() as tmp_dir:
        base = Path(tmp_dir)
        logger.info("Enhanced analyzer working directory: %s", base)

        for uf in files:
            rel_path = Path(uf.filename)
            if not rel_path.suffix:
                rel_path = rel_path.with_suffix(".sql")
            target_path = base / rel_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("wb") as out_f:
                shutil.copyfileobj(uf.file, out_f)

        output_dir = base / "lineage_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            sys.executable,
            str(script_path),
            str(base),
            "--metadata",
            str(metadata_file),
            "--output",
            str(output_dir),
            "--dialect",
            dialect.lower(),
        ]
        if openai_key:
            cmd.extend(["--openai-key", openai_key])

        logger.info("Running enhanced analyzer: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            cwd=str(script_path.parent),
            capture_output=True,
            text=True,
            check=False,
        )

        if proc.returncode != 0:
            logger.error("Enhanced analyzer failed (code %s): %s", proc.returncode, proc.stderr)
            detail = proc.stderr.strip() or proc.stdout.strip() or "Enhanced analyzer failed"
            raise HTTPException(status_code=500, detail=detail)

        logger.info("Enhanced analyzer completed successfully")
        if proc.stdout:
            logger.debug("Enhanced analyzer stdout:\n%s", proc.stdout)

        def _load_latest(prefix: str) -> dict:
            files_found = sorted(output_dir.glob(f"{prefix}_*.json"))
            if not files_found:
                return {}
            with files_found[-1].open("r", encoding="utf-8") as f:
                return json.load(f)

        statement_report = _load_latest("statement_lineage")
        procedure_report = _load_latest("procedure_lineage")
        combined_summary = _load_latest("lineage_summary")

        return JSONResponse({
            "statement_report": statement_report,
            "procedure_report": procedure_report,
            "combined_summary": combined_summary,
            "output_files": {
                "statements": str(next(iter(sorted(output_dir.glob("statement_lineage_*.json"))), "")),
                "procedures": str(next(iter(sorted(output_dir.glob("procedure_lineage_*.json"))), "")),
                "summary": str(next(iter(sorted(output_dir.glob("lineage_summary_*.json"))), "")),
            },
            "metadata_file": str(metadata_file),
            "stdout": proc.stdout,
        })


@app.post("/api/analyze/metadata")
async def analyze_metadata_direct(request: TsqlMetadataAnalysisRequest):
    """Run metadata-based lineage analysis using direct database connection.
    
    This endpoint uses MetadataLineageOrchestrator to:
    1. Extract metadata directly from SQL Server
    2. Analyze views and query history with traditional parsing
    3. Analyze procedures, functions, and triggers with LLM
    4. Return results in the same format as /api/analyze for frontend compatibility
    
    This is the recommended approach for T-SQL database analysis.
    """
    logger.info("/api/analyze/metadata called: server=%s, database=%s", request.server, request.database)
    
    try:
        # Create temporary output directory
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "lineage_output"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Initialize the orchestrator
            orchestrator = TsqlMetadataLineageOrchestrator(
                server=request.server,
                database=request.database,
                username=request.username,
                password=request.password,
                driver=request.driver,
                output_directory=str(output_dir),
                dialect=request.dialect,
                debug=False,
                ollama_url=request.ollama_url or "http://localhost:11434",
                ollama_model=request.ollama_model or "qwen2.5-coder:14b",
                openai_api_key=request.openai_api_key,
                openai_model=request.openai_model or "gpt-4o-mini",
                batch_size=request.batch_size,
                timeout=request.timeout,
                metadata_file_path=request.metadata_file_path
            )
            
            # Run full analysis
            logger.info("Starting metadata-based lineage analysis...")
            results = orchestrator.run_full_analysis()
            logger.info("Analysis completed successfully")
            
            # Load the generated JSON files
            def _latest_path(pattern: str) -> Path | None:
                files = sorted(output_dir.glob(pattern))
                return files[-1] if files else None
            
            def _load_json(path: Path | None) -> dict:
                if not path or not path.exists():
                    return {}
                try:
                    with path.open("r", encoding="utf-8") as f:
                        return json.load(f)
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to parse JSON file %s: %s", path, exc)
                    return {}
            
            # Load reports (same format as /api/analyze)
            statement_path = _latest_path("statement_lineage_*.json")
            procedure_path = _latest_path("procedure_lineage_*.json")
            summary_path = _latest_path("lineage_summary_*.json")
            
            statement_report = _load_json(statement_path)
            procedure_report = _load_json(procedure_path)
            combined_summary = _load_json(summary_path)
            
            # Build response files dictionary
            response_files = {
                "statements": str(statement_path or ""),
                "procedures": str(procedure_path or ""),
                "summary": str(summary_path or ""),
            }
            
            # Include additional output files from the new pipeline
            extra_keys = {
                "catalog": "procedure_*_procedure_catalog_*.json",
                "column_lineage": "procedure_*_column_lineage_*.json",
                "dependency_graph": "procedure_*_dependency_graph_*.json",
                "table_usage": "procedure_*_table_usage_*.json",
                "errors": "procedure_*_errors_*.json",
                "complete": "procedure_*_complete_*.json",
            }
            for key, pattern in extra_keys.items():
                path = _latest_path(pattern)
                if path:
                    response_files[key] = str(path)
            
            # Include metadata file path if it was used
            if orchestrator.metadata_file_path:
                response_files["metadata"] = str(orchestrator.metadata_file_path)
            
            logger.info(
                "Loaded reports: statements=%s, procedures=%s, summary=%s",
                bool(statement_report), bool(procedure_report), bool(combined_summary)
            )
            
            return JSONResponse({
                "statement_report": statement_report,
                "procedure_report": procedure_report,
                "combined_summary": combined_summary,
                "output_files": response_files,
                "statistics": results.get("statistics", {}),
                "elapsed_time": results.get("elapsed_time", 0),
            })
            
    except RuntimeError as exc:
        logger.exception("Metadata analysis failed with runtime error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Metadata analysis failed: %s", exc)
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"Analysis failed: {exc}. Traceback: {tb}"
        ) from exc


@app.post("/api/analyze/metadata/teradata")
async def analyze_teradata_metadata(request: TeradataMetadataAnalysisRequest):
    """Run metadata-based lineage analysis for Teradata databases."""
    logger.info("/api/analyze/metadata/teradata called: host=%s, database=%s", request.host, request.database)

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            if request.output_directory:
                output_dir = Path(request.output_directory).expanduser().resolve()
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                output_dir = Path(tmp_dir) / "lineage_output"
                output_dir.mkdir(parents=True, exist_ok=True)

            orchestrator = TeradataMetadataLineageOrchestrator(
                host=request.host,
                user=request.username,
                password=request.password,
                database=request.database,
                logmech=request.logmech,
                encryptdata=request.encryptdata,
                output_directory=str(output_dir),
                dialect=request.dialect,
                debug=request.debug,
                ollama_url=request.ollama_url or "http://localhost:11434",
                ollama_model=request.ollama_model or "qwen2.5-coder:14b",
                openai_api_key=request.openai_api_key,
                openai_model=request.openai_model or "gpt-4o-mini",
                batch_size=request.batch_size,
                timeout=request.timeout,
                metadata_file_path=request.metadata_file_path,
            )

            logger.info("Starting Teradata metadata-based lineage analysis...")
            results = orchestrator.run_full_analysis()
            logger.info("Teradata analysis completed successfully")

            def _latest_path(pattern: str) -> Path | None:
                files = sorted(output_dir.glob(pattern))
                return files[-1] if files else None

            def _load_json(path: Path | None) -> dict:
                if not path or not path.exists():
                    return {}
                try:
                    with path.open("r", encoding="utf-8") as f:
                        return json.load(f)
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to parse JSON file %s: %s", path, exc)
                    return {}

            statement_path = _latest_path("statement_lineage_*.json")
            procedure_path = _latest_path("procedure_lineage_*.json")
            summary_path = _latest_path("lineage_summary_*.json")

            statement_report = _load_json(statement_path)
            procedure_report = _load_json(procedure_path)
            combined_summary = _load_json(summary_path)

            response_files = {
                "statements": str(statement_path or ""),
                "procedures": str(procedure_path or ""),
                "summary": str(summary_path or ""),
            }

            if orchestrator.metadata_file_path:
                response_files["metadata"] = str(orchestrator.metadata_file_path)

            extra_keys = {
                "catalog": "procedure_*_procedure_catalog_*.json",
                "column_lineage": "procedure_*_column_lineage_*.json",
                "dependency_graph": "procedure_*_dependency_graph_*.json",
                "table_usage": "procedure_*_table_usage_*.json",
                "errors": "procedure_*_errors_*.json",
                "complete": "procedure_*_complete_*.json",
            }
            for key, pattern in extra_keys.items():
                path = _latest_path(pattern)
                if path:
                    response_files[key] = str(path)

            return JSONResponse({
                "statement_report": statement_report,
                "procedure_report": procedure_report,
                "combined_summary": combined_summary,
                "output_files": response_files,
                "statistics": results.get("statistics", {}),
                "elapsed_time": results.get("elapsed_time", 0),
            })
    except RuntimeError as exc:
        logger.exception("Teradata metadata analysis failed with runtime error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Teradata metadata analysis failed: %s", exc)
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {exc}. Traceback: {tb}"
        ) from exc


@app.post("/api/analyze/metadata/postgres")
async def analyze_postgres_metadata(request: PostgresMetadataAnalysisRequest):
    """Run metadata-based lineage analysis for PostgreSQL databases."""
    logger.info("/api/analyze/metadata/postgres called: host=%s, database=%s", request.host, request.database)

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            if request.output_directory:
                output_dir = Path(request.output_directory).expanduser().resolve()
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                output_dir = Path(tmp_dir) / "lineage_output"
                output_dir.mkdir(parents=True, exist_ok=True)

            orchestrator = PostgresMetadataLineageOrchestrator(
                host=request.host,
                database=request.database,
                username=request.username,
                password=request.password,
                port=request.port,
                output_directory=str(output_dir),
                dialect=request.dialect,
                debug=request.debug,
                ollama_url=request.ollama_url or "http://localhost:11434",
                ollama_model=request.ollama_model or "qwen2.5-coder:14b",
                openai_api_key=request.openai_api_key,
                openai_model=request.openai_model or "gpt-4o-mini",
                batch_size=request.batch_size,
                timeout=request.timeout,
                metadata_file_path=request.metadata_file_path,
            )

            logger.info("Starting PostgreSQL metadata-based lineage analysis...")
            results = orchestrator.run_full_analysis()
            logger.info("PostgreSQL analysis completed successfully")

            def _latest_path(pattern: str) -> Path | None:
                files = sorted(output_dir.glob(pattern))
                return files[-1] if files else None

            def _load_json(path: Path | None) -> dict:
                if not path or not path.exists():
                    return {}
                try:
                    with path.open("r", encoding="utf-8") as f:
                        return json.load(f)
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to parse JSON file %s: %s", path, exc)
                    return {}

            statement_path = _latest_path("statement_lineage_*.json")
            procedure_path = _latest_path("procedure_lineage_*.json")
            summary_path = _latest_path("lineage_summary_*.json")

            statement_report = _load_json(statement_path)
            procedure_report = _load_json(procedure_path)
            combined_summary = _load_json(summary_path)

            response_files = {
                "statements": str(statement_path or ""),
                "procedures": str(procedure_path or ""),
                "summary": str(summary_path or ""),
            }

            if orchestrator.metadata_file_path:
                response_files["metadata"] = str(orchestrator.metadata_file_path)

            extra_keys = {
                "catalog": "procedure_*_procedure_catalog_*.json",
                "column_lineage": "procedure_*_column_lineage_*.json",
                "dependency_graph": "procedure_*_dependency_graph_*.json",
                "table_usage": "procedure_*_table_usage_*.json",
                "errors": "procedure_*_errors_*.json",
                "complete": "procedure_*_complete_*.json",
            }
            for key, pattern in extra_keys.items():
                path = _latest_path(pattern)
                if path:
                    response_files[key] = str(path)

            return JSONResponse({
                "statement_report": statement_report,
                "procedure_report": procedure_report,
                "combined_summary": combined_summary,
                "output_files": response_files,
                "statistics": results.get("statistics", {}),
                "elapsed_time": results.get("elapsed_time", 0),
            })
    except RuntimeError as exc:
        logger.exception("PostgreSQL metadata analysis failed with runtime error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("PostgreSQL metadata analysis failed: %s", exc)
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {exc}. Traceback: {tb}"
        ) from exc


@app.post("/api/analyze/metadata/oracle")
async def analyze_oracle_metadata(request: OracleMetadataAnalysisRequest):
    """Run metadata-based lineage analysis for Oracle databases."""
    logger.info(
        "/api/analyze/metadata/oracle called: host=%s, service_name=%s",
        request.host,
        request.service_name,
    )

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            if request.output_directory:
                output_dir = Path(request.output_directory).expanduser().resolve()
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                output_dir = Path(tmp_dir) / "lineage_output"
                output_dir.mkdir(parents=True, exist_ok=True)

            orchestrator = OracleMetadataLineageOrchestrator(
                host=request.host,
                service_name=request.service_name,
                username=request.username,
                password=request.password,
                port=request.port,
                output_directory=str(output_dir),
                dialect=request.dialect,
                debug=request.debug,
                ollama_url=request.ollama_url or "http://localhost:11434",
                ollama_model=request.ollama_model or "qwen2.5-coder:14b",
                openai_api_key=request.openai_api_key,
                openai_model=request.openai_model or "gpt-4o-mini",
                batch_size=request.batch_size,
                timeout=request.timeout,
                metadata_file_path=request.metadata_file_path,
                target_schemas=request.target_schemas,
            )

            logger.info("Starting Oracle metadata-based lineage analysis...")
            results = orchestrator.run_full_analysis()
            logger.info("Oracle analysis completed successfully")

            def _latest_path(pattern: str) -> Path | None:
                files = sorted(output_dir.glob(pattern))
                return files[-1] if files else None

            def _load_json(path: Path | None) -> dict:
                if not path or not path.exists():
                    return {}
                try:
                    with path.open("r", encoding="utf-8") as f:
                        return json.load(f)
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to parse JSON file %s: %s", path, exc)
                    return {}

            statement_path = _latest_path("statement_lineage_*.json")
            procedure_path = _latest_path("procedure_lineage_*.json")
            summary_path = _latest_path("lineage_summary_*.json")

            statement_report = _load_json(statement_path)
            procedure_report = _load_json(procedure_path)
            combined_summary = _load_json(summary_path)

            response_files = {
                "statements": str(statement_path or ""),
                "procedures": str(procedure_path or ""),
                "summary": str(summary_path or ""),
            }

            if orchestrator.metadata_file_path:
                response_files["metadata"] = str(orchestrator.metadata_file_path)

            extra_keys = {
                "catalog": "procedure_*_procedure_catalog_*.json",
                "column_lineage": "procedure_*_column_lineage_*.json",
                "dependency_graph": "procedure_*_dependency_graph_*.json",
                "table_usage": "procedure_*_table_usage_*.json",
                "errors": "procedure_*_errors_*.json",
                "complete": "procedure_*_complete_*.json",
            }
            for key, pattern in extra_keys.items():
                path = _latest_path(pattern)
                if path:
                    response_files[key] = str(path)

            return JSONResponse({
                "statement_report": statement_report,
                "procedure_report": procedure_report,
                "combined_summary": combined_summary,
                "output_files": response_files,
                "statistics": results.get("statistics", {}),
                "elapsed_time": results.get("elapsed_time", 0),
            })
    except RuntimeError as exc:
        logger.exception("Oracle metadata analysis failed with runtime error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Oracle metadata analysis failed: %s", exc)
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {exc}. Traceback: {tb}"
        ) from exc


@app.post("/api/analyze/metadata/snowflake")
async def analyze_snowflake_metadata(request: SnowflakeMetadataAnalysisRequest):
    """Run metadata-based lineage analysis for Snowflake databases."""
    logger.info(
        "/api/analyze/metadata/snowflake called: account=%s, database=%s, warehouse=%s",
        request.account,
        request.database,
        request.warehouse or "N/A",
    )

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            if request.output_directory:
                output_dir = Path(request.output_directory).expanduser().resolve()
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                output_dir = Path(tmp_dir) / "lineage_output"
                output_dir.mkdir(parents=True, exist_ok=True)

            orchestrator = SnowflakeMetadataLineageOrchestrator(
                account=request.account,
                database=request.database,
                username=request.username,
                password=request.password or "",
                warehouse=request.warehouse or "",
                role=request.role or "",
                authenticator=request.authenticator or "externalbrowser",
                schema_filter="",
                output_directory=str(output_dir),
                dialect=request.dialect,
                debug=request.debug,
                ollama_url=request.ollama_url or "http://localhost:11434",
                ollama_model=request.ollama_model or "qwen2.5-coder:14b",
                openai_api_key=request.openai_api_key,
                openai_model=request.openai_model or "gpt-4o-mini",
                batch_size=request.batch_size,
                timeout=request.timeout,
                metadata_file_path=request.metadata_file_path,
            )

            logger.info("Starting Snowflake metadata-based lineage analysis...")
            results = orchestrator.run_full_analysis()
            logger.info("Snowflake analysis completed successfully")

            def _latest_path(pattern: str) -> Path | None:
                files = sorted(output_dir.glob(pattern))
                return files[-1] if files else None

            def _load_json(path: Path | None) -> dict:
                if not path or not path.exists():
                    return {}
                try:
                    with path.open("r", encoding="utf-8") as f:
                        return json.load(f)
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to parse JSON file %s: %s", path, exc)
                    return {}

            statement_path = _latest_path("statement_lineage_*.json")
            procedure_path = _latest_path("procedure_lineage_*.json")
            summary_path = _latest_path("lineage_summary_*.json")

            statement_report = _load_json(statement_path)
            procedure_report = _load_json(procedure_path)
            combined_summary = _load_json(summary_path)

            response_files = {
                "statements": str(statement_path or ""),
                "procedures": str(procedure_path or ""),
                "summary": str(summary_path or ""),
            }

            if orchestrator.metadata_file_path:
                response_files["metadata"] = str(orchestrator.metadata_file_path)

            extra_keys = {
                "catalog": "procedure_*_procedure_catalog_*.json",
                "column_lineage": "procedure_*_column_lineage_*.json",
                "dependency_graph": "procedure_*_dependency_graph_*.json",
                "table_usage": "procedure_*_table_usage_*.json",
                "errors": "procedure_*_errors_*.json",
                "complete": "procedure_*_complete_*.json",
            }
            for key, pattern in extra_keys.items():
                path = _latest_path(pattern)
                if path:
                    response_files[key] = str(path)

            return JSONResponse({
                "statement_report": statement_report,
                "procedure_report": procedure_report,
                "combined_summary": combined_summary,
                "output_files": response_files,
                "statistics": results.get("statistics", {}),
                "elapsed_time": results.get("elapsed_time", 0),
            })

    except RuntimeError as exc:
        logger.exception("Snowflake metadata analysis failed with runtime error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - runtime safeguard
        logger.exception("Snowflake metadata analysis failed: %s", exc)
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {exc}. Traceback: {tb}"
        ) from exc


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/analyze/metadata/{dialect}")
async def analyze_metadata_dynamic(dialect: str, request: Request):
    """Flexible metadata endpoint that routes requests based on dialect in the path."""
    payload = await request.json()
    dialect_lower = (dialect or "").lower()

    if dialect_lower in {"snowflake"}:
        model = SnowflakeMetadataAnalysisRequest(**payload)
        return await analyze_snowflake_metadata(model)

    if dialect_lower in {"tsql", "mssql"}:
        model = TsqlMetadataAnalysisRequest(**payload)
        return await analyze_metadata_direct(model)

    if dialect_lower in {"teradata"}:
        model = TeradataMetadataAnalysisRequest(**payload)
        return await analyze_teradata_metadata(model)

    if dialect_lower in {"postgres", "postgresql", "postgress", "pgsql"}:
        model = PostgresMetadataAnalysisRequest(**payload)
        return await analyze_postgres_metadata(model)

    if dialect_lower in {"oracle"}:
        model = OracleMetadataAnalysisRequest(**payload)
        return await analyze_oracle_metadata(model)

    raise HTTPException(status_code=400, detail=f"Dialect '{dialect}' is not supported for metadata analysis yet.")


