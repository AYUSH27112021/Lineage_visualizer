"""Enhanced SQL Server metadata extractor with comprehensive coverage.

This improved version captures:
- Tables, Views, Stored Procedures, Functions
- Query history from system tables
- Extended properties and descriptions
- Triggers and their definitions
- Complete schema hierarchy
- Performance statistics
- Index usage statistics
"""

from __future__ import annotations

import json
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Set, Optional
from collections import defaultdict, deque

import urllib.parse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
import pyodbc


METADATA_OUTPUT_DIR = Path(__file__).parent / "metadata_cache"

SYSTEM_SCHEMAS = (
    'sys', 'INFORMATION_SCHEMA', 'guest',
    'db_owner', 'db_accessadmin', 'db_securityadmin',
    'db_ddladmin', 'db_backupoperator', 'db_datareader',
    'db_datawriter', 'db_denydatareader', 'db_denydatawriter'
)

SYSTEM_SCHEMA_FILTER_LIST = ", ".join(f"'{schema}'" for schema in SYSTEM_SCHEMAS)

SYSTEM_OBJECT_PREFIXES = ('sp_', 'fn_', 'dt_', 'xp_')


def _is_system_object(schema: str, name: str) -> bool:
    """Check if an object is a system object based on schema and name."""
    if schema in SYSTEM_SCHEMAS:
        return True

    name_lower = name.lower()
    if any(name_lower.startswith(prefix) for prefix in SYSTEM_OBJECT_PREFIXES):
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
        schema = obj.get(schema_key, 'dbo')

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


def build_connection_url(server: str, database: str, username: str, password: str, driver: str) -> str:
    """Construct a SQLAlchemy-compatible ODBC connection URL."""
    odbc_parts = [
        f"DRIVER={driver}",
        f"SERVER={server}",
        f"DATABASE={database}",
        f"UID={username}",
        f"PWD={password}",
        "Encrypt=yes",
        "TrustServerCertificate=yes",  # Required for Azure SQL Database
        "Connection Timeout=30",  # 30 seconds connection timeout
        "Login Timeout=30",  # 30 seconds login timeout
    ]
    params = urllib.parse.quote_plus(";".join(part for part in odbc_parts if part))
    return f"mssql+pyodbc:///?odbc_connect={params}"


