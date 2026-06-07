"""Enhanced Snowflake metadata extractor with comprehensive coverage.

This improved version captures:
- Tables, Views, Stored Procedures, Functions
- Query history from QUERY_HISTORY view
- Extended properties and descriptions
- Streams, Tasks, and Pipes
- Complete schema hierarchy
- Performance statistics
- Stage and File Format metadata

Snowflake-specific features:
- Variant columns
- Time Travel
- Clustering keys
- Materialized views
- External tables
- Dynamic tables
"""

from __future__ import annotations

import json
import time
from datetime import datetime, UTC
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Set, Optional
from collections import defaultdict, deque

import urllib.parse

try:
    import snowflake.connector
    from snowflake.connector import DictCursor
except ImportError:
    snowflake = None
    DictCursor = None


METADATA_OUTPUT_DIR = Path(__file__).parent / "metadata_cache"

# System schemas to exclude
SYSTEM_SCHEMAS = (
    'INFORMATION_SCHEMA',
)

# System databases to exclude
SYSTEM_DATABASES = (
    'SNOWFLAKE',
    'SNOWFLAKE_SAMPLE_DATA',
)

SYSTEM_SCHEMA_FILTER = ", ".join(f"'{schema}'" for schema in SYSTEM_SCHEMAS)


def _is_system_object(schema: str, name: str) -> bool:
    """Check if an object is a system object based on schema and name."""
    if schema.upper() in SYSTEM_SCHEMAS:
        return True
    return False


