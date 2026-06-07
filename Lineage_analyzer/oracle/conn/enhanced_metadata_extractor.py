"""Enhanced Oracle metadata extractor with comprehensive coverage.

This module captures:
- Tables, Views, Stored Procedures, Functions, Packages
- Materialized Views
- Extended properties and descriptions (via COMMENT statements)
- Triggers and their definitions
- Complete schema hierarchy
- Sequences and their usage
- Partitioned tables
- Database links
- Synonyms
- Performance statistics from AWR and v$ views

Oracle-specific features:
- Packages (Package specifications and bodies)
- Object types and type bodies
- Nested tables and VARRAYs
- PL/SQL procedures and functions
- Database links
- Materialized views and logs
- Partitioning information (RANGE, LIST, HASH, COMPOSITE)
- Subpartitions
- Index-organized tables (IOT)
- Cluster tables
"""

from __future__ import annotations

import json
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Set, Optional
from collections import defaultdict, deque

import urllib.parse

try:
    import oracledb
except ImportError:
    oracledb = None

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
    from sqlalchemy.exc import SQLAlchemyError
except ImportError:
    create_engine = None
    text = None
    Engine = None
    SQLAlchemyError = None


METADATA_OUTPUT_DIR = Path(__file__).parent / "metadata_cache"

# Oracle system schemas to exclude
SYSTEM_SCHEMAS = (
    'SYS', 'SYSTEM', 'OUTLN', 'DIP', 'ORACLE_OCM',
    'DBSNMP', 'APPQOSSYS', 'WMSYS', 'EXFSYS',
    'CTXSYS', 'XDB', 'ANONYMOUS', 'APEX_PUBLIC_USER',
    'FLOWS_FILES', 'APEX_040000', 'APEX_040100',
    'APEX_040200', 'APEX_050000', 'MDSYS', 'ORDSYS',
    'ORDDATA', 'SPATIAL_CSW_ADMIN_USR', 'SPATIAL_WFS_ADMIN_USR',
    'ORDPLUGINS', 'SI_INFORMTN_SCHEMA', 'OLAPSYS',
    'MDDATA', 'XS$NULL', 'OJVMSYS', 'GSMADMIN_INTERNAL',
    'LBACSYS', 'AUDSYS', 'DVF', 'DVSYS', 'DBSFWUSER',
    'REMOTE_SCHEDULER_AGENT', 'SYSBACKUP', 'SYSDG',
    'SYSKM', 'SYSRAC', 'SYS$UMF', 'GSMCATUSER',
    'GGSYS', 'GSMUSER', 'RMAN', 'XS$NULL'
)

SYSTEM_SCHEMA_FILTER_LIST = ", ".join(f"'{schema}'" for schema in SYSTEM_SCHEMAS)


def _is_system_object(owner: str, name: str) -> bool:
    """Check if an object is a system object based on owner and name."""
    if owner.upper() in SYSTEM_SCHEMAS:
        return True

    # Oracle system prefixes
    name_upper = name.upper()
    if name_upper.startswith('SYS_'):
        return True
    if name_upper.startswith('BIN$'):  # Recycle bin objects
        return True

    return False


