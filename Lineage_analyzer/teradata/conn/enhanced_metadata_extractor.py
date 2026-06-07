"""Enhanced Teradata metadata extractor with comprehensive coverage.

This improved version captures:
- Tables, Views, Stored Procedures, Functions, Macros
- Complete schema hierarchy from Teradata system tables
- Extended properties and descriptions
- Primary keys, Foreign keys, and Indexes
- Complete column definitions with Teradata-specific data types
- Performance statistics and row counts
- Object dependencies

Teradata-specific features:
- Multi-statement procedure/function/macro definitions
- PERIOD data types (DATE, TIME, TIMESTAMP)
- JSON, XML, ARRAY, VARRAY types
- Join indexes and Hash indexes
- External stored procedures
- Table compression and partitioning info
- Fallback and journal settings
"""

from __future__ import annotations

import json
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Set, Optional
from collections import defaultdict, deque

try:
    import teradatasql
except ImportError:
    teradatasql = None


METADATA_OUTPUT_DIR = Path(__file__).parent / "metadata_cache"

# System databases to exclude
SYSTEM_DATABASES = (
    'DBC',
    'SYSDBA',
    'SYSBAR',
    'SYSLIB',
    'SYSUDTLIB',
    'SYSSPATIAL',
    'SYSUIF',
    'TDWM',
    'TDQCD',
    'TD_SYSGPL',
    'TD_SYSXML',
    'TDStats',
    'SystemFe',
    'SQLJ',
    'EXTUSER',
    'LockLogShredder',
    'Sys_Calendar',
    'SysAdmin',
    'TDPUSER',
    'TDMaps',
    'dbcmngr',
    'Crashdumps',
    'External_AP',
    'TD_SERVER_DB',
    'TD_SYSFNLIB',
)

# Teradata object types
TERADATA_OBJECT_TYPES = {
    'T': 'TABLE',
    'V': 'VIEW',
    'O': 'PROCEDURE',
    'P': 'STORED PROCEDURE',
    'E': 'EXTERNAL STORED PROCEDURE',
    'F': 'FUNCTION',
    'M': 'MACRO',
    'I': 'JOIN INDEX',
    'N': 'HASH INDEX',
    'G': 'TRIGGER',
    'R': 'PROCEDURE',  # Alias for 'P'
}


def _is_system_database(database: str) -> bool:
    """Check if a database is a system database."""
    return database.upper() in SYSTEM_DATABASES


def _filter_system_objects(
    objects: List[Dict[str, Any]],
    database_key: str = 'database_name',
) -> List[Dict[str, Any]]:
    """Filter out system objects from extracted list."""
    filtered: List[Dict[str, Any]] = []

    for obj in objects:
        database = obj.get(database_key, '')
        if _is_system_database(database):
            continue
        filtered.append(obj)

    return filtered


def _ensure_output_dir(output_dir: Path | None) -> Path:
    """Ensure output directory exists."""
    directory = output_dir or METADATA_OUTPUT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


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
    host: str,
    database: str,
    username: str,
    password: str,
    logmech: str = "TD2",
    encryptdata: bool = False,
    charset: str = "UTF8",
    tmode: str = "ANSI",
) -> Dict[str, Any]:
    """Construct Teradata connection parameters.

    Args:
        host: Teradata server hostname or IP address
        database: Default database name
        username: Login username
        password: Login password
        logmech: Authentication mechanism (TD2, LDAP, KRB5, etc.)
        encryptdata: Enable data encryption
        charset: Character set (UTF8, UTF16, etc.)
        tmode: Transaction mode (ANSI or TERA)

    Returns:
        Connection parameters dictionary
    """
    params = {
        "host": host,
        "user": username,
        "password": password,
        "database": database,
        "logmech": logmech,
        "encryptdata": "true" if encryptdata else "false",
        "charset": charset,
        "tmode": tmode,
    }

    return params