def _filter_system_objects(
    objects: List[Dict[str, Any]],
    schema_key: str = 'schema_name',
    name_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter out system objects from extracted list."""
    filtered: List[Dict[str, Any]] = []

    for obj in objects:
        schema = obj.get(schema_key, 'PUBLIC')

        if name_key is None:
            if 'view_name' in obj:
                name = obj['view_name']
            elif 'procedure_name' in obj:
                name = obj['procedure_name']
            elif 'function_name' in obj:
                name = obj['function_name']
            elif 'name' in obj:
                name = obj['name']
            else:
                continue
        else:
            name = obj.get(name_key, '')

        if _is_system_object(schema, name):
            continue

        filtered.append(obj)

    return filtered


def _ensure_output_dir(output_dir: Path | None) -> Path:
    directory = output_dir or METADATA_OUTPUT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _normalize_account_identifier(account: str) -> str:
    """Normalize Snowflake account identifiers so the connector can resolve them."""
    if not account:
        return account

    normalized = account.strip()
    if not normalized:
        return normalized

    if normalized.startswith("https://"):
        normalized = normalized[len("https://") :]
    elif normalized.startswith("http://"):
        normalized = normalized[len("http://") :]

    if "/" in normalized:
        normalized = normalized.split("/", 1)[0]

    if normalized.endswith(":443"):
        normalized = normalized[:-4]

    lower_norm = normalized.lower()
    suffix = ".snowflakecomputing.com"
    idx = lower_norm.find(suffix)
    if idx != -1:
        normalized = normalized[:idx]

    return normalized


def _quote_identifier(identifier: str) -> str:
    """Quote Snowflake identifier, preserving case and special chars."""
    if identifier is None:
        return '""'
    escaped = identifier.replace('"', '""')
    return f'"{escaped}"'


def _to_sql_literal(value: str) -> str:
    """Safely wrap value for inline SQL literals."""
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _extract_select_from_view_ddl(ddl: str) -> str:
    """Best-effort extraction of SELECT body from GET_DDL output."""
    if not ddl:
        return ""
    parts = re.split(r"\\bAS\\b", ddl, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[1].strip().rstrip(";")
    return ddl


def _backfill_view_definitions(cursor, database: str, views: List[Dict[str, Any]]) -> None:
    """Populate missing view definitions using GET_DDL fallback."""
    missing = [
        view for view in views
        if not (view.get("definition") or "").strip()
    ]
    if not missing:
        return

    print(f"Detected {len(missing)} views without definitions. Attempting GET_DDL fallback...")

    for view in missing:
        view_name = view.get("view_name") or view.get("name")
        schema_name = view.get("schema_name") or view.get("table_schema") or "PUBLIC"
        if not view_name:
            continue

        qualified = ".".join([
            _quote_identifier(database),
            _quote_identifier(schema_name),
            _quote_identifier(view_name),
        ])

        try:
            cursor.execute(
                f"SELECT GET_DDL('VIEW', {_to_sql_literal(qualified)}) AS ddl"
            )
            rows = _rows_to_dicts(cursor)
            if not rows:
                continue

            ddl_text = rows[0].get("ddl") or rows[0].get("view_ddl")
            if not ddl_text:
                # Fallback to first value in row dict
                ddl_text = next(iter(rows[0].values()), "")

            select_sql = _extract_select_from_view_ddl(ddl_text)
            if select_sql:
                view["definition"] = select_sql
                view["definition_source"] = "get_ddl"
        except Exception as exc:
            print(f"   ⚠ Warning: Failed to fetch definition for {qualified}: {exc}")


def _needs_procedure_header(definition: Optional[str]) -> bool:
    """Determine if a procedure definition is missing CREATE OR REPLACE header."""
    if not definition:
        return True
    lowered = definition.strip().lower()
    return not lowered.startswith("create or replace")


def _normalize_argument_signature(signature: Optional[str]) -> str:
    """Ensure argument signature is wrapped in parentheses for GET_DDL."""
    if not signature:
        return "()"
    normalized = signature.strip()
    if not normalized:
        return "()"
    if not normalized.startswith("("):
        normalized = f"({normalized})"
    return normalized


def _backfill_procedure_definitions(cursor, database: str, procedures: List[Dict[str, Any]]) -> None:
    """
    Replace Snowflake INFORMATION_SCHEMA procedure bodies with full GET_DDL output.
    Snowflake returns only the procedure body via PROCEDURE_DEFINITION, so we call
    GET_DDL to capture the CREATE OR REPLACE header, arguments, and RETURNS clause.
    """
    if not procedures:
        return

    print("Ensuring stored procedure definitions include full CREATE headers via GET_DDL...")

    for procedure in procedures:
        current_def = (procedure.get("definition") or "").strip()
        if not _needs_procedure_header(current_def):
            continue

        schema_name = (
            procedure.get("schema_name")
            or procedure.get("procedure_schema")
            or "PUBLIC"
        )
        proc_name = procedure.get("procedure_name") or procedure.get("name")
        if not proc_name:
            continue

        signature = _normalize_argument_signature(procedure.get("argument_signature"))

        qualified = ".".join(
            [
                _quote_identifier(database),
                _quote_identifier(schema_name),
                _quote_identifier(proc_name),
            ]
        )

        qualified_with_sig = f"{qualified}{signature}"

        try:
            cursor.execute(
                f"SELECT GET_DDL('PROCEDURE', {_to_sql_literal(qualified_with_sig)}) AS ddl"
            )
            rows = _rows_to_dicts(cursor)
            if not rows:
                continue

            ddl_text = rows[0].get("ddl") or next(iter(rows[0].values()), "")
            ddl_text = (ddl_text or "").strip()
            if ddl_text:
                procedure["definition"] = ddl_text
                procedure["definition_source"] = "get_ddl"
        except Exception as exc:
            print(
                f"   ⚠ Warning: Failed to fetch procedure definition for {qualified_with_sig}: {exc}"
            )


def save_metadata_to_file(
    metadata: Dict[str, Any],
    output_dir: Path | str | None = None,
    filename: str | None = None,
) -> Path:
    """Persist metadata to disk with a consistent naming scheme.

    Args:
        metadata: Extracted metadata dictionary.
        output_dir: Directory to place the JSON file (defaults to metadata cache).
        filename: Optional explicit filename; otherwise an auto timestamped name is used.

    Returns:
        Path to the written JSON file.
    """
    directory: Path
    if output_dir is None:
        directory = _ensure_output_dir(None)
    else:
        directory = _ensure_output_dir(Path(output_dir))

    if filename:
        file_path = directory / filename
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        safe_db = str(metadata.get("database", "database")).replace("/", "-").replace("\\", "-")
        file_path = directory / f"enhanced_metadata_{safe_db}_{timestamp}.json"

    with file_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, default=str)

    return file_path


def build_connection_params(
    account: str,
    database: str,
    username: str,
    password: str = "",
    warehouse: str = "",
    role: str = "",
    authenticator: str = "externalbrowser",
    schema: str = "PUBLIC"
) -> Dict[str, str]:
    """Construct Snowflake connection parameters.

    Args:
        account: Snowflake account identifier (e.g., 'XBXMLZX-MIA01615')
        database: Database name
        username: Login username
        password: Login password (empty for external browser auth)
        warehouse: Compute warehouse name
        role: Role to use
        authenticator: Authentication method (externalbrowser, snowflake, etc.)
        schema: Default schema

    Returns:
        Connection parameters dictionary
    """
    normalized_account = _normalize_account_identifier(account)

    params = {
        "account": normalized_account,
        "user": username,
        "database": database,
        "schema": schema,
        "authenticator": authenticator,
    }

    if password:
        params["password"] = password

    if warehouse:
        params["warehouse"] = warehouse

    if role:
        params["role"] = role

    return params


def _rows_to_dicts(cursor) -> List[Dict[str, Any]]:
    """Convert cursor results to list of dictionaries."""
    if not cursor.description:
        return []

    columns = [col[0].lower() for col in cursor.description]
    results = []
    for row in cursor:
        if isinstance(row, dict):
            results.append({k.lower(): v for k, v in row.items()})
        else:
            results.append(dict(zip(columns, row)))
    return results


def _compute_levels(graph: Dict[str, Iterable[str]], start: str, max_depth: int = 5) -> Dict[str, List[str]]:
    levels: Dict[str, List[str]] = {}
    visited = {start}
    queue = deque([(start, 0)])

    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for neighbour in sorted(set(graph.get(node, []))):
            if neighbour in visited:
                continue
            visited.add(neighbour)
            level_key = str(depth + 1)
            levels.setdefault(level_key, []).append(neighbour)
            queue.append((neighbour, depth + 1))

    return levels


def _build_table_disambiguation_map(tables: List[Dict[str, Any]], database: str) -> Dict[str, Any]:
    """Build a comprehensive table name disambiguation map."""
    disambiguation = {
        "unique_tables": {},
        "ambiguous_tables": {},
        "schema_tables": {},
        "full_hierarchy": {},
    }

    table_name_counts = defaultdict(list)
    schema_tables = defaultdict(list)

    for table in tables:
        schema = table.get('schema', 'PUBLIC')
        name = table['name']
        table_type = table.get('type', 'TABLE')

        qualified_name = f"{schema}.{name}"
        full_name = f"{database}.{schema}.{name}"

        table_name_counts[name].append(qualified_name)
        schema_tables[schema].append(name)

        # Store all possible name variations
        for key in [name, qualified_name, full_name, name.upper(), qualified_name.upper(), full_name.upper()]:
            disambiguation["full_hierarchy"][key] = {
                "table_name": name,
                "schema": schema,
                "qualified_name": qualified_name,
                "full_name": full_name,
                "type": table_type,
                "database": database
            }

    # Categorize as unique or ambiguous
    for table_name, qualified_names in table_name_counts.items():
        if len(qualified_names) == 1:
            disambiguation["unique_tables"][table_name] = qualified_names[0]
        else:
            disambiguation["ambiguous_tables"][table_name] = sorted(qualified_names)

    disambiguation["schema_tables"] = dict(schema_tables)

    return disambiguation


def _build_column_map(columns: List[Dict[str, Any]], database: str) -> Dict[str, Any]:
    """Build comprehensive column mapping for parser support."""
    column_map = {
        "by_table": {},
        "by_column_name": defaultdict(list),
        "unique_columns": {},
        "column_types": {},
    }

    column_name_counts = defaultdict(set)

    for column in columns:
        schema = column.get('table_schema', 'PUBLIC')
        table = column['table_name']
        col_name = column['column_name']

        qualified_table = f"{schema}.{table}"
        full_table = f"{database}.{schema}.{table}"
        qualified_column = f"{qualified_table}.{col_name}"

        col_metadata = {
            "name": col_name,
            "data_type": column.get('data_type'),
            "character_maximum_length": column.get('character_maximum_length'),
            "numeric_precision": column.get('numeric_precision'),
            "numeric_scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable'),
            "is_identity": column.get('is_identity', False),
            "column_default": column.get('column_default'),
            "comment": column.get('comment'),
            "qualified_name": qualified_column,
            "table": qualified_table,
            "full_table": full_table,
            "schema": schema,
        }

        if qualified_table not in column_map["by_table"]:
            column_map["by_table"][qualified_table] = []
        column_map["by_table"][qualified_table].append(col_metadata)

        column_name_counts[col_name].add(qualified_table)
        column_map["by_column_name"][col_name].append(qualified_table)

        column_map["column_types"][qualified_column] = {
            "data_type": column.get('data_type'),
            "character_maximum_length": column.get('character_maximum_length'),
            "numeric_precision": column.get('numeric_precision'),
            "numeric_scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable'),
        }

    # Identify unique columns
    for col_name, tables in column_name_counts.items():
        if len(tables) == 1:
            column_map["unique_columns"][col_name] = list(tables)[0]

    column_map["by_column_name"] = dict(column_map["by_column_name"])

    return column_map


def _is_transient_error(error: Exception) -> bool:
    """Check if the error is a transient Snowflake error that should be retried."""
    error_str = str(error).upper()
    transient_indicators = [
        "TIMEOUT",
        "CONNECTION",
        "NETWORK",
        "RETRY",
        "UNAVAILABLE",
        "SERVICE_UNAVAILABLE",
    ]
    return any(indicator in error_str for indicator in transient_indicators)


def extract_enhanced_database_metadata(
    account: str,
    database: str,
    username: str,
    password: str = "",
    warehouse: str = "",
    role: str = "",
    authenticator: str = "externalbrowser",
    schema_filter: str = "",
    output_dir: Path | None = None,
    max_retries: int = 3,
    initial_retry_delay: float = 2.0,
) -> Tuple[Dict[str, Any], Path]:
    """Extract comprehensive metadata from Snowflake database.

    Args:
        account: Snowflake account identifier
        database: Database name
        username: Login username
        password: Login password
        warehouse: Compute warehouse name
        role: Role to use
        authenticator: Authentication method
        schema_filter: Optional schema name to filter (empty = all schemas)
        output_dir: Output directory for metadata files
        max_retries: Maximum number of retry attempts for transient errors
        initial_retry_delay: Initial delay in seconds before first retry

    Returns:
        Tuple of (metadata dictionary, output file path)

    Raises:
        RuntimeError: If connection fails after all retries
        ImportError: If snowflake-connector-python is not installed
    """

    if snowflake is None:
        raise ImportError(
            "snowflake-connector-python is required. "
            "Install it with: pip install snowflake-connector-python"
        )

    metadata: Dict[str, Any] = {"database": database, "account": account}
    conn = None

    conn_params = build_connection_params(
        account=account,
        database=database,
        username=username,
        password=password,
        warehouse=warehouse,
        role=role,
        authenticator=authenticator
    )

    # Safety: ensure account identifier is normalized before connecting
    conn_params["account"] = _normalize_account_identifier(conn_params.get("account", ""))

    # Retry logic for transient errors
    last_error = None
    for attempt in range(max_retries):
        try:
            if conn is not None:
                try:
                    conn.close()
                except:
                    pass

            conn = snowflake.connector.connect(**conn_params)
            cursor = conn.cursor(DictCursor)

            # Set context
            cursor.execute(f"USE DATABASE {database}")
            if warehouse:
                cursor.execute(f"USE WAREHOUSE {warehouse}")

            # Build schema filter clause
            schema_clause = ""
            if schema_filter:
                schema_clause = f"AND TABLE_SCHEMA = '{schema_filter}'"
            else:
                schema_clause = f"AND TABLE_SCHEMA NOT IN ({SYSTEM_SCHEMA_FILTER})"

            # 1. Extract Tables
            cursor.execute(f"""
            SELECT
                TABLE_SCHEMA as table_schema,
                TABLE_NAME as table_name,
                TABLE_TYPE as table_type,
                CREATED as create_date,
                LAST_ALTERED as modify_date,
                COMMENT as description,
                ROW_COUNT as row_count,
                BYTES as bytes,
                CLUSTERING_KEY as clustering_key,
                IS_TRANSIENT as is_transient,
                RETENTION_TIME as retention_time
            FROM {database}.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_CATALOG = '{database}'
                {schema_clause}
                AND TABLE_TYPE IN ('BASE TABLE', 'EXTERNAL TABLE', 'DYNAMIC TABLE')
            ORDER BY TABLE_SCHEMA, TABLE_NAME
            """)
            tables = _rows_to_dicts(cursor)

            # 2. Extract Columns
            cursor.execute(f"""
            SELECT
                TABLE_SCHEMA as table_schema,
                TABLE_NAME as table_name,
                COLUMN_NAME as column_name,
                ORDINAL_POSITION as ordinal_position,
                DATA_TYPE as data_type,
                CHARACTER_MAXIMUM_LENGTH as character_maximum_length,
                NUMERIC_PRECISION as numeric_precision,
                NUMERIC_SCALE as numeric_scale,
                IS_NULLABLE as is_nullable,
                COLUMN_DEFAULT as column_default,
                IS_IDENTITY as is_identity,
                COMMENT as comment
            FROM {database}.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_CATALOG = '{database}'
                {schema_clause}
            ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
            """)
            columns = _rows_to_dicts(cursor)

            # 3. Extract Views (with graceful fallback for older accounts without IS_MATERIALIZED)
            try:
                cursor.execute(f"""
                SELECT
                    TABLE_SCHEMA as schema_name,
                    TABLE_NAME as view_name,
                    VIEW_DEFINITION as definition,
                    CREATED as create_date,
                    LAST_ALTERED as modify_date,
                    COMMENT as description,
                    IS_SECURE as is_secure,
                    IS_MATERIALIZED as is_materialized
                FROM {database}.INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_CATALOG = '{database}'
                    {schema_clause}
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """)
                views = _rows_to_dicts(cursor)
            except Exception as exc:
                fallback_needed = "IS_MATERIALIZED" in str(exc).upper()
                if not fallback_needed:
                    raise
                cursor.execute(f"""
                SELECT
                    TABLE_SCHEMA as schema_name,
                    TABLE_NAME as view_name,
                    VIEW_DEFINITION as definition,
                    CREATED as create_date,
                    LAST_ALTERED as modify_date,
                    COMMENT as description,
                    IS_SECURE as is_secure
                FROM {database}.INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_CATALOG = '{database}'
                    {schema_clause}
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """)
                views = _rows_to_dicts(cursor)
                for view in views:
                    view['is_materialized'] = False

            # Ensure secure or restricted views still get definitions
            _backfill_view_definitions(cursor, database, views)

            # 4. Extract Stored Procedures
            cursor.execute(f"""
            SELECT
                PROCEDURE_SCHEMA as schema_name,
                PROCEDURE_NAME as procedure_name,
                PROCEDURE_DEFINITION as definition,
                CREATED as create_date,
                LAST_ALTERED as modify_date,
                COMMENT as description,
                PROCEDURE_LANGUAGE as language,
                ARGUMENT_SIGNATURE as argument_signature
            FROM {database}.INFORMATION_SCHEMA.PROCEDURES
            WHERE PROCEDURE_CATALOG = '{database}'
                AND PROCEDURE_SCHEMA NOT IN ({SYSTEM_SCHEMA_FILTER})
            ORDER BY PROCEDURE_SCHEMA, PROCEDURE_NAME
            """)
            procedures = _rows_to_dicts(cursor)
            _backfill_procedure_definitions(cursor, database, procedures)

            # 5. Extract Functions (UDFs)
            cursor.execute(f"""
            SELECT
                FUNCTION_SCHEMA as schema_name,
                FUNCTION_NAME as function_name,
                DATA_TYPE as return_type,
                FUNCTION_DEFINITION as definition,
                CREATED as create_date,
                LAST_ALTERED as modify_date,
                COMMENT as description,
                FUNCTION_LANGUAGE as language,
                ARGUMENT_SIGNATURE as argument_signature,
                IS_SECURE as is_secure,
                IS_EXTERNAL as is_external,
                IS_AGGREGATE as is_aggregate
            FROM {database}.INFORMATION_SCHEMA.FUNCTIONS
            WHERE FUNCTION_CATALOG = '{database}'
                AND FUNCTION_SCHEMA NOT IN ({SYSTEM_SCHEMA_FILTER})
            ORDER BY FUNCTION_SCHEMA, FUNCTION_NAME
            """)
            functions = _rows_to_dicts(cursor)

            # 6. Extract Primary Keys
            try:
                cursor.execute(f"""
                SELECT
                    tc.TABLE_SCHEMA,
                    tc.TABLE_NAME,
                    tc.CONSTRAINT_NAME as PK_NAME,
                    kcu.COLUMN_NAME,
                    kcu.ORDINAL_POSITION
                FROM {database}.INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN {database}.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                    AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                    AND tc.TABLE_NAME = kcu.TABLE_NAME
                WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
                    AND tc.TABLE_CATALOG = '{database}'
                    {schema_clause.replace('TABLE_SCHEMA', 'tc.TABLE_SCHEMA')}
                ORDER BY tc.TABLE_SCHEMA, tc.TABLE_NAME, kcu.ORDINAL_POSITION
                """)
                primary_keys = _rows_to_dicts(cursor)
            except Exception as exc:
                print(f"Could not extract primary keys (KEY_COLUMN_USAGE unavailable?): {exc}")
                primary_keys = []
                try:
                    cursor.execute(f"SHOW PRIMARY KEYS IN DATABASE {database}")
                    pk_rows = _rows_to_dicts(cursor)
                    for row in pk_rows:
                        primary_keys.append({
                            "table_schema": row.get("schema_name") or row.get("schema"),
                            "table_name": row.get("table_name"),
                            "column_name": row.get("column_name"),
                            "ordinal_position": row.get("key_sequence") or row.get("position"),
                            "constraint_name": row.get("primary_key_name") or row.get("name"),
                        })
                    if primary_keys:
                        print(f"   ✓ Fallback primary key extraction succeeded via SHOW PRIMARY KEYS ({len(primary_keys)} entries)")
                except Exception as fallback_exc:
                    print(f"Fallback primary key extraction also failed: {fallback_exc}")

            # 7. Extract Foreign Keys
            try:
                cursor.execute(f"""
                SELECT
                    tc.TABLE_SCHEMA as schema_name,
                    tc.TABLE_NAME as table_name,
                    tc.CONSTRAINT_NAME as constraint_name,
                    kcu.COLUMN_NAME as column_name,
                    rc.UNIQUE_CONSTRAINT_SCHEMA as referenced_schema,
                    rc.UNIQUE_CONSTRAINT_NAME as referenced_constraint,
                    kcu2.TABLE_NAME as referenced_table,
                    kcu2.COLUMN_NAME as referenced_column,
                    rc.DELETE_RULE as delete_action,
                    rc.UPDATE_RULE as update_action
                FROM {database}.INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
                JOIN {database}.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
                    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                    AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
                JOIN {database}.INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
                    ON tc.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
                    AND tc.TABLE_SCHEMA = rc.CONSTRAINT_SCHEMA
                JOIN {database}.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
                    ON rc.UNIQUE_CONSTRAINT_NAME = kcu2.CONSTRAINT_NAME
                    AND rc.UNIQUE_CONSTRAINT_SCHEMA = kcu2.TABLE_SCHEMA
                WHERE tc.CONSTRAINT_TYPE = 'FOREIGN KEY'
                    AND tc.TABLE_CATALOG = '{database}'
                    {schema_clause.replace('TABLE_SCHEMA', 'tc.TABLE_SCHEMA')}
                ORDER BY tc.TABLE_SCHEMA, tc.TABLE_NAME, tc.CONSTRAINT_NAME
                """)
                foreign_keys = _rows_to_dicts(cursor)
            except Exception as exc:
                print(f"Could not extract foreign keys (KEY_COLUMN_USAGE/REFERENTIAL_CONSTRAINTS unavailable?): {exc}")
                foreign_keys = []
                try:
                    cursor.execute(f"SHOW IMPORTED KEYS IN DATABASE {database}")
                    fk_rows = _rows_to_dicts(cursor)
                    for row in fk_rows:
                        foreign_keys.append({
                            "schema_name": row.get("foreign_key_table_schema") or row.get("fk_table_schema"),
                            "table_name": row.get("foreign_key_table_name") or row.get("fk_table_name"),
                            "constraint_name": row.get("foreign_key_name") or row.get("name"),
                            "column_name": row.get("foreign_key_column_name") or row.get("fk_column_name"),
                            "referenced_schema": row.get("primary_key_table_schema") or row.get("pk_table_schema"),
                            "referenced_table": row.get("primary_key_table_name") or row.get("pk_table_name"),
                            "referenced_column": row.get("primary_key_column_name") or row.get("pk_column_name"),
                            "delete_action": row.get("delete_rule"),
                            "update_action": row.get("update_rule"),
                        })
                    if foreign_keys:
                        print(f"   ✓ Fallback foreign key extraction succeeded via SHOW IMPORTED KEYS ({len(foreign_keys)} entries)")
                except Exception as fallback_exc:
                    print(f"Fallback foreign key extraction also failed: {fallback_exc}")

            # 8. Extract Streams (Snowflake-specific CDC)
            streams = []
            try:
                cursor.execute(f"""
                SHOW STREAMS IN DATABASE {database}
                """)
                stream_rows = _rows_to_dicts(cursor)
                for stream in stream_rows:
                    streams.append({
                        'schema_name': stream.get('schema_name'),
                        'stream_name': stream.get('name'),
                        'source_table': stream.get('table_name'),
                        'mode': stream.get('mode'),
                        'stale': stream.get('stale'),
                        'created_on': stream.get('created_on'),
                    })
            except Exception as e:
                print(f"Could not extract streams: {e}")

            # 9. Extract Tasks (Snowflake-specific scheduling)
            tasks = []
            try:
                cursor.execute(f"""
                SHOW TASKS IN DATABASE {database}
                """)
                task_rows = _rows_to_dicts(cursor)
                for task in task_rows:
                    tasks.append({
                        'schema_name': task.get('schema_name'),
                        'task_name': task.get('name'),
                        'warehouse': task.get('warehouse'),
                        'schedule': task.get('schedule'),
                        'definition': task.get('definition'),
                        'state': task.get('state'),
                        'created_on': task.get('created_on'),
                    })
            except Exception as e:
                print(f"Could not extract tasks: {e}")

            # 10. Extract Stages
            stages = []
            try:
                cursor.execute(f"""
                SHOW STAGES IN DATABASE {database}
                """)
                stage_rows = _rows_to_dicts(cursor)
                for stage in stage_rows:
                    stages.append({
                        'schema_name': stage.get('schema_name'),
                        'stage_name': stage.get('name'),
                        'url': stage.get('url'),
                        'type': stage.get('type'),
                        'created_on': stage.get('created_on'),
                    })
            except Exception as e:
                print(f"Could not extract stages: {e}")

            # 11. Extract Query History (last 7 days)
            query_history = []
            try:
                cursor.execute(f"""
                SELECT
                    QUERY_ID,
                    QUERY_TEXT,
                    QUERY_TYPE,
                    DATABASE_NAME,
                    SCHEMA_NAME,
                    USER_NAME,
                    WAREHOUSE_NAME,
                    EXECUTION_STATUS,
                    TOTAL_ELAPSED_TIME / 1000.0 as avg_duration_ms,
                    BYTES_SCANNED,
                    ROWS_PRODUCED,
                    START_TIME as last_execution_time
                FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
                WHERE DATABASE_NAME = '{database}'
                    AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP())
                    AND QUERY_TYPE IN ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'CREATE_TABLE_AS_SELECT')
                    AND EXECUTION_STATUS = 'SUCCESS'
                    AND QUERY_TEXT NOT LIKE '%INFORMATION_SCHEMA%'
                    AND QUERY_TEXT NOT LIKE '%SHOW%'
                    AND LENGTH(QUERY_TEXT) >= 50
                ORDER BY TOTAL_ELAPSED_TIME DESC
                LIMIT 1000
                """)
                query_history = _rows_to_dicts(cursor)
                print(f"Extracted {len(query_history)} queries from history")
            except Exception as e:
                print(f"Could not access Query History (requires SNOWFLAKE.ACCOUNT_USAGE access): {e}")

            # 12. Extract Sequences
            sequences = []
            try:
                cursor.execute(f"""
                SELECT
                    SEQUENCE_SCHEMA as schema_name,
                    SEQUENCE_NAME,
                    DATA_TYPE,
                    START_VALUE,
                    "INCREMENT",
                    MINIMUM_VALUE,
                    MAXIMUM_VALUE,
                    CYCLE_OPTION,
                    CREATED,
                    LAST_ALTERED,
                    COMMENT
                FROM {database}.INFORMATION_SCHEMA.SEQUENCES
                WHERE SEQUENCE_CATALOG = '{database}'
                    {schema_clause.replace('TABLE_SCHEMA', 'SEQUENCE_SCHEMA')}
                ORDER BY SEQUENCE_SCHEMA, SEQUENCE_NAME
                """)
                sequences = _rows_to_dicts(cursor)
            except Exception as e:
                print(f"Could not extract sequences from INFORMATION_SCHEMA (older accounts?): {e}")
                # Fallback to SHOW SEQUENCES which is more widely available
                try:
                    cursor.execute(f"SHOW SEQUENCES IN DATABASE {database}")
                    seq_rows = _rows_to_dicts(cursor)
                    for seq in seq_rows:
                        sequences.append({
                            "schema_name": seq.get("schema_name") or seq.get("schema"),
                            "sequence_name": seq.get("name"),
                            "data_type": seq.get("data_type"),
                            "start_value": seq.get("start_value"),
                            "increment": seq.get("increment"),
                            "minimum_value": seq.get("minimum_value"),
                            "maximum_value": seq.get("maximum_value"),
                            "cycle_option": seq.get("cycle"),
                            "created": seq.get("created_on"),
                            "last_altered": seq.get("last_altered"),
                            "comment": seq.get("comment"),
                        })
                except Exception as fallback_exc:
                    print(f"Fallback sequence extraction also failed: {fallback_exc}")

            # 13. Extract File Formats
            file_formats = []
            try:
                cursor.execute(f"""
                SHOW FILE FORMATS IN DATABASE {database}
                """)
                ff_rows = _rows_to_dicts(cursor)
                for ff in ff_rows:
                    file_formats.append({
                        'schema_name': ff.get('schema_name'),
                        'name': ff.get('name'),
                        'type': ff.get('type'),
                        'format_options': ff.get('format_options'),
                        'created_on': ff.get('created_on'),
                        'comment': ff.get('comment'),
                    })
            except Exception as e:
                print(f"Could not extract file formats: {e}")

            # 14. Extract Pipes (for continuous data loading)
            pipes = []
            try:
                cursor.execute(f"""
                SHOW PIPES IN DATABASE {database}
                """)
                pipe_rows = _rows_to_dicts(cursor)
                for pipe in pipe_rows:
                    pipes.append({
                        'schema_name': pipe.get('schema_name'),
                        'pipe_name': pipe.get('name'),
                        'definition': pipe.get('definition'),
                        'notification_channel': pipe.get('notification_channel'),
                        'created_on': pipe.get('created_on'),
                        'comment': pipe.get('comment'),
                    })
            except Exception as e:
                print(f"Could not extract pipes: {e}")

            # 15. Extract External Tables
            external_tables = []
            try:
                cursor.execute(f"""
                SHOW EXTERNAL TABLES IN DATABASE {database}
                """)
                ext_rows = _rows_to_dicts(cursor)
                for ext in ext_rows:
                    external_tables.append({
                        'schema_name': ext.get('schema_name'),
                        'table_name': ext.get('name'),
                        'location': ext.get('location'),
                        'file_format': ext.get('file_format_name'),
                        'created_on': ext.get('created_on'),
                    })
            except Exception as e:
                print(f"Could not extract external tables: {e}")

            # 16. Extract Masking Policies
            masking_policies = []
            try:
                cursor.execute(f"""
                SHOW MASKING POLICIES IN DATABASE {database}
                """)
                policy_rows = _rows_to_dicts(cursor)
                for policy in policy_rows:
                    masking_policies.append({
                        'schema_name': policy.get('schema_name'),
                        'policy_name': policy.get('name'),
                        'kind': policy.get('kind'),
                        'return_type': policy.get('return_type'),
                        'body': policy.get('body'),
                        'created_on': policy.get('created_on'),
                    })
            except Exception as e:
                print(f"Could not extract masking policies: {e}")

            # 17. Extract Row Access Policies
            row_access_policies = []
            try:
                cursor.execute(f"""
                SHOW ROW ACCESS POLICIES IN DATABASE {database}
                """)
                rap_rows = _rows_to_dicts(cursor)
                for rap in rap_rows:
                    row_access_policies.append({
                        'schema_name': rap.get('schema_name'),
                        'policy_name': rap.get('name'),
                        'kind': rap.get('kind'),
                        'return_type': rap.get('return_type'),
                        'body': rap.get('body'),
                        'created_on': rap.get('created_on'),
                    })
            except Exception as e:
                print(f"Could not extract row access policies: {e}")

            # 18. Extract Tags
            tags = []
            try:
                cursor.execute(f"""
                SHOW TAGS IN DATABASE {database}
                """)
                tag_rows = _rows_to_dicts(cursor)
                for tag in tag_rows:
                    tags.append({
                        'schema_name': tag.get('schema_name'),
                        'tag_name': tag.get('name'),
                        'allowed_values': tag.get('allowed_values'),
                        'created_on': tag.get('created_on'),
                        'comment': tag.get('comment'),
                    })
            except Exception as e:
                print(f"Could not extract tags: {e}")

            # 19. Extract Materialized Views
            materialized_views = []
            try:
                cursor.execute(f"""
                SHOW MATERIALIZED VIEWS IN DATABASE {database}
                """)
                mv_rows = _rows_to_dicts(cursor)
                for mv in mv_rows:
                    materialized_views.append({
                        'schema_name': mv.get('schema_name'),
                        'view_name': mv.get('name'),
                        'text': mv.get('text'),
                        'cluster_by': mv.get('cluster_by'),
                        'rows': mv.get('rows'),
                        'bytes': mv.get('bytes'),
                        'refresh_state': mv.get('refreshed_on'),
                        'created_on': mv.get('created_on'),
                    })
            except Exception as e:
                print(f"Could not extract materialized views: {e}")

            # 20. Extract Dynamic Tables
            dynamic_tables = []
            try:
                cursor.execute(f"""
                SHOW DYNAMIC TABLES IN DATABASE {database}
                """)
                dt_rows = _rows_to_dicts(cursor)
                for dt in dt_rows:
                    dynamic_tables.append({
                        'schema_name': dt.get('schema_name'),
                        'table_name': dt.get('name'),
                        'text': dt.get('text'),
                        'target_lag': dt.get('target_lag'),
                        'warehouse': dt.get('warehouse'),
                        'scheduling_state': dt.get('scheduling_state'),
                        'created_on': dt.get('created_on'),
                    })
            except Exception as e:
                print(f"Could not extract dynamic tables: {e}")

            # 21. Extract Object Dependencies (using ACCESS_HISTORY if available)
            dependencies = []
            try:
                cursor.execute(f"""
                SELECT DISTINCT
                    REFERENCING_OBJECT_DOMAIN as referencing_type,
                    REFERENCING_DATABASE || '.' || REFERENCING_SCHEMA || '.' || REFERENCING_OBJECT_NAME as referencing_name,
                    REFERENCED_OBJECT_DOMAIN as referenced_type,
                    REFERENCED_DATABASE || '.' || REFERENCED_SCHEMA || '.' || REFERENCED_OBJECT_NAME as referenced_name
                FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
                WHERE REFERENCING_DATABASE = '{database}'
                    AND REFERENCED_DATABASE = '{database}'
                LIMIT 5000
                """)
                dependencies = _rows_to_dicts(cursor)
            except Exception as e:
                print(f"Could not access Object Dependencies: {e}")

            views = _filter_system_objects(views)
            procedures = _filter_system_objects(procedures)
            functions = _filter_system_objects(functions)

            print(f"After filtering: {len(views)} views, {len(procedures)} procedures, {len(functions)} functions")

            # If we get here, connection was successful
            break  # Exit retry loop

        except Exception as exc:
            last_error = exc
            is_transient = _is_transient_error(exc)

            if not is_transient or attempt == max_retries - 1:
                if conn is not None:
                    try:
                        conn.close()
                    except:
                        pass
                error_msg = f"Snowflake connection failed: {exc}"
                if is_transient and attempt == max_retries - 1:
                    error_msg += f"\n\nAttempted {max_retries} times with exponential backoff."
                raise RuntimeError(error_msg) from exc

            # Transient error - retry with exponential backoff
            retry_delay = initial_retry_delay * (2 ** attempt)
            print(f"⚠️  Transient error (attempt {attempt + 1}/{max_retries}): {exc}")
            print(f"   Retrying in {retry_delay:.1f} seconds...")
            time.sleep(retry_delay)

    # Clean up connection
    if conn is not None:
        try:
            conn.close()
        except:
            pass

    # Build comprehensive table map
    table_map: Dict[str, Dict[str, Any]] = {}
    for table in tables:
        key = f"{table['table_schema']}.{table['table_name']}"
        table_map[key] = {
            "schema": table['table_schema'],
            "name": table['table_name'],
            "type": table['table_type'],
            "qualified_name": key,
            "full_name": f"{database}.{key}",
            "description": table.get('description'),
            "row_count": table.get('row_count', 0),
            "bytes": table.get('bytes', 0),
            "clustering_key": table.get('clustering_key'),
            "is_transient": table.get('is_transient'),
            "retention_time": table.get('retention_time'),
            "create_date": str(table.get('create_date')) if table.get('create_date') else None,
            "modify_date": str(table.get('modify_date')) if table.get('modify_date') else None,
            "columns": [],
            "primary_key": [],
            "foreign_keys": [],
            "unique_constraints": [],
            "dependencies": {
                "depends_on": [],
                "referenced_by": [],
            }
        }

    # Process columns
    for column in columns:
        key = f"{column['table_schema']}.{column['table_name']}"
        if key not in table_map:
            continue

        column_details = {
            "name": column['column_name'],
            "ordinal_position": column['ordinal_position'],
            "data_type": column['data_type'],
            "character_maximum_length": column.get('character_maximum_length'),
            "numeric_precision": column.get('numeric_precision'),
            "numeric_scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable'),
            "is_identity": bool(column.get('is_identity')),
            "column_default": column.get('column_default'),
            "comment": column.get('comment'),
            "qualified_name": f"{key}.{column['column_name']}",
        }
        table_map[key]["columns"].append(column_details)

    # Process primary keys
    pk_map = defaultdict(list)
    for pk in primary_keys:
        key = f"{pk['table_schema']}.{pk['table_name']}"
        pk_map[key].append((pk['ordinal_position'], pk['column_name']))

    for key, pk_cols in pk_map.items():
        if key in table_map:
            table_map[key]["primary_key"] = [col for _, col in sorted(pk_cols)]

    # Process foreign keys
    for fk in foreign_keys:
        key = f"{fk['schema_name']}.{fk['table_name']}"
        if key not in table_map:
            continue
        table_map[key]["foreign_keys"].append({
            "constraint": fk['constraint_name'],
            "column": fk['column_name'],
            "references": f"{fk['referenced_schema']}.{fk['referenced_table']}({fk['referenced_column']})",
            "referenced_schema": fk['referenced_schema'],
            "referenced_table": fk['referenced_table'],
            "referenced_column": fk['referenced_column'],
            "delete_action": fk.get('delete_action'),
            "update_action": fk.get('update_action'),
        })

    # Process dependencies
    dependency_graph: Dict[str, set[str]] = defaultdict(set)
    reverse_dependency_graph: Dict[str, set[str]] = defaultdict(set)

    for dep in dependencies:
        if dep.get('referencing_name') and dep.get('referenced_name'):
            referencing = dep['referencing_name'].replace(f"{database}.", "")
            referenced = dep['referenced_name'].replace(f"{database}.", "")
            dependency_graph[referencing].add(referenced)
            reverse_dependency_graph[referenced].add(referencing)

    for key, table in table_map.items():
        table["dependencies"]["depends_on"] = sorted(dependency_graph.get(key, []))
        table["dependencies"]["referenced_by"] = sorted(reverse_dependency_graph.get(key, []))

    # Assemble final metadata
    sorted_tables = sorted(table_map.values(), key=lambda t: (t["schema"], t["name"]))
    table_disambiguation = _build_table_disambiguation_map(sorted_tables, database)
    column_map = _build_column_map(columns, database)

    metadata["tables"] = sorted_tables
    metadata["views"] = views
    metadata["procedures"] = procedures
    metadata["functions"] = functions
    metadata["streams"] = streams
    metadata["tasks"] = tasks
    metadata["stages"] = stages
    metadata["sequences"] = sequences
    metadata["query_history"] = query_history
    metadata["dependencies"] = dependencies
    # Additional Snowflake-specific objects
    metadata["file_formats"] = file_formats
    metadata["pipes"] = pipes
    metadata["external_tables"] = external_tables
    metadata["masking_policies"] = masking_policies
    metadata["row_access_policies"] = row_access_policies
    metadata["tags"] = tags
    metadata["materialized_views"] = materialized_views
    metadata["dynamic_tables"] = dynamic_tables

    # Add parser support maps
    metadata["parser_support"] = {
        "table_disambiguation": table_disambiguation,
        "column_map": column_map,
        "database_name": database,
        "schemas": sorted({t["schema"] for t in metadata["tables"]}),
    }

    # Add summary statistics
    metadata["summary"] = {
        "database": database,
        "account": account,
        "extraction_timestamp": datetime.now(UTC).isoformat(),
        "table_count": len(metadata["tables"]),
        "view_count": len(metadata["views"]),
        "procedure_count": len(metadata["procedures"]),
        "function_count": len(metadata["functions"]),
        "stream_count": len(streams),
        "task_count": len(tasks),
        "stage_count": len(stages),
        "sequence_count": len(sequences),
        "column_count": len(columns),
        "foreign_key_count": len(foreign_keys),
        "schema_count": len(metadata["parser_support"]["schemas"]),
        "unique_table_names": len(table_disambiguation["unique_tables"]),
        "ambiguous_table_names": len(table_disambiguation["ambiguous_tables"]),
        "query_history_count": len(query_history),
        # Additional Snowflake-specific counts
        "file_format_count": len(file_formats),
        "pipe_count": len(pipes),
        "external_table_count": len(external_tables),
        "masking_policy_count": len(masking_policies),
        "row_access_policy_count": len(row_access_policies),
        "tag_count": len(tags),
        "materialized_view_count": len(materialized_views),
        "dynamic_table_count": len(dynamic_tables),
    }

    # Save metadata
    output_directory = _ensure_output_dir(output_dir)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_db = database.replace("/", "-").replace("\\", "-")
    file_path = output_directory / f"enhanced_metadata_{safe_db}_{timestamp}.json"

    with file_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, default=str)

    print(f"Metadata extraction complete. Saved to: {file_path}")
    print(f"Extracted: {metadata['summary']}")

    return metadata, file_path


__all__ = [
    "extract_enhanced_database_metadata",
    "build_connection_params",
    "save_metadata_to_file",
]


if __name__ == "__main__":
    import sys
    import getpass

    print("=" * 70)
    print("Enhanced Snowflake Metadata Extractor")
    print("=" * 70)
    print()

    # Get connection parameters
    if len(sys.argv) >= 4:
        account = sys.argv[1]
        database = sys.argv[2]
        username = sys.argv[3]
        password = sys.argv[4] if len(sys.argv) > 4 else ""
        warehouse = sys.argv[5] if len(sys.argv) > 5 else ""
        authenticator = sys.argv[6] if len(sys.argv) > 6 else "externalbrowser"
    else:
        print("Usage: python enhanced_metadata_extractor.py <account> <database> <username> [password] [warehouse] [authenticator]")
        print("\nOr provide interactively:")
        account = input("Account: ").strip()
        database = input("Database: ").strip()
        username = input("Username: ").strip()
        password = getpass.getpass("Password (leave empty for external browser): ")
        warehouse = input("Warehouse (optional): ").strip()
        authenticator = input("Authenticator (default: externalbrowser): ").strip()
        if not authenticator:
            authenticator = "externalbrowser"

    if not all([account, database, username]):
        print("Error: Account, database, and username are required.")
        sys.exit(1)

    try:
        print(f"\nConnecting to {account}/{database}...")
        metadata, file_path = extract_enhanced_database_metadata(
            account=account,
            database=database,
            username=username,
            password=password,
            warehouse=warehouse,
            authenticator=authenticator
        )
        print(f"\n✓ Success! Metadata saved to: {file_path}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