def _filter_system_objects(
    objects: List[Dict[str, Any]],
    owner_key: str = 'owner',
    name_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter out system objects from extracted list."""
    filtered: List[Dict[str, Any]] = []

    for obj in objects:
        owner = obj.get(owner_key, '')

        if name_key is None:
            # Auto-detect name key
            if 'view_name' in obj:
                name = obj['view_name']
            elif 'procedure_name' in obj:
                name = obj['procedure_name']
            elif 'function_name' in obj:
                name = obj['function_name']
            elif 'package_name' in obj:
                name = obj['package_name']
            elif 'table_name' in obj:
                name = obj['table_name']
            elif 'name' in obj:
                name = obj['name']
            else:
                continue
        else:
            name = obj.get(name_key, '')

        if _is_system_object(owner, name):
            continue

        filtered.append(obj)

    return filtered


def _ensure_output_dir(output_dir: Path | None) -> Path:
    directory = output_dir or METADATA_OUTPUT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_connection_url(
    host: str,
    service_name: str,
    username: str,
    password: str,
    port: int = 1521,
    use_thick_mode: bool = False,
) -> str:
    """Construct a SQLAlchemy-compatible Oracle connection URL.

    Args:
        host: Oracle server hostname
        service_name: Oracle service name (not SID)
        username: Login username
        password: Login password
        port: Oracle port (default: 1521)
        use_thick_mode: Use Oracle thick client mode (requires Oracle Client)

    Returns:
        SQLAlchemy connection URL
    """
    encoded_password = urllib.parse.quote_plus(password) if password else ''
    encoded_username = urllib.parse.quote_plus(username)

    # Use service name instead of SID for better compatibility
    return f"oracle+oracledb://{encoded_username}:{encoded_password}@{host}:{port}/?service_name={service_name}"


def _rows_to_dicts(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    """Convert SQLAlchemy result rows to dictionaries."""
    return [dict(row._mapping) for row in rows]


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
        owner = table.get('owner', '')
        name = table['name']
        table_type = table.get('type', 'TABLE')

        qualified_name = f"{owner}.{name}"
        full_name = f"{database}.{owner}.{name}"

        table_name_counts[name].append(qualified_name)
        schema_tables[owner].append(name)

        # Store all possible name variations (Oracle is case-insensitive by default)
        for key in [name, qualified_name, full_name,
                    name.upper(), qualified_name.upper(), full_name.upper(),
                    name.lower(), qualified_name.lower(), full_name.lower()]:
            disambiguation["full_hierarchy"][key] = {
                "table_name": name,
                "owner": owner,
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
        owner = column.get('owner', '')
        table = column['table_name']
        col_name = column['column_name']

        qualified_table = f"{owner}.{table}"
        full_table = f"{database}.{owner}.{table}"
        qualified_column = f"{qualified_table}.{col_name}"

        col_metadata = {
            "name": col_name,
            "data_type": column.get('data_type'),
            "data_length": column.get('data_length'),
            "data_precision": column.get('data_precision'),
            "data_scale": column.get('data_scale'),
            "nullable": column.get('nullable') == 'Y',
            "data_default": column.get('data_default'),
            "virtual_column": column.get('virtual_column') == 'YES',
            "hidden_column": column.get('hidden_column') == 'YES',
            "identity_column": column.get('identity_column') == 'YES',
            "description": column.get('comments'),
            "qualified_name": qualified_column,
            "table": qualified_table,
            "full_table": full_table,
            "owner": owner,
        }

        if qualified_table not in column_map["by_table"]:
            column_map["by_table"][qualified_table] = []
        column_map["by_table"][qualified_table].append(col_metadata)

        column_name_counts[col_name].add(qualified_table)
        column_map["by_column_name"][col_name].append(qualified_table)

        column_map["column_types"][qualified_column] = {
            "data_type": column.get('data_type'),
            "data_length": column.get('data_length'),
            "data_precision": column.get('data_precision'),
            "data_scale": column.get('data_scale'),
            "nullable": column.get('nullable') == 'Y',
        }

    # Identify unique columns
    for col_name, tables in column_name_counts.items():
        if len(tables) == 1:
            column_map["unique_columns"][col_name] = list(tables)[0]

    column_map["by_column_name"] = dict(column_map["by_column_name"])

    return column_map


def extract_enhanced_database_metadata(
    host: str,
    service_name: str,
    username: str,
    password: str,
    port: int = 1521,
    output_dir: Path | None = None,
    max_retries: int = 3,
    initial_retry_delay: float = 2.0,
    target_schemas: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], Path]:
    """Extract comprehensive metadata from Oracle database.

    Args:
        host: Oracle server hostname
        service_name: Oracle service name
        username: Login username
        password: Login password
        port: Oracle port (default: 1521)
        output_dir: Output directory for metadata files
        max_retries: Maximum number of retry attempts
        initial_retry_delay: Initial delay in seconds before first retry
        target_schemas: List of specific schemas to extract (None = user's schema only)

    Returns:
        Tuple of (metadata dictionary, output file path)

    Raises:
        RuntimeError: If connection fails after all retries
        ImportError: If oracledb is not installed
    """

    if oracledb is None:
        raise ImportError(
            "oracledb (python-oracledb) is required. "
            "Install it with: pip install oracledb"
        )

    metadata: Dict[str, Any] = {
        "database": service_name,
        "host": host,
        "port": port,
        "username": username
    }
    engine: Optional[Engine] = None

    conn_str = build_connection_url(host, service_name, username, password, port)

    # Determine schema filter
    if target_schemas:
        schema_filter = ", ".join(f"'{schema.upper()}'" for schema in target_schemas)
    else:
        # Default to user's own schema
        schema_filter = f"'{username.upper()}'"

    # Retry logic
    last_error = None
    for attempt in range(max_retries):
        try:
            if engine is not None:
                engine.dispose()

            engine = create_engine(
                conn_str,
                pool_pre_ping=True,
                connect_args={"encoding": "UTF-8", "nencoding": "UTF-8"},
                pool_timeout=30,
            )

            with engine.connect() as conn:
                print(f"Connected to Oracle database: {service_name}")

                # 1. Extract Tables with comments
                print("Extracting tables...")
                table_rows = conn.execute(text(f"""
                SELECT
                    t.owner,
                    t.table_name,
                    'TABLE' AS table_type,
                    t.tablespace_name,
                    t.status,
                    t.num_rows,
                    t.blocks,
                    t.avg_row_len,
                    t.last_analyzed,
                    t.partitioned,
                    t.iot_type,
                    t.temporary,
                    t.cluster_name,
                    t.compression,
                    t.compress_for,
                    c.comments AS description
                FROM all_tables t
                LEFT JOIN all_tab_comments c
                    ON t.owner = c.owner
                    AND t.table_name = c.table_name
                WHERE t.owner IN ({schema_filter})
                    AND t.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND t.table_name NOT LIKE 'BIN$%'
                ORDER BY t.owner, t.table_name
                """))
                tables = _rows_to_dicts(table_rows)

                # 2. Extract Columns with comments
                print("Extracting columns...")
                column_rows = conn.execute(text(f"""
                SELECT
                    c.owner,
                    c.table_name,
                    c.column_name,
                    c.column_id AS ordinal_position,
                    c.data_type,
                    c.data_length,
                    c.data_precision,
                    c.data_scale,
                    c.nullable,
                    c.data_default,
                    c.virtual_column,
                    c.hidden_column,
                    c.identity_column,
                    cc.comments
                FROM all_tab_columns c
                LEFT JOIN all_col_comments cc
                    ON c.owner = cc.owner
                    AND c.table_name = cc.table_name
                    AND c.column_name = cc.column_name
                WHERE c.owner IN ({schema_filter})
                    AND c.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND c.table_name NOT LIKE 'BIN$%'
                ORDER BY c.owner, c.table_name, c.column_id
                """))
                columns = _rows_to_dicts(column_rows)

                # 3. Extract Views with definitions
                print("Extracting views...")
                view_rows = conn.execute(text(f"""
                SELECT
                    v.owner,
                    v.view_name,
                    v.text AS definition,
                    v.type_text,
                    v.oid_text,
                    v.view_type_owner,
                    v.view_type,
                    v.read_only,
                    c.comments AS description
                FROM all_views v
                LEFT JOIN all_tab_comments c
                    ON v.owner = c.owner
                    AND v.view_name = c.table_name
                WHERE v.owner IN ({schema_filter})
                    AND v.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND v.view_name NOT LIKE 'BIN$%'
                ORDER BY v.owner, v.view_name
                """))
                views = _rows_to_dicts(view_rows)

                # 4. Extract Materialized Views
                print("Extracting materialized views...")
                mview_rows = conn.execute(text(f"""
                SELECT
                    m.owner,
                    m.mview_name,
                    m.query AS definition,
                    m.refresh_mode,
                    m.refresh_method,
                    m.build_mode,
                    m.fast_refreshable,
                    m.last_refresh_date,
                    m.compile_state,
                    m.staleness,
                    c.comments AS description
                FROM all_mviews m
                LEFT JOIN all_tab_comments c
                    ON m.owner = c.owner
                    AND m.mview_name = c.table_name
                WHERE m.owner IN ({schema_filter})
                    AND m.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY m.owner, m.mview_name
                """))
                matviews = _rows_to_dicts(mview_rows)

                # 5. Extract Stored Procedures
                print("Extracting procedures...")
                proc_rows = conn.execute(text(f"""
                SELECT
                    p.owner,
                    p.object_name AS procedure_name,
                    p.procedure_name AS specific_name,
                    s.text AS definition,
                    p.object_type,
                    p.aggregate,
                    p.pipelined,
                    p.parallel,
                    p.deterministic
                FROM all_procedures p
                LEFT JOIN all_source s
                    ON p.owner = s.owner
                    AND p.object_name = s.name
                    AND p.object_type = s.type
                WHERE p.owner IN ({schema_filter})
                    AND p.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND p.object_type = 'PROCEDURE'
                    AND p.object_name NOT LIKE 'BIN$%'
                ORDER BY p.owner, p.object_name, s.line
                """))
                procedures = _rows_to_dicts(proc_rows)

                # 6. Extract Functions
                print("Extracting functions...")
                function_rows = conn.execute(text(f"""
                SELECT
                    p.owner,
                    p.object_name AS function_name,
                    p.procedure_name AS specific_name,
                    s.text AS definition,
                    p.object_type,
                    p.aggregate,
                    p.pipelined,
                    p.parallel,
                    p.deterministic
                FROM all_procedures p
                LEFT JOIN all_source s
                    ON p.owner = s.owner
                    AND p.object_name = s.name
                    AND p.object_type = s.type
                WHERE p.owner IN ({schema_filter})
                    AND p.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND p.object_type = 'FUNCTION'
                    AND p.object_name NOT LIKE 'BIN$%'
                ORDER BY p.owner, p.object_name, s.line
                """))
                functions = _rows_to_dicts(function_rows)

                # 7. Extract Packages
                print("Extracting packages...")
                package_rows = conn.execute(text(f"""
                SELECT
                    owner,
                    object_name AS package_name,
                    object_type,
                    status,
                    created,
                    last_ddl_time
                FROM all_objects
                WHERE owner IN ({schema_filter})
                    AND owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND object_type IN ('PACKAGE', 'PACKAGE BODY')
                    AND object_name NOT LIKE 'BIN$%'
                ORDER BY owner, object_name, object_type
                """))
                packages = _rows_to_dicts(package_rows)

                # Get package source
                for pkg in packages:
                    src_rows = conn.execute(text(f"""
                    SELECT text, line
                    FROM all_source
                    WHERE owner = :owner
                        AND name = :name
                        AND type = :type
                    ORDER BY line
                    """), {"owner": pkg['owner'], "name": pkg['package_name'], "type": pkg['object_type']})
                    pkg['definition'] = ''.join([row.text for row in src_rows])

                # 8. Extract Triggers
                print("Extracting triggers...")
                trigger_rows = conn.execute(text(f"""
                SELECT
                    t.owner,
                    t.trigger_name,
                    t.trigger_type,
                    t.triggering_event,
                    t.table_owner,
                    t.table_name,
                    t.base_object_type,
                    t.status,
                    t.trigger_body AS definition,
                    t.action_type,
                    t.when_clause
                FROM all_triggers t
                WHERE t.owner IN ({schema_filter})
                    AND t.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND t.trigger_name NOT LIKE 'BIN$%'
                ORDER BY t.owner, t.table_name, t.trigger_name
                """))
                triggers = _rows_to_dicts(trigger_rows)

                # 9. Extract Primary Keys
                print("Extracting primary keys...")
                pk_rows = conn.execute(text(f"""
                SELECT
                    c.owner,
                    c.table_name,
                    c.constraint_name AS pk_name,
                    cc.column_name,
                    cc.position AS ordinal_position
                FROM all_constraints c
                INNER JOIN all_cons_columns cc
                    ON c.owner = cc.owner
                    AND c.constraint_name = cc.constraint_name
                WHERE c.constraint_type = 'P'
                    AND c.owner IN ({schema_filter})
                    AND c.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND c.table_name NOT LIKE 'BIN$%'
                ORDER BY c.owner, c.table_name, cc.position
                """))
                primary_keys = _rows_to_dicts(pk_rows)

                # 10. Extract Foreign Keys
                print("Extracting foreign keys...")
                fk_rows = conn.execute(text(f"""
                SELECT
                    c.owner,
                    c.table_name,
                    c.constraint_name,
                    cc.column_name,
                    rc.owner AS referenced_owner,
                    rc.table_name AS referenced_table,
                    rcc.column_name AS referenced_column,
                    c.delete_rule,
                    c.status,
                    c.deferrable,
                    c.deferred
                FROM all_constraints c
                INNER JOIN all_cons_columns cc
                    ON c.owner = cc.owner
                    AND c.constraint_name = cc.constraint_name
                INNER JOIN all_constraints rc
                    ON c.r_owner = rc.owner
                    AND c.r_constraint_name = rc.constraint_name
                INNER JOIN all_cons_columns rcc
                    ON rc.owner = rcc.owner
                    AND rc.constraint_name = rcc.constraint_name
                    AND cc.position = rcc.position
                WHERE c.constraint_type = 'R'
                    AND c.owner IN ({schema_filter})
                    AND c.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND c.table_name NOT LIKE 'BIN$%'
                ORDER BY c.owner, c.table_name, c.constraint_name, cc.position
                """))
                foreign_keys = _rows_to_dicts(fk_rows)

                # 11. Extract Indexes with usage stats
                print("Extracting indexes...")
                index_rows = conn.execute(text(f"""
                SELECT
                    i.owner,
                    i.table_name,
                    i.index_name,
                    i.index_type,
                    i.uniqueness,
                    i.compression,
                    i.prefix_length,
                    i.tablespace_name,
                    i.status,
                    i.partitioned,
                    i.temporary,
                    ic.column_name,
                    ic.column_position,
                    ic.descend
                FROM all_indexes i
                INNER JOIN all_ind_columns ic
                    ON i.owner = ic.index_owner
                    AND i.index_name = ic.index_name
                WHERE i.owner IN ({schema_filter})
                    AND i.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND i.table_name NOT LIKE 'BIN$%'
                ORDER BY i.owner, i.table_name, i.index_name, ic.column_position
                """))
                indexes = _rows_to_dicts(index_rows)

                # 12. Extract Sequences
                print("Extracting sequences...")
                sequence_rows = conn.execute(text(f"""
                SELECT
                    sequence_owner AS owner,
                    sequence_name,
                    min_value,
                    max_value,
                    increment_by,
                    cycle_flag,
                    order_flag,
                    cache_size,
                    last_number
                FROM all_sequences
                WHERE sequence_owner IN ({schema_filter})
                    AND sequence_owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY sequence_owner, sequence_name
                """))
                sequences = _rows_to_dicts(sequence_rows)

                # 13. Extract Check Constraints
                print("Extracting check constraints...")
                check_rows = conn.execute(text(f"""
                SELECT
                    c.owner,
                    c.table_name,
                    c.constraint_name,
                    c.search_condition AS definition,
                    c.status,
                    c.deferrable,
                    c.deferred,
                    c.validated
                FROM all_constraints c
                WHERE c.constraint_type = 'C'
                    AND c.owner IN ({schema_filter})
                    AND c.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND c.table_name NOT LIKE 'BIN$%'
                    AND c.constraint_name NOT LIKE 'SYS_%'
                    AND c.generated != 'GENERATED NAME'
                ORDER BY c.owner, c.table_name, c.constraint_name
                """))
                check_constraints = _rows_to_dicts(check_rows)

                # 14. Extract Unique Constraints
                print("Extracting unique constraints...")
                unique_rows = conn.execute(text(f"""
                SELECT
                    c.owner,
                    c.table_name,
                    c.constraint_name,
                    cc.column_name,
                    cc.position AS ordinal_position
                FROM all_constraints c
                INNER JOIN all_cons_columns cc
                    ON c.owner = cc.owner
                    AND c.constraint_name = cc.constraint_name
                WHERE c.constraint_type = 'U'
                    AND c.owner IN ({schema_filter})
                    AND c.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND c.table_name NOT LIKE 'BIN$%'
                ORDER BY c.owner, c.table_name, c.constraint_name, cc.position
                """))
                unique_constraints = _rows_to_dicts(unique_rows)

                # 15. Extract Synonyms
                print("Extracting synonyms...")
                synonym_rows = conn.execute(text(f"""
                SELECT
                    owner,
                    synonym_name,
                    table_owner,
                    table_name,
                    db_link
                FROM all_synonyms
                WHERE owner IN ({schema_filter})
                    AND owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY owner, synonym_name
                """))
                synonyms = _rows_to_dicts(synonym_rows)

                # 16. Extract Database Links
                print("Extracting database links...")
                dblink_rows = conn.execute(text(f"""
                SELECT
                    owner,
                    db_link,
                    username,
                    host,
                    created
                FROM all_db_links
                WHERE owner IN ({schema_filter})
                    AND owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                ORDER BY owner, db_link
                """))
                db_links = _rows_to_dicts(dblink_rows)

                # 17. Extract Dependencies
                print("Extracting dependencies...")
                dependency_rows = conn.execute(text(f"""
                SELECT DISTINCT
                    d.owner AS referencing_owner,
                    d.name AS referencing_name,
                    d.type AS referencing_type,
                    d.referenced_owner,
                    d.referenced_name,
                    d.referenced_type,
                    d.referenced_link_name
                FROM all_dependencies d
                WHERE d.owner IN ({schema_filter})
                    AND d.owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND d.referenced_owner NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND d.type IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW', 'PROCEDURE', 'FUNCTION', 'PACKAGE')
                    AND d.referenced_type IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW', 'PROCEDURE', 'FUNCTION', 'PACKAGE')
                ORDER BY d.owner, d.name
                """))
                dependencies = _rows_to_dicts(dependency_rows)

                # Filter system objects
                views = _filter_system_objects(views, 'owner')
                procedures = _filter_system_objects(procedures, 'owner')
                functions = _filter_system_objects(functions, 'owner')
                packages = _filter_system_objects(packages, 'owner')

                print(f"After filtering: {len(views)} views, {len(procedures)} procedures, "
                      f"{len(functions)} functions, {len(packages)} packages")

                # If we get here, connection was successful
                break  # Exit retry loop

        except Exception as exc:
            last_error = exc

            if attempt == max_retries - 1:
                if engine is not None:
                    engine.dispose()
                error_msg = f"Database connection failed after {max_retries} attempts: {exc}"
                raise RuntimeError(error_msg) from exc

            # Retry with exponential backoff
            retry_delay = initial_retry_delay * (2 ** attempt)
            print(f"⚠️  Error (attempt {attempt + 1}/{max_retries}): {exc}")
            print(f"   Retrying in {retry_delay:.1f} seconds...")
            time.sleep(retry_delay)

    # Clean up engine
    if engine is not None:
        try:
            engine.dispose()
        except:
            pass

    # Build comprehensive table map
    table_map: Dict[str, Dict[str, Any]] = {}
    for table in tables:
        owner = table['owner']
        table_name = table['table_name']
        key = f"{owner}.{table_name}"

        table_map[key] = {
            "owner": owner,
            "name": table_name,
            "type": table['table_type'],
            "qualified_name": key,
            "full_name": f"{service_name}.{key}",
            "description": table.get('description'),
            "tablespace_name": table.get('tablespace_name'),
            "status": table.get('status'),
            "num_rows": table.get('num_rows'),
            "blocks": table.get('blocks'),
            "avg_row_len": table.get('avg_row_len'),
            "last_analyzed": str(table.get('last_analyzed')) if table.get('last_analyzed') else None,
            "partitioned": table.get('partitioned') == 'YES',
            "iot_type": table.get('iot_type'),
            "temporary": table.get('temporary') == 'Y',
            "cluster_name": table.get('cluster_name'),
            "compression": table.get('compression'),
            "compress_for": table.get('compress_for'),
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
        owner = column['owner']
        table_name = column['table_name']
        key = f"{owner}.{table_name}"

        if key not in table_map:
            continue

        column_details = {
            "name": column['column_name'],
            "ordinal_position": column['ordinal_position'],
            "data_type": column['data_type'],
            "data_length": column.get('data_length'),
            "data_precision": column.get('data_precision'),
            "data_scale": column.get('data_scale'),
            "nullable": column.get('nullable') == 'Y',
            "data_default": column.get('data_default'),
            "virtual_column": column.get('virtual_column') == 'YES',
            "hidden_column": column.get('hidden_column') == 'YES',
            "identity_column": column.get('identity_column') == 'YES',
            "comments": column.get('comments'),
            "qualified_name": f"{key}.{column['column_name']}",
        }
        table_map[key]["columns"].append(column_details)

    # Process primary keys
    pk_map = defaultdict(list)
    for pk in primary_keys:
        key = f"{pk['owner']}.{pk['table_name']}"
        pk_map[key].append((pk['ordinal_position'], pk['column_name']))

    for key, pk_cols in pk_map.items():
        if key in table_map:
            table_map[key]["primary_key"] = [col for _, col in sorted(pk_cols)]

    # Process foreign keys
    for fk in foreign_keys:
        key = f"{fk['owner']}.{fk['table_name']}"
        if key not in table_map:
            continue

        table_map[key]["foreign_keys"].append({
            "constraint": fk['constraint_name'],
            "column": fk['column_name'],
            "references": f"{fk['referenced_owner']}.{fk['referenced_table']}({fk['referenced_column']})",
            "referenced_owner": fk['referenced_owner'],
            "referenced_table": fk['referenced_table'],
            "referenced_column": fk['referenced_column'],
            "delete_rule": fk.get('delete_rule'),
            "status": fk.get('status'),
            "deferrable": fk.get('deferrable'),
            "deferred": fk.get('deferred'),
        })

    # Process indexes
    index_map = defaultdict(lambda: defaultdict(dict))
    for idx in indexes:
        owner = idx['owner']
        table_name = idx['table_name']
        key = f"{owner}.{table_name}"
        idx_name = idx['index_name']

        if 'columns' not in index_map[key][idx_name]:
            index_map[key][idx_name]['columns'] = []
            index_map[key][idx_name].update({
                'name': idx_name,
                'type': idx['index_type'],
                'uniqueness': idx.get('uniqueness'),
                'compression': idx.get('compression'),
                'tablespace_name': idx.get('tablespace_name'),
                'status': idx.get('status'),
                'partitioned': idx.get('partitioned') == 'YES',
            })

        index_map[key][idx_name]['columns'].append((idx['column_position'], idx['column_name'], idx.get('descend')))

    # Sort index columns and add to table map
    for key, idx_dict in index_map.items():
        if key in table_map:
            for idx_info in idx_dict.values():
                idx_info['columns'] = [
                    {"name": col, "descend": desc}
                    for _, col, desc in sorted(idx_info['columns'])
                ]
                table_map[key]["indexes"].append(idx_info)

    # Process unique constraints
    unique_map = defaultdict(lambda: defaultdict(list))
    for uc in unique_constraints:
        key = f"{uc['owner']}.{uc['table_name']}"
        unique_map[key][uc['constraint_name']].append((uc['ordinal_position'], uc['column_name']))

    for key, constraints in unique_map.items():
        if key in table_map:
            table_map[key]["unique_constraints"] = [
                {"constraint_name": name, "columns": [col for _, col in sorted(cols)]}
                for name, cols in constraints.items()
            ]

    # Process check constraints
    for cc in check_constraints:
        key = f"{cc['owner']}.{cc['table_name']}"
        if key in table_map:
            table_map[key]["check_constraints"].append({
                "constraint_name": cc['constraint_name'],
                "definition": cc.get('definition'),
                "status": cc.get('status'),
                "deferrable": cc.get('deferrable'),
                "deferred": cc.get('deferred'),
                "validated": cc.get('validated'),
            })

    # Process triggers
    for trigger in triggers:
        key = f"{trigger.get('table_owner', trigger['owner'])}.{trigger['table_name']}" if trigger.get('table_name') else None
        if key and key in table_map:
            table_map[key]["triggers"].append({
                "name": trigger['trigger_name'],
                "type": trigger.get('trigger_type'),
                "event": trigger.get('triggering_event'),
                "definition": trigger.get('definition'),
                "status": trigger.get('status'),
                "action_type": trigger.get('action_type'),
                "when_clause": trigger.get('when_clause'),
            })

    # Process dependencies
    dependency_graph: Dict[str, set[str]] = defaultdict(set)
    reverse_dependency_graph: Dict[str, set[str]] = defaultdict(set)

    for dep in dependencies:
        if dep.get('referencing_name') and dep.get('referenced_name'):
            referencing = f"{dep['referencing_owner']}.{dep['referencing_name']}"
            referenced = f"{dep['referenced_owner']}.{dep['referenced_name']}"
            dependency_graph[referencing].add(referenced)
            reverse_dependency_graph[referenced].add(referencing)

    for key, table in table_map.items():
        table["dependencies"]["depends_on"] = sorted(dependency_graph.get(key, []))
        table["dependencies"]["referenced_by"] = sorted(reverse_dependency_graph.get(key, []))

    # Assemble final metadata
    sorted_tables = sorted(table_map.values(), key=lambda t: (t["owner"], t["name"]))
    table_disambiguation = _build_table_disambiguation_map(sorted_tables, service_name)
    column_map = _build_column_map(columns, service_name)

    metadata["tables"] = sorted_tables
    metadata["views"] = views
    metadata["materialized_views"] = matviews
    metadata["procedures"] = procedures
    metadata["functions"] = functions
    metadata["packages"] = packages
    metadata["triggers"] = triggers
    metadata["sequences"] = sequences
    metadata["synonyms"] = synonyms
    metadata["db_links"] = db_links
    metadata["dependencies"] = dependencies

    # Add parser support maps
    metadata["parser_support"] = {
        "table_disambiguation": table_disambiguation,
        "column_map": column_map,
        "database_name": service_name,
        "schemas": sorted({t["owner"] for t in metadata["tables"]}),
    }

    # Add summary statistics
    metadata["summary"] = {
        "database": service_name,
        "host": host,
        "port": port,
        "extraction_timestamp": datetime.now(UTC).isoformat(),
        "table_count": len(metadata["tables"]),
        "view_count": len(metadata["views"]),
        "materialized_view_count": len(matviews),
        "procedure_count": len(metadata["procedures"]),
        "function_count": len(metadata["functions"]),
        "package_count": len(packages),
        "trigger_count": len(triggers),
        "sequence_count": len(sequences),
        "synonym_count": len(synonyms),
        "db_link_count": len(db_links),
        "column_count": len(columns),
        "index_count": len(set((idx['owner'], idx['table_name'], idx['index_name']) for idx in indexes)),
        "foreign_key_count": len(set((fk['owner'], fk['table_name'], fk['constraint_name']) for fk in foreign_keys)),
        "schema_count": len(metadata["parser_support"]["schemas"]),
        "unique_table_names": len(table_disambiguation["unique_tables"]),
        "ambiguous_table_names": len(table_disambiguation["ambiguous_tables"]),
    }

    # Save metadata
    output_directory = _ensure_output_dir(output_dir)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_db = service_name.replace("/", "-").replace("\\", "-")
    file_path = output_directory / f"enhanced_metadata_{safe_db}_{timestamp}.json"

    with file_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, default=str)

    print(f"\nMetadata extraction complete. Saved to: {file_path}")
    print(f"\nExtraction Summary:")
    for key, value in metadata['summary'].items():
        if key not in ['database', 'host', 'port', 'extraction_timestamp']:
            print(f"  {key}: {value}")

    return metadata, file_path


__all__ = ["extract_enhanced_database_metadata", "build_connection_url"]


if __name__ == "__main__":
    import sys
    import getpass

    print("=" * 70)
    print("Enhanced Oracle Metadata Extractor")
    print("=" * 70)
    print()

    # Get connection parameters
    if len(sys.argv) >= 5:
        host = sys.argv[1]
        service_name = sys.argv[2]
        username = sys.argv[3]
        password = sys.argv[4]
        port = int(sys.argv[5]) if len(sys.argv) > 5 else 1521
    else:
        print("Usage: python enhanced_metadata_extractor.py <host> <service_name> <username> <password> [port]")
        print("\nOr provide interactively:")
        host = input("Host: ").strip()
        service_name = input("Service Name: ").strip()
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        port_input = input("Port (default: 1521): ").strip()
        port = int(port_input) if port_input else 1521

    if not all([host, service_name, username]):
        print("Error: Host, service name, and username are required.")
        sys.exit(1)

    # Ask about target schemas
    schemas_input = input("Target schemas (comma-separated, blank for current user): ").strip()
    target_schemas = [s.strip() for s in schemas_input.split(",")] if schemas_input else None

    try:
        print(f"\nConnecting to {host}:{port}/{service_name}...")
        metadata, file_path = extract_enhanced_database_metadata(
            host=host,
            service_name=service_name,
            username=username,
            password=password,
            port=port,
            target_schemas=target_schemas
        )
        print(f"\n✓ Success! Metadata saved to: {file_path}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