def _execute_query(cursor, query: str) -> List[Dict[str, Any]]:
    """Execute a query and return results as list of dictionaries."""
    try:
        cursor.execute(query)
        columns = [desc[0].lower() for desc in cursor.description] if cursor.description else []
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        return results
    except Exception as e:
        print(f"Query execution error: {e}")
        print(f"Query: {query[:200]}...")
        return []


def _extract_tables_and_views(cursor, database: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extract tables and views from DBC.TablesV."""
    query = f"""
    SELECT
        DatabaseName as database_name,
        TableName as table_name,
        TableKind as table_kind,
        CreatorName as creator,
        CreateTimeStamp as create_date,
        LastAlterName as last_alter_user,
        LastAlterTimeStamp as modify_date,
        CommentString as description,
        CheckOpt as check_option,
        RequestText as request_text,
        ParentCount as parent_count,
        ChildCount as child_count,
        NamedTblCheckCount as check_constraint_count,
        UnnamedTblCheckExist as has_unnamed_check,
        PrimaryKeyIndexId as primary_key_index_id,
        RepStatus as replication_status,
        CommitOpt as commit_option,
        TransLog as transaction_log,
        AccessCount as access_count,
        ProtectionType as protection_type,
        JournalFlag as journal_flag,
        TemporaryFlag as temporary_flag,
        QueueFlag as queue_flag
    FROM DBC.TablesV
    WHERE DatabaseName = '{database}'
        AND TableKind IN ('T', 'V', 'O', 'I', 'N')
    ORDER BY DatabaseName, TableName
    """

    results = _execute_query(cursor, query)

    tables = []
    views = []

    for row in results:
        table_kind = row.get('table_kind', 'T')

        if table_kind == 'V':  # View
            # Get view definition from RequestText or DBC.TableTextV
            view_def = row.get('request_text', '')
            if not view_def:
                # Try to get from TableTextV
                text_query = f"""
                SELECT RequestText
                FROM DBC.TableTextV
                WHERE DatabaseName = '{row['database_name']}'
                    AND TableName = '{row['table_name']}'
                    AND TextType = 'V'
                ORDER BY LineNo
                """
                text_results = _execute_query(cursor, text_query)
                view_def = '\n'.join([r.get('requesttext', '') for r in text_results])

            views.append({
                'database_name': row['database_name'],
                'view_name': row['table_name'],
                'definition': view_def,
                'creator': row.get('creator'),
                'create_date': row.get('create_date'),
                'modify_date': row.get('modify_date'),
                'description': row.get('description'),
                'check_option': row.get('check_option'),
            })
        elif table_kind in ('T', 'O', 'I', 'N'):  # Table, No Primary Index, Join Index, Hash Index
            tables.append({
                'database_name': row['database_name'],
                'table_name': row['table_name'],
                'table_type': TERADATA_OBJECT_TYPES.get(table_kind, 'TABLE'),
                'table_kind': table_kind,
                'creator': row.get('creator'),
                'create_date': row.get('create_date'),
                'modify_date': row.get('modify_date'),
                'description': row.get('description'),
                'primary_key_index_id': row.get('primary_key_index_id'),
                'replication_status': row.get('replication_status'),
                'transaction_log': row.get('transaction_log'),
                'access_count': row.get('access_count'),
                'protection_type': row.get('protection_type'),
                'journal_flag': row.get('journal_flag'),
                'temporary_flag': row.get('temporary_flag'),
                'queue_flag': row.get('queue_flag'),
                'parent_count': row.get('parent_count', 0),
                'child_count': row.get('child_count', 0),
                'check_constraint_count': row.get('check_constraint_count', 0),
            })

    return tables, views


def _extract_columns(cursor, database: str) -> List[Dict[str, Any]]:
    """Extract column definitions from DBC.ColumnsV."""
    query = f"""
    SELECT
        DatabaseName as database_name,
        TableName as table_name,
        ColumnName as column_name,
        ColumnId as ordinal_position,
        ColumnType as data_type,
        ColumnLength as column_length,
        DecimalTotalDigits as numeric_precision,
        DecimalFractionalDigits as numeric_scale,
        Nullable as is_nullable,
        DefaultValue as column_default,
        CommentString as comment,
        ColumnFormat as column_format,
        UpperCaseFlag as upper_case_flag,
        CompressValueList as compress_value_list,
        CharType as char_type,
        IdColType as identity_type,
        Compressible as compressible
    FROM DBC.ColumnsV
    WHERE DatabaseName = '{database}'
    ORDER BY DatabaseName, TableName, ColumnId
    """

    return _execute_query(cursor, query)


def _extract_indexes(cursor, database: str) -> List[Dict[str, Any]]:
    """Extract indexes and primary keys from DBC.IndicesV."""
    query = f"""
    SELECT
        DatabaseName as database_name,
        TableName as table_name,
        IndexName as index_name,
        IndexNumber as index_number,
        IndexType as index_type,
        ColumnName as column_name,
        ColumnPosition as column_position,
        UniqueFlag as is_unique
    FROM DBC.IndicesV
    WHERE DatabaseName = '{database}'
    ORDER BY DatabaseName, TableName, IndexNumber, ColumnPosition
    """

    return _execute_query(cursor, query)


def _extract_foreign_keys(cursor, database: str) -> List[Dict[str, Any]]:
    """Extract foreign key relationships from DBC.All_RI_ChildrenV and All_RI_ParentsV."""
    query = f"""
    SELECT
        c.ChildDB as database_name,
        c.ChildTable as table_name,
        c.IndexName as constraint_name,
        c.ChildKeyColumn as column_name,
        c.ParentDB as referenced_database,
        c.ParentTable as referenced_table,
        p.ParentKeyColumn as referenced_column,
        c.InconsistencyFlag as inconsistency_flag
    FROM DBC.All_RI_ChildrenV c
    LEFT JOIN DBC.All_RI_ParentsV p
        ON c.ChildDB = p.ChildDB
        AND c.ChildTable = p.ChildTable
        AND c.IndexID = p.IndexID
    WHERE c.ChildDB = '{database}'
    ORDER BY c.ChildDB, c.ChildTable, c.IndexName
    """

    return _execute_query(cursor, query)


def _extract_procedures_functions_macros(cursor, database: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Extract procedures, functions, and macros from DBC system tables."""
    # Get all procedure/function/macro definitions
    obj_query = f"""
    SELECT DISTINCT
        DatabaseName as database_name,
        TableName as object_name,
        TableKind as object_kind,
        CreatorName as creator,
        CreateTimeStamp as create_date,
        LastAlterTimeStamp as modify_date,
        CommentString as description
    FROM DBC.TablesV
    WHERE DatabaseName = '{database}'
        AND TableKind IN ('P', 'F', 'M', 'E', 'R')
    ORDER BY DatabaseName, TableName
    """

    objects = _execute_query(cursor, obj_query)

    procedures = []
    functions = []
    macros = []

    for obj in objects:
        obj_name = obj['object_name']
        obj_kind = obj['object_kind']

        # Get source code from TableTextV
        text_query = f"""
        SELECT RequestText, LineNo
        FROM DBC.TableTextV
        WHERE DatabaseName = '{database}'
            AND TableName = '{obj_name}'
        ORDER BY LineNo
        """

        text_results = _execute_query(cursor, text_query)
        source_code = '\n'.join([r.get('requesttext', '') for r in text_results])

        # Try to get function/procedure info from UDFInfo if available
        parameters = []
        return_type = None
        language = 'SQL'

        if obj_kind in ('F', 'P', 'E', 'R'):
            udf_query = f"""
            SELECT
                SpecificName as specific_name,
                ParameterDataType as parameter_type,
                ParameterStyle as parameter_style,
                TypeUDTName as return_type,
                SQLDataAccess as sql_data_access,
                Deterministic as is_deterministic,
                ExternalLanguageName as external_language
            FROM DBC.UDFInfo
            WHERE DatabaseName = '{database}'
                AND UDFName = '{obj_name}'
            """

            udf_results = _execute_query(cursor, udf_query)
            if udf_results:
                udf_info = udf_results[0]
                return_type = udf_info.get('return_type')
                language = udf_info.get('external_language', 'SQL')

        obj_data = {
            'database_name': obj['database_name'],
            'object_name': obj_name,
            'object_kind': obj_kind,
            'definition': source_code,
            'creator': obj.get('creator'),
            'create_date': obj.get('create_date'),
            'modify_date': obj.get('modify_date'),
            'description': obj.get('description'),
            'language': language,
            'return_type': return_type,
            'parameters': parameters,
        }

        if obj_kind in ('P', 'E', 'R'):  # Procedures
            procedures.append({
                'schema_name': obj['database_name'],
                'procedure_name': obj_name,
                'definition': source_code,
                'creator': obj.get('creator'),
                'create_date': obj.get('create_date'),
                'modify_date': obj.get('modify_date'),
                'description': obj.get('description'),
                'language': language,
                'is_external': obj_kind == 'E',
            })
        elif obj_kind == 'F':  # Functions
            functions.append({
                'schema_name': obj['database_name'],
                'function_name': obj_name,
                'definition': source_code,
                'return_type': return_type,
                'creator': obj.get('creator'),
                'create_date': obj.get('create_date'),
                'modify_date': obj.get('modify_date'),
                'description': obj.get('description'),
                'language': language,
            })
        elif obj_kind == 'M':  # Macros
            macros.append({
                'schema_name': obj['database_name'],
                'macro_name': obj_name,
                'definition': source_code,
                'creator': obj.get('creator'),
                'create_date': obj.get('create_date'),
                'modify_date': obj.get('modify_date'),
                'description': obj.get('description'),
            })

    return procedures, functions, macros


def _extract_table_statistics(cursor, database: str, table_name: str) -> Dict[str, Any]:
    """Extract table statistics including row count and space usage."""
    query = f"""
    SELECT
        SUM(CurrentPerm) as current_perm_bytes,
        SUM(PeakPerm) as peak_perm_bytes
    FROM DBC.TableSizeV
    WHERE DatabaseName = '{database}'
        AND TableName = '{table_name}'
    """

    results = _execute_query(cursor, query)

    stats = {
        'current_perm_bytes': 0,
        'peak_perm_bytes': 0,
        'row_count': 0,
    }

    if results:
        stats['current_perm_bytes'] = results[0].get('current_perm_bytes', 0)
        stats['peak_perm_bytes'] = results[0].get('peak_perm_bytes', 0)

    # Try to get row count (may require statistics to be collected)
    try:
        count_query = f'SELECT COUNT(*) as row_count FROM {database}.{table_name}'
        count_results = _execute_query(cursor, count_query)
        if count_results:
            stats['row_count'] = count_results[0].get('row_count', 0)
    except:
        # If count fails, try to get from DBC.TableStatsV if available
        stats_query = f"""
        SELECT ApproxRowCount as row_count
        FROM DBC.TableStatsV
        WHERE DatabaseName = '{database}'
            AND TableName = '{table_name}'
        """
        stats_results = _execute_query(cursor, stats_query)
        if stats_results:
            stats['row_count'] = stats_results[0].get('row_count', 0)

    return stats


def _compute_levels(graph: Dict[str, Iterable[str]], start: str, max_depth: int = 5) -> Dict[str, List[str]]:
    """Compute dependency levels using BFS."""
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
        "database_tables": {},
        "full_hierarchy": {},
    }

    table_name_counts = defaultdict(list)
    database_tables = defaultdict(list)

    for table in tables:
        db_name = table.get('database_name', database)
        name = table['table_name']
        table_type = table.get('table_type', 'TABLE')

        qualified_name = f"{db_name}.{name}"

        table_name_counts[name].append(qualified_name)
        database_tables[db_name].append(name)

        # Store all possible name variations
        for key in [name, qualified_name, name.upper(), qualified_name.upper()]:
            disambiguation["full_hierarchy"][key] = {
                "table_name": name,
                "database": db_name,
                "qualified_name": qualified_name,
                "type": table_type,
            }

    # Categorize as unique or ambiguous
    for table_name, qualified_names in table_name_counts.items():
        if len(qualified_names) == 1:
            disambiguation["unique_tables"][table_name] = qualified_names[0]
        else:
            disambiguation["ambiguous_tables"][table_name] = sorted(qualified_names)

    disambiguation["database_tables"] = dict(database_tables)

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
        db_name = column.get('database_name', database)
        table = column['table_name']
        col_name = column['column_name']

        qualified_table = f"{db_name}.{table}"
        qualified_column = f"{qualified_table}.{col_name}"

        col_metadata = {
            "name": col_name,
            "data_type": column.get('data_type'),
            "column_length": column.get('column_length'),
            "numeric_precision": column.get('numeric_precision'),
            "numeric_scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable') == 'Y',
            "column_default": column.get('column_default'),
            "comment": column.get('comment'),
            "column_format": column.get('column_format'),
            "qualified_name": qualified_column,
            "table": qualified_table,
            "database": db_name,
        }

        if qualified_table not in column_map["by_table"]:
            column_map["by_table"][qualified_table] = []
        column_map["by_table"][qualified_table].append(col_metadata)

        column_name_counts[col_name].add(qualified_table)
        column_map["by_column_name"][col_name].append(qualified_table)

        column_map["column_types"][qualified_column] = {
            "data_type": column.get('data_type'),
            "column_length": column.get('column_length'),
            "numeric_precision": column.get('numeric_precision'),
            "numeric_scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable') == 'Y',
        }

    # Identify unique columns
    for col_name, tables in column_name_counts.items():
        if len(tables) == 1:
            column_map["unique_columns"][col_name] = list(tables)[0]

    column_map["by_column_name"] = dict(column_map["by_column_name"])

    return column_map


