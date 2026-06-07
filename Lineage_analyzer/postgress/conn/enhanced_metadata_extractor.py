"""Enhanced PostgreSQL metadata extractor with comprehensive coverage.

This module captures:
- Tables, Views, Stored Procedures, Functions
- Materialized Views
- Extended properties and descriptions (via COMMENT statements)
- Triggers and their definitions
- Complete schema hierarchy
- Sequences and their usage
- Partitioned tables
- Foreign data wrappers
- Query statistics (via pg_stat_statements if available)
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
import psycopg2


METADATA_OUTPUT_DIR = Path(__file__).parent / "metadata_cache"

# PostgreSQL system schemas to exclude
SYSTEM_SCHEMAS = (
    'pg_catalog', 'information_schema', 'pg_toast',
    'pg_temp_1', 'pg_toast_temp_1', 'pg_statistic',
    'pg_type', 'pg_authid', 'pg_auth_members'
)

SYSTEM_SCHEMA_FILTER_LIST = ", ".join(f"'{schema}'" for schema in SYSTEM_SCHEMAS)


def _is_system_object(schema: str, name: str) -> bool:
    """Check if an object is a system object based on schema and name."""
    if schema in SYSTEM_SCHEMAS:
        return True

    # PostgreSQL system prefixes
    name_lower = name.lower()
    if name_lower.startswith('pg_'):
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
        schema = obj.get(schema_key, 'public')

        if name_key is None:
            # Auto-detect name key
            if 'view_name' in obj:
                name = obj['view_name']
            elif 'function_name' in obj:
                name = obj['function_name']
            elif 'procedure_name' in obj:
                name = obj['procedure_name']
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


def build_connection_url(host: str, database: str, username: str, password: str, port: int = 5432) -> str:
    """Construct a SQLAlchemy-compatible PostgreSQL connection URL."""
    encoded_password = urllib.parse.quote_plus(password) if password else ''
    encoded_username = urllib.parse.quote_plus(username)

    if password:
        return f"postgresql://{encoded_username}:{encoded_password}@{host}:{port}/{database}"
    else:
        return f"postgresql://{encoded_username}@{host}:{port}/{database}"


def _rows_to_dicts(rows: Iterable[Any]) -> List[Dict[str, Any]]:
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
        schema = table.get('schema', 'public')
        name = table['name']
        table_type = table.get('type', 'TABLE')

        qualified_name = f"{schema}.{name}"
        full_name = f"{database}.{schema}.{name}"

        table_name_counts[name].append(qualified_name)
        schema_tables[schema].append(name)

        # Store all possible name variations
        for key in [name, qualified_name, full_name]:
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
        schema = column.get('table_schema', 'public')
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
            "is_nullable": column.get('is_nullable') == 'YES',
            "column_default": column.get('column_default'),
            "is_identity": column.get('is_identity') == 'YES',
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
            "size": column.get('character_maximum_length'),
            "precision": column.get('numeric_precision'),
            "scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable') == 'YES',
        }

    # Identify unique columns
    for col_name, tables in column_name_counts.items():
        if len(tables) == 1:
            column_map["unique_columns"][col_name] = list(tables)[0]

    column_map["by_column_name"] = dict(column_map["by_column_name"])

    return column_map


def extract_enhanced_database_metadata(
    host: str,
    database: str,
    username: str,
    password: str,
    port: int = 5432,
    output_dir: Path | None = None,
    max_retries: int = 3,
    initial_retry_delay: float = 2.0,
) -> Tuple[Dict[str, Any], Path]:
    """Extract comprehensive metadata from PostgreSQL database.

    Args:
        host: PostgreSQL server hostname
        database: Database name
        username: Login username
        password: Login password
        port: PostgreSQL port (default: 5432)
        output_dir: Output directory for metadata files
        max_retries: Maximum number of retry attempts
        initial_retry_delay: Initial delay in seconds before first retry

    Returns:
        Tuple of (metadata dictionary, output file path)

    Raises:
        RuntimeError: If connection fails after all retries
    """

    metadata: Dict[str, Any] = {"database": database, "host": host, "port": port}
    engine: Optional[Engine] = None

    conn_str = build_connection_url(host, database, username, password, port)

    # Retry logic
    last_error = None
    for attempt in range(max_retries):
        try:
            if engine is not None:
                engine.dispose()

            engine = create_engine(
                conn_str,
                pool_pre_ping=True,
                connect_args={"connect_timeout": 30},
                pool_timeout=30,
            )

            with engine.connect() as conn:
                # 1. Extract Tables with descriptions
                table_rows = conn.execute(text(f"""
                SELECT
                    t.schemaname AS table_schema,
                    t.tablename AS table_name,
                    'TABLE' AS table_type,
                    obj_description(c.oid, 'pg_class') AS description,
                    c.reltuples::BIGINT AS row_count
                FROM pg_catalog.pg_tables t
                INNER JOIN pg_catalog.pg_class c ON c.relname = t.tablename
                INNER JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.schemaname
                WHERE t.schemaname NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND t.schemaname NOT LIKE 'pg_%'
                ORDER BY t.schemaname, t.tablename
                """))
                tables = _rows_to_dicts(table_rows)

                # 2. Extract Columns with descriptions
                column_rows = conn.execute(text(f"""
                SELECT
                    c.table_schema,
                    c.table_name,
                    c.column_name,
                    c.ordinal_position,
                    c.data_type,
                    c.character_maximum_length,
                    c.numeric_precision,
                    c.numeric_scale,
                    c.is_nullable,
                    c.column_default,
                    c.is_identity,
                    c.is_generated,
                    c.generation_expression,
                    col_description(
                        (c.table_schema || '.' || c.table_name)::regclass::oid,
                        c.ordinal_position
                    ) AS description
                FROM information_schema.columns c
                WHERE c.table_schema NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND c.table_schema NOT LIKE 'pg_%'
                ORDER BY c.table_schema, c.table_name, c.ordinal_position
                """))
                columns = _rows_to_dicts(column_rows)

                # 3. Extract Views with definitions
                view_rows = conn.execute(text(f"""
                SELECT
                    schemaname AS schema_name,
                    viewname AS view_name,
                    definition,
                    obj_description((schemaname || '.' || viewname)::regclass::oid, 'pg_class') AS description
                FROM pg_catalog.pg_views
                WHERE schemaname NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND schemaname NOT LIKE 'pg_%'
                ORDER BY schemaname, viewname
                """))
                views = _rows_to_dicts(view_rows)

                # 4. Extract Materialized Views
                matview_rows = conn.execute(text(f"""
                SELECT
                    schemaname AS schema_name,
                    matviewname AS matview_name,
                    definition,
                    obj_description((schemaname || '.' || matviewname)::regclass::oid, 'pg_class') AS description
                FROM pg_catalog.pg_matviews
                WHERE schemaname NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND schemaname NOT LIKE 'pg_%'
                ORDER BY schemaname, matviewname
                """))
                matviews = _rows_to_dicts(matview_rows)

                # 5. Extract Functions and Procedures
                function_rows = conn.execute(text(f"""
                SELECT
                    n.nspname AS schema_name,
                    p.proname AS function_name,
                    pg_get_functiondef(p.oid) AS definition,
                    CASE
                        WHEN p.prokind = 'f' THEN 'FUNCTION'
                        WHEN p.prokind = 'p' THEN 'PROCEDURE'
                        WHEN p.prokind = 'a' THEN 'AGGREGATE'
                        WHEN p.prokind = 'w' THEN 'WINDOW'
                        ELSE 'FUNCTION'
                    END AS function_type,
                    pg_catalog.format_type(p.prorettype, NULL) AS return_type,
                    pg_get_function_arguments(p.oid) AS arguments,
                    pg_get_function_identity_arguments(p.oid) AS identity_arguments,
                    l.lanname AS language,
                    obj_description(p.oid, 'pg_proc') AS description
                FROM pg_catalog.pg_proc p
                INNER JOIN pg_catalog.pg_namespace n ON p.pronamespace = n.oid
                LEFT JOIN pg_catalog.pg_language l ON p.prolang = l.oid
                WHERE n.nspname NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND n.nspname NOT LIKE 'pg_%'
                    AND p.proname NOT LIKE 'pg_%'
                ORDER BY n.nspname, p.proname
                """))
                functions = _rows_to_dicts(function_rows)

                # Separate procedures from functions
                procedures = [f for f in functions if f.get('function_type') == 'PROCEDURE']
                functions = [f for f in functions if f.get('function_type') != 'PROCEDURE']

                # 6. Extract Triggers
                trigger_rows = conn.execute(text(f"""
                SELECT
                    n.nspname AS schema_name,
                    c.relname AS table_name,
                    t.tgname AS trigger_name,
                    tg.event_manipulation AS trigger_event,
                    tg.action_timing,
                    tg.action_orientation,
                    pg_get_triggerdef(t.oid) AS definition,
                    t.tgenabled::TEXT AS is_enabled
                FROM pg_catalog.pg_trigger t
                INNER JOIN pg_catalog.pg_class c ON t.tgrelid = c.oid
                INNER JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
                LEFT JOIN information_schema.triggers tg
                    ON tg.trigger_name = t.tgname
                    AND tg.event_object_table = c.relname
                    AND tg.trigger_schema = n.nspname
                WHERE n.nspname NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND n.nspname NOT LIKE 'pg_%'
                    AND NOT t.tgisinternal
                ORDER BY n.nspname, c.relname, t.tgname
                """))
                triggers = _rows_to_dicts(trigger_rows)

                # 7. Extract Primary Keys
                pk_rows = conn.execute(text(f"""
                SELECT
                    kcu.table_schema,
                    kcu.table_name,
                    tc.constraint_name AS pk_name,
                    kcu.column_name,
                    kcu.ordinal_position
                FROM information_schema.table_constraints tc
                INNER JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_schema NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND tc.table_schema NOT LIKE 'pg_%'
                ORDER BY kcu.table_schema, kcu.table_name, kcu.ordinal_position
                """))
                primary_keys = _rows_to_dicts(pk_rows)

                # 8. Extract Foreign Keys
                fk_rows = conn.execute(text(f"""
                SELECT
                    tc.table_schema AS schema_name,
                    tc.table_name,
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_schema AS referenced_schema,
                    ccu.table_name AS referenced_table,
                    ccu.column_name AS referenced_column,
                    rc.update_rule AS update_action,
                    rc.delete_rule AS delete_action
                FROM information_schema.table_constraints tc
                INNER JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                INNER JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                LEFT JOIN information_schema.referential_constraints rc
                    ON tc.constraint_name = rc.constraint_name
                    AND tc.table_schema = rc.constraint_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND tc.table_schema NOT LIKE 'pg_%'
                ORDER BY tc.table_schema, tc.table_name, tc.constraint_name
                """))
                foreign_keys = _rows_to_dicts(fk_rows)

                # 9. Extract Indexes with usage stats
                index_rows = conn.execute(text(f"""
                SELECT
                    n.nspname AS schema_name,
                    t.relname AS table_name,
                    i.relname AS index_name,
                    ix.indisunique AS is_unique,
                    ix.indisprimary AS is_primary_key,
                    am.amname AS index_type,
                    pg_get_indexdef(ix.indexrelid) AS index_definition,
                    s.idx_scan AS index_scans,
                    s.idx_tup_read AS tuples_read,
                    s.idx_tup_fetch AS tuples_fetched
                FROM pg_catalog.pg_index ix
                INNER JOIN pg_catalog.pg_class t ON ix.indrelid = t.oid
                INNER JOIN pg_catalog.pg_class i ON ix.indexrelid = i.oid
                INNER JOIN pg_catalog.pg_namespace n ON t.relnamespace = n.oid
                LEFT JOIN pg_catalog.pg_am am ON i.relam = am.oid
                LEFT JOIN pg_catalog.pg_stat_user_indexes s ON i.oid = s.indexrelid
                WHERE n.nspname NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND n.nspname NOT LIKE 'pg_%'
                ORDER BY n.nspname, t.relname, i.relname
                """))
                indexes = _rows_to_dicts(index_rows)

                # 10. Extract Sequences
                sequence_rows = conn.execute(text(f"""
                SELECT
                    schemaname AS schema_name,
                    sequencename AS sequence_name,
                    start_value,
                    min_value,
                    max_value,
                    increment_by,
                    cycle AS is_cycling,
                    last_value AS current_value
                FROM pg_catalog.pg_sequences
                WHERE schemaname NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND schemaname NOT LIKE 'pg_%'
                ORDER BY schemaname, sequencename
                """))
                sequences = _rows_to_dicts(sequence_rows)

                # 11. Extract Check Constraints
                check_rows = conn.execute(text(f"""
                SELECT
                    tc.table_schema AS schema_name,
                    tc.table_name,
                    tc.constraint_name,
                    cc.check_clause AS definition
                FROM information_schema.table_constraints tc
                INNER JOIN information_schema.check_constraints cc
                    ON tc.constraint_name = cc.constraint_name
                    AND tc.table_schema = cc.constraint_schema
                WHERE tc.constraint_type = 'CHECK'
                    AND tc.table_schema NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND tc.table_schema NOT LIKE 'pg_%'
                ORDER BY tc.table_schema, tc.table_name, tc.constraint_name
                """))
                check_constraints = _rows_to_dicts(check_rows)

                # 12. Extract Unique Constraints
                unique_rows = conn.execute(text(f"""
                SELECT
                    kcu.table_schema AS schema_name,
                    kcu.table_name,
                    tc.constraint_name,
                    kcu.column_name,
                    kcu.ordinal_position
                FROM information_schema.table_constraints tc
                INNER JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'UNIQUE'
                    AND tc.table_schema NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND tc.table_schema NOT LIKE 'pg_%'
                ORDER BY kcu.table_schema, kcu.table_name, tc.constraint_name, kcu.ordinal_position
                """))
                unique_constraints = _rows_to_dicts(unique_rows)

                # 13. Extract Query Statistics (if pg_stat_statements is available)
                query_history = []
                try:
                    # Check if pg_stat_statements extension exists
                    extension_check = conn.execute(text("""
                    SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_stat_statements'
                    """)).fetchone()

                    if extension_check and extension_check[0] > 0:
                        print("pg_stat_statements extension found - extracting query statistics...")

                        query_rows = conn.execute(text("""
                        SELECT
                            queryid AS query_id,
                            query AS query_text,
                            calls AS execution_count,
                            total_exec_time / calls AS avg_duration_ms,
                            mean_exec_time AS avg_exec_time_ms,
                            min_exec_time AS min_duration_ms,
                            max_exec_time AS max_duration_ms,
                            rows AS total_rows,
                            shared_blks_hit,
                            shared_blks_read,
                            shared_blks_written
                        FROM pg_stat_statements
                        WHERE query NOT LIKE '%pg_catalog%'
                            AND query NOT LIKE '%information_schema%'
                            AND query NOT LIKE '%pg_stat_statements%'
                            AND LENGTH(query) >= 50
                        ORDER BY calls DESC
                        LIMIT 1000
                        """))
                        query_history = _rows_to_dicts(query_rows)
                        print(f"Extracted {len(query_history)} query statistics")
                except Exception as e:
                    print(f"Could not access pg_stat_statements: {e}")
                    query_history = []

                # 14. Extract Dependencies
                dependency_rows = conn.execute(text(f"""
                SELECT DISTINCT
                    ref_nsp.nspname AS referencing_schema,
                    ref_class.relname AS referencing_name,
                    ref_class.relkind AS referencing_type,
                    dep_nsp.nspname AS referenced_schema,
                    dep_class.relname AS referenced_name,
                    dep_class.relkind AS referenced_type
                FROM pg_catalog.pg_depend d
                INNER JOIN pg_catalog.pg_class ref_class ON d.objid = ref_class.oid
                INNER JOIN pg_catalog.pg_namespace ref_nsp ON ref_class.relnamespace = ref_nsp.oid
                INNER JOIN pg_catalog.pg_class dep_class ON d.refobjid = dep_class.oid
                INNER JOIN pg_catalog.pg_namespace dep_nsp ON dep_class.relnamespace = dep_nsp.oid
                WHERE d.deptype = 'n'
                    AND ref_nsp.nspname NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND dep_nsp.nspname NOT IN ({SYSTEM_SCHEMA_FILTER_LIST})
                    AND ref_nsp.nspname NOT LIKE 'pg_%'
                    AND dep_nsp.nspname NOT LIKE 'pg_%'
                    AND ref_class.relkind IN ('r', 'v', 'm')
                    AND dep_class.relkind IN ('r', 'v', 'm')
                ORDER BY ref_nsp.nspname, ref_class.relname
                """))
                dependencies = _rows_to_dicts(dependency_rows)

                # Filter system objects
                views = _filter_system_objects(views)
                functions = _filter_system_objects(functions)
                procedures = _filter_system_objects(procedures)

                print(f"After filtering: {len(views)} views, {len(procedures)} procedures, {len(functions)} functions")

                # If we get here, connection was successful
                break  # Exit retry loop

        except (SQLAlchemyError, psycopg2.Error) as exc:
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
        key = f"{table['table_schema']}.{table['table_name']}"
        table_map[key] = {
            "schema": table['table_schema'],
            "name": table['table_name'],
            "type": table['table_type'],
            "qualified_name": key,
            "full_name": f"{database}.{key}",
            "description": table.get('description'),
            "row_count": table.get('row_count', 0),
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
            "character_maximum_length": column.get('character_maximum_length'),
            "numeric_precision": column.get('numeric_precision'),
            "numeric_scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable') == 'YES',
            "column_default": column.get('column_default'),
            "is_identity": column.get('is_identity') == 'YES',
            "is_generated": column.get('is_generated'),
            "generation_expression": column.get('generation_expression'),
            "description": column.get('description'),
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

    # Process indexes
    for idx in indexes:
        key = f"{idx['schema_name']}.{idx['table_name']}"
        if key not in table_map:
            continue
        table_map[key]["indexes"].append({
            "name": idx['index_name'],
            "type": idx.get('index_type'),
            "is_unique": idx.get('is_unique'),
            "is_primary_key": idx.get('is_primary_key'),
            "definition": idx.get('index_definition'),
            "usage_stats": {
                "scans": idx.get('index_scans', 0),
                "tuples_read": idx.get('tuples_read', 0),
                "tuples_fetched": idx.get('tuples_fetched', 0),
            }
        })

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
                "definition": cc['definition']
            })

    # Process triggers
    for trigger in triggers:
        key = f"{trigger['schema_name']}.{trigger['table_name']}"
        if key in table_map:
            table_map[key]["triggers"].append({
                "name": trigger['trigger_name'],
                "event": trigger.get('trigger_event'),
                "timing": trigger.get('action_timing'),
                "orientation": trigger.get('action_orientation'),
                "definition": trigger.get('definition'),
                "is_enabled": trigger.get('is_enabled') != 'D',
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
    metadata["materialized_views"] = matviews
    metadata["procedures"] = procedures
    metadata["functions"] = functions
    metadata["triggers"] = triggers
    metadata["sequences"] = sequences
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
        "host": host,
        "port": port,
        "extraction_timestamp": datetime.now(UTC).isoformat(),
        "table_count": len(metadata["tables"]),
        "view_count": len(metadata["views"]),
        "materialized_view_count": len(matviews),
        "procedure_count": len(metadata["procedures"]),
        "function_count": len(metadata["functions"]),
        "trigger_count": len(triggers),
        "sequence_count": len(sequences),
        "column_count": len(columns),
        "index_count": len(indexes),
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
    print("Enhanced PostgreSQL Metadata Extractor")
    print("=" * 70)
    print()

    # Get connection parameters
    if len(sys.argv) >= 5:
        host = sys.argv[1]
        database = sys.argv[2]
        username = sys.argv[3]
        password = sys.argv[4]
        port = int(sys.argv[5]) if len(sys.argv) > 5 else 5432
    else:
        print("Usage: python enhanced_metadata_extractor.py <host> <database> <username> <password> [port]")
        print("\nOr provide interactively:")
        host = input("Host: ").strip()
        database = input("Database: ").strip()
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        port_input = input("Port (default: 5432): ").strip()
        port = int(port_input) if port_input else 5432

    if not all([host, database, username]):
        print("Error: Host, database, and username are required.")
        sys.exit(1)

    try:
        print(f"\nConnecting to {host}:{port}/{database}...")
        metadata, file_path = extract_enhanced_database_metadata(
            host=host,
            database=database,
            username=username,
            password=password,
            port=port
        )
        print(f"\n✓ Success! Metadata saved to: {file_path}")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