def _rows_to_dicts(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    return [dict(row._mapping) for row in rows]


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
        schema = table.get('schema', 'dbo')
        name = table['name']
        table_type = table.get('type', 'TABLE')
        
        qualified_name = f"{schema}.{name}"
        full_name = f"{database}.{schema}.{name}"
        
        table_name_counts[name].append(qualified_name)
        schema_tables[schema].append(name)
        
        # Store all possible name variations
        for key in [name, qualified_name, full_name, f"[{schema}].[{name}]", f"[{database}].[{schema}].[{name}]"]:
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
        schema = column.get('table_schema', 'dbo')
        table = column['table_name']
        col_name = column['column_name']
        
        qualified_table = f"{schema}.{table}"
        full_table = f"{database}.{schema}.{table}"
        qualified_column = f"{qualified_table}.{col_name}"
        
        col_metadata = {
            "name": col_name,
            "data_type": column.get('data_type'),
            "size": column.get('size'),
            "scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable'),
            "is_identity": column.get('is_identity', False),
            "is_computed": column.get('is_computed', False),
            "column_default": column.get('column_default'),
            "description": column.get('description'),
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
            "size": column.get('size'),
            "scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable'),
        }
    
    # Identify unique columns
    for col_name, tables in column_name_counts.items():
        if len(tables) == 1:
            column_map["unique_columns"][col_name] = list(tables)[0]
    
    column_map["by_column_name"] = dict(column_map["by_column_name"])
    
    return column_map


def _is_transient_error(error: Exception) -> bool:
    """Check if the error is a transient Azure SQL Database error that should be retried."""
    error_str = str(error).upper()
    # Azure SQL Database transient errors
    transient_indicators = [
        "40613",  # Database not currently available
        "40197",  # Service has encountered an error processing your request
        "40501",  # Service is currently busy
        "4060",   # Cannot open database
        "10928",  # Resource ID exceeded
        "10929",  # Resource ID exceeded
        "10053",  # Transport-level error
        "10054",  # Connection reset
        "10060",  # Connection timeout
        "HY000",  # General error (often transient in Azure)
    ]
    return any(indicator in error_str for indicator in transient_indicators)


def extract_enhanced_database_metadata(
    server: str,
    database: str,
    username: str,
    password: str,
    driver: str = "{ODBC Driver 17 for SQL Server}",
    output_dir: Path | None = None,
    max_retries: int = 5,
    initial_retry_delay: float = 2.0,
) -> Tuple[Dict[str, Any], Path]:
    """Extract comprehensive metadata from SQL Server database.
    
    Args:
        server: SQL Server hostname
        database: Database name
        username: Login username
        password: Login password
        driver: ODBC driver name
        output_dir: Output directory for metadata files
        max_retries: Maximum number of retry attempts for transient errors
        initial_retry_delay: Initial delay in seconds before first retry (exponential backoff)
    
    Returns:
        Tuple of (metadata dictionary, output file path)
    
    Raises:
        RuntimeError: If connection fails after all retries
    """
    
    metadata: Dict[str, Any] = {"database": database, "server": server}
    engine: Optional[Engine] = None
    
    conn_str = build_connection_url(server, database, username, password, driver)
    
    # Retry logic for transient errors
    last_error = None
    for attempt in range(max_retries):
        try:
            if engine is not None:
                engine.dispose()
            
            engine = create_engine(
                conn_str, 
                pool_pre_ping=True,
                connect_args={"timeout": 30},  # Connection timeout in seconds
                pool_timeout=30,  # Pool timeout in seconds
            )

            with engine.connect() as conn:
                # 1. Extract Tables with extended properties
                table_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS table_schema,
                    t.name AS table_name,
                    'TABLE' AS table_type,
                    t.create_date,
                    t.modify_date,
                    ep.value AS description,
                    t.max_column_id_used AS max_columns,
                    p.rows AS row_count
                FROM sys.tables t
                INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                LEFT JOIN sys.extended_properties ep 
                    ON ep.major_id = t.object_id 
                    AND ep.minor_id = 0 
                    AND ep.name = 'MS_Description'
                LEFT JOIN sys.partitions p 
                    ON t.object_id = p.object_id 
                    AND p.index_id IN (0, 1)
                WHERE t.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY s.name, t.name
                """))
                tables = _rows_to_dicts(table_rows)

                # 2. Extract Columns with extended properties
                column_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS table_schema,
                    t.name AS table_name,
                    c.name AS column_name,
                    c.column_id AS ordinal_position,
                    TYPE_NAME(c.system_type_id) AS data_type,
                    CASE 
                        WHEN TYPE_NAME(c.system_type_id) IN ('varchar', 'char', 'nvarchar', 'nchar')
                        THEN c.max_length
                        WHEN TYPE_NAME(c.system_type_id) IN ('decimal', 'numeric')
                        THEN c.precision
                        ELSE NULL
                    END AS size,
                    c.scale AS numeric_scale,
                    c.precision AS numeric_precision,
                    c.is_nullable,
                    c.is_identity,
                    c.is_computed,
                    c.is_hidden,
                    dc.definition AS column_default,
                    cc.definition AS computed_definition,
                    ep.value AS description
                FROM sys.columns c
                INNER JOIN sys.tables t ON c.object_id = t.object_id
                INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
                LEFT JOIN sys.computed_columns cc 
                    ON cc.object_id = c.object_id 
                    AND cc.column_id = c.column_id
                LEFT JOIN sys.extended_properties ep 
                    ON ep.major_id = c.object_id 
                    AND ep.minor_id = c.column_id
                    AND ep.name = 'MS_Description'
                WHERE t.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY s.name, t.name, c.column_id
                """))
                columns = _rows_to_dicts(column_rows)

                # 3. Extract Views with definitions
                view_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS schema_name,
                    v.name AS view_name,
                    m.definition,
                    v.create_date,
                    v.modify_date,
                    ep.value AS description
                FROM sys.views v
                INNER JOIN sys.schemas s ON v.schema_id = s.schema_id
                INNER JOIN sys.sql_modules m ON v.object_id = m.object_id
                LEFT JOIN sys.extended_properties ep 
                    ON ep.major_id = v.object_id 
                    AND ep.minor_id = 0
                    AND ep.name = 'MS_Description'
                WHERE v.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND v.name NOT LIKE 'sys%'
                    AND v.name NOT LIKE 'sp[_]%'
                    AND v.name NOT LIKE 'fn[_]%'
                    AND v.name NOT LIKE 'dt[_]%'
                    AND v.name NOT LIKE 'xp[_]%'
                ORDER BY s.name, v.name
                """))
                views = _rows_to_dicts(view_rows)

                # 4. Extract Stored Procedures
                proc_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS schema_name,
                    p.name AS procedure_name,
                    m.definition,
                    p.create_date,
                    p.modify_date,
                    ep.value AS description
                FROM sys.procedures p
                INNER JOIN sys.schemas s ON p.schema_id = s.schema_id
                INNER JOIN sys.sql_modules m ON p.object_id = m.object_id
                LEFT JOIN sys.extended_properties ep 
                    ON ep.major_id = p.object_id 
                    AND ep.minor_id = 0
                    AND ep.name = 'MS_Description'
                WHERE p.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND p.name NOT LIKE 'sp[_]%'
                    AND p.name NOT LIKE 'dt[_]%'
                    AND p.name NOT LIKE 'fn[_]%'
                    AND p.name NOT LIKE 'xp[_]%'
                    AND p.name NOT LIKE '#%'
                    AND p.name NOT IN (
                        'sp_alterdiagram', 'sp_creatediagram', 'sp_dropdiagram',
                        'sp_helpdiagramdefinition', 'sp_helpdiagrams', 'sp_renamediagram',
                        'sp_upgraddiagrams'
                    )
                ORDER BY s.name, p.name
                """))
                procedures = _rows_to_dicts(proc_rows)

                # 5. Extract Functions (Scalar, Table-valued, Inline)
                function_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS schema_name,
                    o.name AS function_name,
                    o.type_desc AS function_type,
                    m.definition,
                    o.create_date,
                    o.modify_date,
                    ep.value AS description
                FROM sys.objects o
                INNER JOIN sys.schemas s ON o.schema_id = s.schema_id
                INNER JOIN sys.sql_modules m ON o.object_id = m.object_id
                LEFT JOIN sys.extended_properties ep 
                    ON ep.major_id = o.object_id 
                    AND ep.minor_id = 0
                    AND ep.name = 'MS_Description'
                WHERE o.type IN ('FN', 'IF', 'TF', 'FS', 'FT')
                    AND o.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND o.name NOT LIKE 'fn[_]%'
                    AND o.name NOT LIKE 'sp[_]%'
                    AND o.name NOT LIKE 'dt[_]%'
                    AND o.name NOT LIKE 'xp[_]%'
                    AND o.name NOT LIKE '#%'
                    AND o.name NOT IN (
                        'fn_diagramobjects'
                    )
                ORDER BY s.name, o.name
                """))
                functions = _rows_to_dicts(function_rows)

                # 6. Extract Triggers
                trigger_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS schema_name,
                    OBJECT_NAME(tr.parent_id) AS table_name,
                    tr.name AS trigger_name,
                    tr.is_disabled,
                    te.type_desc AS trigger_event,
                    m.definition,
                    tr.create_date,
                    tr.modify_date
                FROM sys.triggers tr
                INNER JOIN sys.trigger_events te ON tr.object_id = te.object_id
                INNER JOIN sys.sql_modules m ON tr.object_id = m.object_id
                INNER JOIN sys.tables t ON tr.parent_id = t.object_id
                INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE tr.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY s.name, t.name, tr.name
                """))
                triggers = _rows_to_dicts(trigger_rows)

                # 7. Extract Primary Keys
                pk_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS TABLE_SCHEMA,
                    t.name AS TABLE_NAME,
                    i.name AS PK_NAME,
                    c.name AS COLUMN_NAME,
                    ic.key_ordinal AS ORDINAL_POSITION
                FROM sys.indexes i
                INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                INNER JOIN sys.tables t ON i.object_id = t.object_id
                INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE i.is_primary_key = 1
                    AND t.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY s.name, t.name, ic.key_ordinal
                """))
                primary_keys = _rows_to_dicts(pk_rows)

                # 8. Extract Foreign Keys
                fk_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS schema_name,
                    t.name AS table_name,
                    fk.name AS constraint_name,
                    c.name AS column_name,
                    rs.name AS referenced_schema,
                    rt.name AS referenced_table,
                    rc.name AS referenced_column,
                    fk.delete_referential_action_desc AS delete_action,
                    fk.update_referential_action_desc AS update_action
                FROM sys.foreign_keys fk
                INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
                INNER JOIN sys.columns c ON fkc.parent_object_id = c.object_id 
                    AND fkc.parent_column_id = c.column_id
                INNER JOIN sys.tables t ON fk.parent_object_id = t.object_id
                INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                INNER JOIN sys.columns rc ON fkc.referenced_object_id = rc.object_id 
                    AND fkc.referenced_column_id = rc.column_id
                INNER JOIN sys.tables rt ON fk.referenced_object_id = rt.object_id
                INNER JOIN sys.schemas rs ON rt.schema_id = rs.schema_id
                WHERE t.is_ms_shipped = 0
                    AND rt.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND rs.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY s.name, t.name, fk.name
                """))
                foreign_keys = _rows_to_dicts(fk_rows)

                # 9. Extract Indexes with usage stats
                index_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS schema_name,
                    t.name AS table_name,
                    i.name AS index_name,
                    i.type_desc AS index_type,
                    i.is_unique,
                    i.is_primary_key,
                    i.is_unique_constraint,
                    i.fill_factor,
                    i.is_disabled,
                    c.name AS column_name,
                    ic.key_ordinal AS column_position,
                    ic.is_included_column,
                    ISNULL(ius.user_seeks, 0) AS user_seeks,
                    ISNULL(ius.user_scans, 0) AS user_scans,
                    ISNULL(ius.user_lookups, 0) AS user_lookups,
                    ISNULL(ius.user_updates, 0) AS user_updates
                FROM sys.indexes i
                INNER JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
                INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                INNER JOIN sys.tables t ON i.object_id = t.object_id
                INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                LEFT JOIN sys.dm_db_index_usage_stats ius 
                    ON i.object_id = ius.object_id 
                    AND i.index_id = ius.index_id
                    AND ius.database_id = DB_ID()
                WHERE t.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY s.name, t.name, i.name, ic.key_ordinal
                """))
                indexes = _rows_to_dicts(index_rows)

                # 10. Extract Query History (if Query Store is enabled) - WITH FILTERS
                query_history = []
                try:
                    # Check if Query Store is enabled
                    qs_check = conn.execute(text("""
                    SELECT is_query_store_on 
                    FROM sys.databases 
                    WHERE database_id = DB_ID()
                    """)).fetchone()
                    
                    if qs_check and qs_check[0]:
                        print("Query Store enabled - extracting filtered query history...")
                        
                        # Get schema names dynamically for filtering
                        schema_rows = conn.execute(text(f"""
                        SELECT name FROM sys.schemas 
                        WHERE name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                        """)).fetchall()
                        
                        user_schemas = [row[0] for row in schema_rows]
                        schema_patterns = ' OR '.join([f"qt.query_sql_text LIKE '%{schema}.%'" for schema in user_schemas])
                        
                        query_sql = f"""
                        SELECT TOP 1000
                            qt.query_text_id,
                            qt.query_sql_text,
                            q.query_hash,
                            p.plan_id,
                            rs.execution_type_desc,
                            rs.count_executions,
                            rs.avg_duration / 1000.0 AS avg_duration_ms,
                            rs.avg_cpu_time / 1000.0 AS avg_cpu_time_ms,
                            rs.avg_logical_io_reads,
                            rs.avg_logical_io_writes,
                            rs.last_execution_time,
                            rs.first_execution_time
                        FROM sys.query_store_query_text qt
                        INNER JOIN sys.query_store_query q ON qt.query_text_id = q.query_text_id
                        INNER JOIN sys.query_store_plan p ON q.query_id = p.query_id
                        INNER JOIN sys.query_store_runtime_stats rs ON p.plan_id = rs.plan_id
                        WHERE 
                            rs.last_execution_time > DATEADD(day, -30, GETUTCDATE())
                            
                            -- Exclude system queries
                            AND qt.query_sql_text NOT LIKE '%sys.%'
                            AND qt.query_sql_text NOT LIKE '%INFORMATION_SCHEMA%'
                            AND qt.query_sql_text NOT LIKE '%sys.dm_%'
                            AND qt.query_sql_text NOT LIKE '%SCHEMA_NAME%'
                            AND qt.query_sql_text NOT LIKE '%OBJECT_ID%'
                            
                            -- Exclude SSMS metadata queries
                            AND qt.query_sql_text NOT LIKE '(@_msparam_%'
                            AND qt.query_sql_text NOT LIKE '(@databaseId int)%'
                            
                            -- Exclude Query Store internal
                            AND qt.query_sql_text NOT LIKE '%query_store%'
                            
                            -- Exclude maintenance
                            AND qt.query_sql_text NOT LIKE '%BACKUP%'
                            AND qt.query_sql_text NOT LIKE '%DBCC%'
                            
                            -- Only user schema queries
                            AND ({schema_patterns} OR (
                                qt.query_sql_text LIKE '%SELECT%'
                                AND LEN(qt.query_sql_text) > 50
                            ))
                            
                            -- Minimum length
                            AND LEN(qt.query_sql_text) >= 50
                            
                        ORDER BY rs.count_executions DESC
                        """
                        
                        query_rows = conn.execute(text(query_sql))
                        query_history = _rows_to_dicts(query_rows)
                        
                        print(f"Extracted {len(query_history)} user queries (system queries filtered out)")
                        
                except Exception as e:
                    # Query Store might not be enabled or accessible
                    print(f"Could not access Query Store: {e}")
                    query_history = []

                # 11. Extract Dependencies (handle SQL Server version differences)
                dependency_flag_columns = ("is_ambiguous", "is_selected", "is_updated", "is_select_all")
                dependency_column_rows = conn.execute(text("""
                SELECT name
                FROM sys.columns
                WHERE object_id = OBJECT_ID('sys.sql_expression_dependencies')
                  AND name IN ('is_ambiguous', 'is_selected', 'is_updated', 'is_select_all')
                """)).fetchall()
                available_dependency_columns = {row[0] for row in dependency_column_rows}

                dependency_select_parts = [
                    "s_from.name AS referencing_schema",
                    "o_from.name AS referencing_name",
                    "o_from.type_desc AS referencing_type",
                    "s_to.name AS referenced_schema",
                    "o_to.name AS referenced_name",
                    "o_to.type_desc AS referenced_type",
                ]

                optional_column_map = {
                    "is_ambiguous": "dep.is_ambiguous AS is_ambiguous",
                    "is_selected": "dep.is_selected AS is_selected",
                    "is_updated": "dep.is_updated AS is_updated",
                    "is_select_all": "dep.is_select_all AS is_select_all",
                }

                for column_name in dependency_flag_columns:
                    if column_name in available_dependency_columns:
                        dependency_select_parts.append(optional_column_map[column_name])

                dependency_query = f"""
                SELECT
                    {",\n                    ".join(dependency_select_parts)}
                FROM sys.sql_expression_dependencies dep
                LEFT JOIN sys.objects o_from ON dep.referencing_id = o_from.object_id
                LEFT JOIN sys.schemas s_from ON o_from.schema_id = s_from.schema_id
                LEFT JOIN sys.objects o_to ON dep.referenced_id = o_to.object_id
                LEFT JOIN sys.schemas s_to ON o_to.schema_id = s_to.schema_id
                WHERE (dep.referenced_database_name IS NULL OR dep.referenced_database_name = DB_NAME())
                    AND o_from.name IS NOT NULL
                    AND o_to.name IS NOT NULL
                    AND (o_from.is_ms_shipped = 0 OR o_from.is_ms_shipped IS NULL)
                    AND (o_to.is_ms_shipped = 0 OR o_to.is_ms_shipped IS NULL)
                    AND (s_from.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST}) OR s_from.name IS NULL)
                    AND (s_to.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST}) OR s_to.name IS NULL)
                ORDER BY s_from.name, o_from.name
                """

                dependency_rows = conn.execute(text(dependency_query))
                dependencies = _rows_to_dicts(dependency_rows)
                for dependency in dependencies:
                    for column_name in dependency_flag_columns:
                        dependency.setdefault(column_name, None)

                # 12. Extract Check Constraints
                check_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS schema_name,
                    t.name AS table_name,
                    cc.name AS constraint_name,
                    cc.definition,
                    cc.is_disabled
                FROM sys.check_constraints cc
                INNER JOIN sys.tables t ON cc.parent_object_id = t.object_id
                INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE t.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY s.name, t.name, cc.name
                """))
                check_constraints = _rows_to_dicts(check_rows)

                # 13. Extract Unique Constraints
                unique_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS schema_name,
                    t.name AS table_name,
                    kc.name AS constraint_name,
                    c.name AS column_name,
                    ic.key_ordinal AS ordinal_position
                FROM sys.key_constraints kc
                INNER JOIN sys.index_columns ic ON kc.parent_object_id = ic.object_id 
                    AND kc.unique_index_id = ic.index_id
                INNER JOIN sys.columns c ON ic.object_id = c.object_id 
                    AND ic.column_id = c.column_id
                INNER JOIN sys.tables t ON kc.parent_object_id = t.object_id
                INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
                WHERE kc.type = 'UQ'
                    AND t.is_ms_shipped = 0
                    AND s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY s.name, t.name, kc.name, ic.key_ordinal
                """))
                unique_constraints = _rows_to_dicts(unique_rows)

                # 14. Extract Sequences (handle unsupported ODBC types)
                sequences = []
                try:
                    sequence_rows = conn.execute(text(f"""
                    SELECT 
                        s.name AS schema_name,
                        seq.name AS sequence_name,
                        CAST(TYPE_NAME(seq.system_type_id) AS VARCHAR(128)) AS data_type,
                        CAST(seq.start_value AS BIGINT) AS start_value,
                        CAST(seq.increment AS BIGINT) AS increment,
                        CAST(seq.minimum_value AS BIGINT) AS minimum_value,
                        CAST(seq.maximum_value AS BIGINT) AS maximum_value,
                        CAST(seq.is_cycling AS BIT) AS is_cycling,
                        CAST(seq.current_value AS BIGINT) AS current_value
                    FROM sys.sequences seq
                    INNER JOIN sys.schemas s ON seq.schema_id = s.schema_id
                    WHERE s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    ORDER BY s.name, seq.name
                    """))
                    sequences = _rows_to_dicts(sequence_rows)
                except Exception as e:
                    # Handle unsupported ODBC types gracefully
                    print(f"Could not extract sequences (unsupported ODBC type): {e}")
                    sequences = []

                # 15. Extract Synonyms
                synonym_rows = conn.execute(text(f"""
                SELECT 
                    s.name AS schema_name,
                    syn.name AS synonym_name,
                    syn.base_object_name AS target_object,
                    syn.create_date,
                    syn.modify_date
                FROM sys.synonyms syn
                INNER JOIN sys.schemas s ON syn.schema_id = s.schema_id
                WHERE s.name NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY s.name, syn.name
                """))
                synonyms = _rows_to_dicts(synonym_rows)

                views = _filter_system_objects(views)
                procedures = _filter_system_objects(procedures)
                functions = _filter_system_objects(functions)

                print(f"After filtering: {len(views)} views, {len(procedures)} procedures, {len(functions)} functions")
                
                # If we get here, connection was successful
                break  # Exit retry loop
            
        except (SQLAlchemyError, pyodbc.Error) as exc:
            last_error = exc
            is_transient = _is_transient_error(exc)
            
            if not is_transient or attempt == max_retries - 1:
                if engine is not None:
                    engine.dispose()
                error_msg = f"Database connection failed: {exc}"
                if is_transient and attempt == max_retries - 1:
                    error_msg += f"\n\nAttempted {max_retries} times with exponential backoff. The database may be paused or unavailable."
                    error_msg += "\nFor Azure SQL Database, check if the database is paused in the Azure portal."
                raise RuntimeError(error_msg) from exc
            
            # Transient error - retry with exponential backoff
            retry_delay = initial_retry_delay * (2 ** attempt)
            print(f"⚠️  Transient error (attempt {attempt + 1}/{max_retries}): {exc}")
            print(f"   Retrying in {retry_delay:.1f} seconds...")
            time.sleep(retry_delay)
    
    # Clean up engine if we're done
    if engine is not None:
        try:
            engine.dispose()
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
            "create_date": str(table.get('create_date')) if table.get('create_date') else None,
            "modify_date": str(table.get('modify_date')) if table.get('modify_date') else None,
            "columns": [],
            "primary_key": [],
            "foreign_keys": [],
            "indexes": [],
            "unique_constraints": [],
            "check_constraints": [],
            "triggers": [],
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
            "size": column.get('size'),
            "scale": column.get('numeric_scale'),
            "precision": column.get('numeric_precision'),
            "is_nullable": column.get('is_nullable'),
            "is_identity": bool(column.get('is_identity')),
            "is_computed": bool(column.get('is_computed')),
            "is_hidden": bool(column.get('is_hidden')),
            "column_default": column.get('column_default'),
            "computed_definition": column.get('computed_definition'),
            "description": column.get('description'),
            "qualified_name": f"{key}.{column['column_name']}",
        }
        table_map[key]["columns"].append(column_details)

    # Process primary keys
    pk_map = defaultdict(list)
    for pk in primary_keys:
        key = f"{pk['TABLE_SCHEMA']}.{pk['TABLE_NAME']}"
        pk_map[key].append((pk['ORDINAL_POSITION'], pk['COLUMN_NAME']))
    
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

    # Process indexes
    index_map = defaultdict(lambda: defaultdict(dict))
    for idx in indexes:
        key = f"{idx['schema_name']}.{idx['table_name']}"
        idx_name = idx['index_name']
        if 'columns' not in index_map[key][idx_name]:
            index_map[key][idx_name]['columns'] = []
            index_map[key][idx_name]['included_columns'] = []
            index_map[key][idx_name].update({
                'name': idx_name,
                'type': idx['index_type'],
                'is_unique': idx.get('is_unique'),
                'is_primary_key': idx.get('is_primary_key'),
                'is_disabled': idx.get('is_disabled'),
                'fill_factor': idx.get('fill_factor'),
                'usage_stats': {
                    'seeks': idx.get('user_seeks', 0),
                    'scans': idx.get('user_scans', 0),
                    'lookups': idx.get('user_lookups', 0),
                    'updates': idx.get('user_updates', 0),
                }
            })
        
        if idx.get('is_included_column'):
            index_map[key][idx_name]['included_columns'].append(idx['column_name'])
        else:
            index_map[key][idx_name]['columns'].append((idx['column_position'], idx['column_name']))
    
    # Sort index columns and add to table map
    for key, idx_dict in index_map.items():
        if key in table_map:
            for idx_info in idx_dict.values():
                idx_info['columns'] = [col for _, col in sorted(idx_info['columns'])]
                table_map[key]["indexes"].append(idx_info)

    # Process unique constraints
    unique_map = defaultdict(lambda: defaultdict(list))
    for uc in unique_constraints:
        key = f"{uc['schema_name']}.{uc['table_name']}"
        unique_map[key][uc['constraint_name']].append((uc['ordinal_position'], uc['column_name']))
    
    for key, constraints in unique_map.items():
        if key in table_map:
            table_map[key]["unique_constraints"] = [
                {"constraint_name": name, "columns": [col for _, col in sorted(cols)]}
                for name, cols in constraints.items()
            ]

    # Process check constraints
    for cc in check_constraints:
        key = f"{cc['schema_name']}.{cc['table_name']}"
        if key in table_map:
            table_map[key]["check_constraints"].append({
                "constraint_name": cc['constraint_name'],
                "definition": cc['definition'],
                "is_disabled": cc.get('is_disabled', False)
            })

    # Process triggers
    for trigger in triggers:
        key = f"{trigger['schema_name']}.{trigger['table_name']}"
        if key in table_map:
            table_map[key]["triggers"].append({
                "name": trigger['trigger_name'],
                "event": trigger.get('trigger_event'),
                "definition": trigger.get('definition'),
                "is_disabled": trigger.get('is_disabled', False),
                "create_date": str(trigger.get('create_date')) if trigger.get('create_date') else None,
                "modify_date": str(trigger.get('modify_date')) if trigger.get('modify_date') else None,
            })

    # Process dependencies
    dependency_graph: Dict[str, set[str]] = defaultdict(set)
    reverse_dependency_graph: Dict[str, set[str]] = defaultdict(set)
    
    for dep in dependencies:
        if dep.get('referencing_name') and dep.get('referenced_name'):
            referencing = f"{dep['referencing_schema']}.{dep['referencing_name']}"
            referenced = f"{dep['referenced_schema']}.{dep['referenced_name']}"
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
    metadata["triggers"] = triggers
    metadata["sequences"] = sequences
    metadata["synonyms"] = synonyms
    metadata["query_history"] = query_history
    metadata["dependencies"] = dependencies
    
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
        "server": server,
        "extraction_timestamp": datetime.now(UTC).isoformat(),
        "table_count": len(metadata["tables"]),
        "view_count": len(metadata["views"]),
        "procedure_count": len(metadata["procedures"]),
        "function_count": len(metadata["functions"]),
        "trigger_count": len(triggers),
        "sequence_count": len(sequences),
        "synonym_count": len(synonyms),
        "column_count": len(columns),
        "index_count": len(set((idx['schema_name'], idx['table_name'], idx['index_name']) 
                              for idx in indexes)),
        "foreign_key_count": len(foreign_keys),
        "schema_count": len(metadata["parser_support"]["schemas"]),
        "unique_table_names": len(table_disambiguation["unique_tables"]),
        "ambiguous_table_names": len(table_disambiguation["ambiguous_tables"]),
        "query_history_count": len(query_history),
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


__all__ = ["extract_enhanced_database_metadata", "build_connection_url"]


if __name__ == "__main__":
    import sys
    import getpass
    
    print("=" * 70)
    print("Enhanced SQL Server Metadata Extractor")
    print("=" * 70)
    print()
    
    # Get connection parameters
    if len(sys.argv) >= 5:
        server = sys.argv[1]
        database = sys.argv[2]
        username = sys.argv[3]
        password = sys.argv[4]
        driver = sys.argv[5] if len(sys.argv) > 5 else "{ODBC Driver 18 for SQL Server}"
    else:
        print("Usage: python enhanced_metadata_extractor.py <server> <database> <username> <password> [driver]")
        print("\nOr provide interactively:")
        server = input("Server: ").strip()
        database = input("Database: ").strip()
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        driver = input("ODBC Driver (default: {ODBC Driver 18 for SQL Server}): ").strip()
        if not driver:
            driver = "{ODBC Driver 18 for SQL Server}"
    
    if not all([server, database, username, password]):
        print("Error: All connection parameters are required.")
        sys.exit(1)
    
    try:
        print(f"\nConnecting to {server}/{database}...")
        metadata, file_path = extract_enhanced_database_metadata(
            server=server,
            database=database,
            username=username,
            password=password,
            driver=driver
        )
        print(f"\n✓ Success! Metadata saved to: {file_path}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