def _is_transient_error(error: Exception) -> bool:
    """Check if the error is a transient Teradata error that should be retried."""
    error_str = str(error).upper()
    transient_indicators = [
        "TIMEOUT",
        "CONNECTION",
        "NETWORK",
        "RETRY",
        "UNAVAILABLE",
        "SERVICE UNAVAILABLE",
        "TRANSACTION ABORTED",
        "DEADLOCK",
    ]
    return any(indicator in error_str for indicator in transient_indicators)


def extract_enhanced_database_metadata(
    host: str,
    database: str,
    username: str,
    password: str,
    logmech: str = "TD2",
    encryptdata: bool = False,
    charset: str = "UTF8",
    tmode: str = "ANSI",
    output_dir: Path | None = None,
    max_retries: int = 3,
    initial_retry_delay: float = 2.0,
    extract_statistics: bool = False,
) -> Tuple[Dict[str, Any], Path]:
    """Extract comprehensive metadata from Teradata database.

    Args:
        host: Teradata server hostname or IP address
        database: Database name
        username: Login username
        password: Login password
        logmech: Authentication mechanism (TD2, LDAP, KRB5, etc.)
        encryptdata: Enable data encryption
        charset: Character set
        tmode: Transaction mode (ANSI or TERA)
        output_dir: Output directory for metadata files
        max_retries: Maximum number of retry attempts for transient errors
        initial_retry_delay: Initial delay in seconds before first retry
        extract_statistics: Extract table statistics (row counts, space usage)

    Returns:
        Tuple of (metadata dictionary, output file path)

    Raises:
        RuntimeError: If connection fails after all retries
        ImportError: If teradatasql is not installed
    """

    if teradatasql is None:
        raise ImportError(
            "teradatasql is required. "
            "Install it with: pip install teradatasql"
        )

    metadata: Dict[str, Any] = {"database": database, "host": host}
    conn = None

    conn_params = build_connection_params(
        host=host,
        database=database,
        username=username,
        password=password,
        logmech=logmech,
        encryptdata=encryptdata,
        charset=charset,
        tmode=tmode,
    )

    # Retry logic for transient errors
    last_error = None
    for attempt in range(max_retries):
        try:
            if conn is not None:
                try:
                    conn.close()
                except:
                    pass

            print(f"Connecting to Teradata at {host}...")
            conn = teradatasql.connect(**conn_params)
            cursor = conn.cursor()

            # Set default database
            cursor.execute(f"DATABASE {database}")

            print("Extracting tables and views...")
            # 1. Extract Tables and Views
            tables, views = _extract_tables_and_views(cursor, database)
            print(f"Found {len(tables)} tables and {len(views)} views")

            print("Extracting columns...")
            # 2. Extract Columns
            columns = _extract_columns(cursor, database)
            print(f"Found {len(columns)} columns")

            print("Extracting indexes...")
            # 3. Extract Indexes (including primary keys)
            indexes = _extract_indexes(cursor, database)
            print(f"Found {len(indexes)} index entries")

            print("Extracting foreign keys...")
            # 4. Extract Foreign Keys
            foreign_keys = _extract_foreign_keys(cursor, database)
            print(f"Found {len(foreign_keys)} foreign key relationships")

            print("Extracting procedures, functions, and macros...")
            # 5. Extract Procedures, Functions, and Macros
            procedures, functions, macros = _extract_procedures_functions_macros(cursor, database)
            print(f"Found {len(procedures)} procedures, {len(functions)} functions, {len(macros)} macros")

            # 6. Extract table statistics if requested
            table_statistics = {}
            if extract_statistics:
                print("Extracting table statistics...")
                for table in tables:
                    table_name = table['table_name']
                    try:
                        stats = _extract_table_statistics(cursor, database, table_name)
                        table_statistics[table_name] = stats
                    except Exception as e:
                        print(f"Could not extract statistics for {table_name}: {e}")

            # Filter system objects
            tables = _filter_system_objects(tables, 'database_name')
            views = _filter_system_objects(views, 'database_name')
            procedures = _filter_system_objects(procedures, 'database_name')
            functions = _filter_system_objects(functions, 'database_name')
            macros = _filter_system_objects(macros, 'database_name')

            print(f"After filtering: {len(tables)} tables, {len(views)} views, {len(procedures)} procedures, {len(functions)} functions, {len(macros)} macros")

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
                error_msg = f"Teradata connection failed: {exc}"
                if is_transient and attempt == max_retries - 1:
                    error_msg += f"\n\nAttempted {max_retries} times with exponential backoff."
                raise RuntimeError(error_msg) from exc

            # Transient error - retry with exponential backoff
            retry_delay = initial_retry_delay * (2 ** attempt)
            print(f"Transient error (attempt {attempt + 1}/{max_retries}): {exc}")
            print(f"Retrying in {retry_delay:.1f} seconds...")
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
        db_name = table['database_name']
        table_name = table['table_name']
        key = f"{db_name}.{table_name}"

        table_map[key] = {
            "database": db_name,
            "name": table_name,
            "type": table.get('table_type', 'TABLE'),
            "table_kind": table.get('table_kind', 'T'),
            "qualified_name": key,
            "description": table.get('description'),
            "creator": table.get('creator'),
            "create_date": str(table.get('create_date')) if table.get('create_date') else None,
            "modify_date": str(table.get('modify_date')) if table.get('modify_date') else None,
            "primary_key_index_id": table.get('primary_key_index_id'),
            "replication_status": table.get('replication_status'),
            "transaction_log": table.get('transaction_log'),
            "journal_flag": table.get('journal_flag'),
            "temporary_flag": table.get('temporary_flag'),
            "columns": [],
            "primary_key": [],
            "indexes": [],
            "foreign_keys": [],
            "statistics": table_statistics.get(table_name, {}),
            "dependencies": {
                "depends_on": [],
                "referenced_by": [],
            }
        }

    # Process columns
    for column in columns:
        db_name = column['database_name']
        table_name = column['table_name']
        key = f"{db_name}.{table_name}"

        if key not in table_map:
            continue

        column_details = {
            "name": column['column_name'],
            "ordinal_position": column['ordinal_position'],
            "data_type": column['data_type'],
            "column_length": column.get('column_length'),
            "numeric_precision": column.get('numeric_precision'),
            "numeric_scale": column.get('numeric_scale'),
            "is_nullable": column.get('is_nullable') == 'Y',
            "column_default": column.get('column_default'),
            "comment": column.get('comment'),
            "column_format": column.get('column_format'),
            "upper_case_flag": column.get('upper_case_flag'),
            "identity_type": column.get('identity_type'),
            "compressible": column.get('compressible'),
            "qualified_name": f"{key}.{column['column_name']}",
        }
        table_map[key]["columns"].append(column_details)

    # Process indexes and primary keys
    index_map = defaultdict(lambda: defaultdict(list))
    for idx in indexes:
        db_name = idx['database_name']
        table_name = idx['table_name']
        key = f"{db_name}.{table_name}"

        if key not in table_map:
            continue

        index_number = idx['index_number']
        index_map[key][index_number].append({
            'column_name': idx['column_name'],
            'column_position': idx['column_position'],
            'index_type': idx['index_type'],
            'index_name': idx.get('index_name'),
            'is_unique': idx.get('is_unique') == 'Y',
        })

    # Organize indexes
    for key, indexes_by_num in index_map.items():
        if key not in table_map:
            continue

        for index_number, index_cols in indexes_by_num.items():
            sorted_cols = sorted(index_cols, key=lambda x: x['column_position'])

            # Check if this is a primary key (index_number == 1 typically)
            if index_number == 1 or sorted_cols[0].get('index_type') == 'P':
                table_map[key]["primary_key"] = [col['column_name'] for col in sorted_cols]

            # Add to indexes list
            table_map[key]["indexes"].append({
                'index_number': index_number,
                'index_name': sorted_cols[0].get('index_name', f'INDEX_{index_number}'),
                'index_type': sorted_cols[0].get('index_type'),
                'is_unique': sorted_cols[0].get('is_unique', False),
                'columns': [col['column_name'] for col in sorted_cols],
            })

    # Process foreign keys
    fk_map = defaultdict(list)
    for fk in foreign_keys:
        db_name = fk['database_name']
        table_name = fk['table_name']
        key = f"{db_name}.{table_name}"

        if key not in table_map:
            continue

        fk_map[key].append({
            "constraint": fk['constraint_name'],
            "column": fk['column_name'],
            "referenced_database": fk['referenced_database'],
            "referenced_table": fk['referenced_table'],
            "referenced_column": fk.get('referenced_column'),
            "references": f"{fk['referenced_database']}.{fk['referenced_table']}({fk.get('referenced_column', 'unknown')})",
            "inconsistency_flag": fk.get('inconsistency_flag'),
        })

    for key, fk_list in fk_map.items():
        if key in table_map:
            table_map[key]["foreign_keys"] = fk_list

    # Build dependency graph from foreign keys
    dependency_graph: Dict[str, set[str]] = defaultdict(set)
    reverse_dependency_graph: Dict[str, set[str]] = defaultdict(set)

    for key, table in table_map.items():
        for fk in table["foreign_keys"]:
            referenced = f"{fk['referenced_database']}.{fk['referenced_table']}"
            dependency_graph[key].add(referenced)
            reverse_dependency_graph[referenced].add(key)

    for key, table in table_map.items():
        table["dependencies"]["depends_on"] = sorted(dependency_graph.get(key, []))
        table["dependencies"]["referenced_by"] = sorted(reverse_dependency_graph.get(key, []))

    # Assemble final metadata
    sorted_tables = sorted(table_map.values(), key=lambda t: (t["database"], t["name"]))
    table_disambiguation = _build_table_disambiguation_map(sorted_tables, database)
    column_map = _build_column_map(columns, database)

    metadata["tables"] = sorted_tables
    metadata["views"] = views
    metadata["procedures"] = procedures
    metadata["functions"] = functions
    metadata["macros"] = macros

    # Add parser support maps
    metadata["parser_support"] = {
        "table_disambiguation": table_disambiguation,
        "column_map": column_map,
        "database_name": database,
    }

    # Add summary statistics
    metadata["summary"] = {
        "database": database,
        "host": host,
        "extraction_timestamp": datetime.now(UTC).isoformat(),
        "table_count": len(metadata["tables"]),
        "view_count": len(metadata["views"]),
        "procedure_count": len(metadata["procedures"]),
        "function_count": len(metadata["functions"]),
        "macro_count": len(metadata["macros"]),
        "column_count": len(columns),
        "index_count": len(indexes),
        "foreign_key_count": len(foreign_keys),
        "unique_table_names": len(table_disambiguation["unique_tables"]),
        "ambiguous_table_names": len(table_disambiguation["ambiguous_tables"]),
    }

    # Save metadata
    output_directory = _ensure_output_dir(output_dir)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_db = database.replace("/", "-").replace("\\", "-")
    file_path = output_directory / f"enhanced_metadata_{safe_db}_{timestamp}.json"

    with file_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2, default=str)

    print(f"\nMetadata extraction complete. Saved to: {file_path}")
    print(f"\nExtraction Summary:")
    print(f"  Tables: {metadata['summary']['table_count']}")
    print(f"  Views: {metadata['summary']['view_count']}")
    print(f"  Procedures: {metadata['summary']['procedure_count']}")
    print(f"  Functions: {metadata['summary']['function_count']}")
    print(f"  Macros: {metadata['summary']['macro_count']}")
    print(f"  Columns: {metadata['summary']['column_count']}")
    print(f"  Indexes: {metadata['summary']['index_count']}")
    print(f"  Foreign Keys: {metadata['summary']['foreign_key_count']}")

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
    print("Enhanced Teradata Metadata Extractor")
    print("=" * 70)
    print()

    # Get connection parameters
    if len(sys.argv) >= 4:
        host = sys.argv[1]
        database = sys.argv[2]
        username = sys.argv[3]
        password = sys.argv[4] if len(sys.argv) > 4 else ""
        logmech = sys.argv[5] if len(sys.argv) > 5 else "TD2"
    else:
        print("Usage: python enhanced_metadata_extractor.py <host> <database> <username> [password] [logmech]")
        print("\nOr provide interactively:")
        host = input("Host: ").strip()
        database = input("Database: ").strip()
        username = input("Username: ").strip()
        password = getpass.getpass("Password: ")
        logmech = input("Logmech (default: TD2): ").strip() or "TD2"

    if not all([host, database, username, password]):
        print("Error: Host, database, username, and password are required.")
        sys.exit(1)

    # Ask about statistics extraction
    extract_stats = input("Extract table statistics (row counts, space usage)? [y/N]: ").strip().lower() == 'y'

    try:
        print(f"\nConnecting to Teradata at {host}, database {database}...")
        metadata, file_path = extract_enhanced_database_metadata(
            host=host,
            database=database,
            username=username,
            password=password,
            logmech=logmech,
            extract_statistics=extract_stats,
        )
        print(f"\nSuccess! Metadata saved to: {file_path}")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
