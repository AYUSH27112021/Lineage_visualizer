"""
Enhanced Snowflake Specific Cleaner
Handles Snowflake specific syntax, multi-statement blocks, procedures, functions, and complex patterns
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class SQLBatch:
    """Represents a batch of SQL statements"""
    content: str
    batch_type: str  # 'statement', 'procedure', 'function', 'view', 'task', 'stream'
    object_name: Optional[str] = None
    line_number: int = 0


class EnhancedSQLCleaner:
    """Enhanced Snowflake specific SQL file cleaner with procedure/function awareness"""

    def __init__(self, sql_directory: str, debug: bool = False):
        self.sql_directory = Path(sql_directory)
        self.debug = debug
        self.stats = defaultdict(int)

        # Compile regex patterns for performance
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile all regex patterns"""
        # Comment patterns
        self.multiline_comment = re.compile(r'/\*.*?\*/', re.DOTALL)
        self.single_line_comment = re.compile(r'--[^\n]*')

        # Snowflake doesn't use GO, but we might encounter batch separators
        self.semicolon_separator = re.compile(r';\s*(?=\n|$)')

        # Snowflake-specific patterns
        self.execute_immediate = re.compile(r'EXECUTE\s+IMMEDIATE', re.IGNORECASE)
        self.execute_task = re.compile(r'EXECUTE\s+TASK', re.IGNORECASE)

        # Object creation patterns - Snowflake style
        self.create_proc = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?PROCEDURE\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.alter_proc = re.compile(
            r'ALTER\s+PROCEDURE\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_function = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?FUNCTION\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.alter_function = re.compile(
            r'ALTER\s+FUNCTION\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_view = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?(?:MATERIALIZED\s+)?VIEW\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.alter_view = re.compile(
            r'ALTER\s+(?:MATERIALIZED\s+)?VIEW\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_task = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?TASK\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_stream = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?STREAM\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_pipe = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?PIPE\s+([\w\.\"]+)',
            re.IGNORECASE
        )

        # Additional Snowflake object patterns
        self.create_stage = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMPORARY\s+)?STAGE\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_file_format = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?FILE\s+FORMAT\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_sequence = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?SEQUENCE\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_masking_policy = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?MASKING\s+POLICY\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_row_access_policy = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?ROW\s+ACCESS\s+POLICY\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_tag = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?TAG\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_dynamic_table = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?DYNAMIC\s+TABLE\s+([\w\.\"]+)',
            re.IGNORECASE
        )
        self.create_external_table = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?EXTERNAL\s+TABLE\s+([\w\.\"]+)',
            re.IGNORECASE
        )

        # Noise patterns - Snowflake specific
        self.use_database = re.compile(r'USE\s+(?:DATABASE|SCHEMA|WAREHOUSE|ROLE)\s+[\w\.\"]+\s*;?', re.IGNORECASE)
        self.alter_session = re.compile(r'ALTER\s+SESSION\s+SET\s+[^;]+;?', re.IGNORECASE)
        self.show_statement = re.compile(r'SHOW\s+\w+[^;]*;?', re.IGNORECASE)
        self.describe_statement = re.compile(r'(?:DESC|DESCRIBE)\s+\w+[^;]*;?', re.IGNORECASE)
        self.list_statement = re.compile(r'LIST\s+@[\w\.\/]+[^;]*;?', re.IGNORECASE)
        self.rm_statement = re.compile(r'RM\s+@[\w\.\/]+[^;]*;?', re.IGNORECASE)
        self.put_statement = re.compile(r'PUT\s+[^;]+;?', re.IGNORECASE)
        self.get_statement = re.compile(r'GET\s+[^;]+;?', re.IGNORECASE)

        # Transaction control - Snowflake
        self.begin_tran = re.compile(r'BEGIN\s*(?:TRANSACTION|WORK|NAME\s+\w+)?\s*;?', re.IGNORECASE)
        self.commit_tran = re.compile(r'COMMIT\s*(?:WORK)?\s*;?', re.IGNORECASE)
        self.rollback_tran = re.compile(r'ROLLBACK\s*(?:WORK)?\s*;?', re.IGNORECASE)

        # Temp table patterns - Snowflake style
        self.temp_table = re.compile(r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMPORARY|TEMP|TRANSIENT)\s+TABLE', re.IGNORECASE)
        self.temp_table_name = re.compile(r'TEMP_[\w]+|TMP_[\w]+', re.IGNORECASE)

        # Variant/JSON access patterns
        self.variant_access = re.compile(r'[\w\.\"]+:[:\w\.\"]+')
        self.lateral_flatten = re.compile(r'LATERAL\s+FLATTEN\s*\(', re.IGNORECASE)

        # Time travel patterns
        self.time_travel = re.compile(r'AT\s*\(\s*(?:TIMESTAMP|OFFSET|STATEMENT)\s*=>', re.IGNORECASE)
        self.changes_clause = re.compile(r'CHANGES\s*\(\s*INFORMATION\s*=>', re.IGNORECASE)

        # Data loading patterns
        self.copy_into = re.compile(r'COPY\s+INTO', re.IGNORECASE)
        self.stage_reference = re.compile(r'@[\w\.\/]+', re.IGNORECASE)

        # Snowflake special clauses
        self.qualify_clause = re.compile(r'\bQUALIFY\b', re.IGNORECASE)
        self.match_recognize = re.compile(r'MATCH_RECOGNIZE\s*\(', re.IGNORECASE)
        self.pivot_clause = re.compile(r'\bPIVOT\s*\(', re.IGNORECASE)
        self.unpivot_clause = re.compile(r'\bUNPIVOT\s*\(', re.IGNORECASE)
        self.sample_clause = re.compile(r'\bSAMPLE\s*\(', re.IGNORECASE)
        self.connect_by = re.compile(r'CONNECT\s+BY', re.IGNORECASE)

        # Result scan and metadata
        self.result_scan = re.compile(r'RESULT_SCAN\s*\(', re.IGNORECASE)
        self.generator = re.compile(r'GENERATOR\s*\(', re.IGNORECASE)

        # Procedure body delimiters
        self.proc_body_delimiter = re.compile(r'\$\$', re.DOTALL)

    def clean_all_files(self, max_files: int = None) -> Dict[str, Dict[str, List]]:
        """Clean all SQL files in directory"""
        cleaned_results = {}
        sql_files = list(self.sql_directory.rglob("*.sql"))

        if max_files:
            sql_files = sql_files[:max_files]

        print(f"   Found {len(sql_files)} SQL files")

        for sql_file in sql_files:
            try:
                relative_path = str(sql_file.relative_to(self.sql_directory))
                result = self._clean_file(sql_file)

                if result['statements'] or result['procedures'] or result['functions']:
                    cleaned_results[relative_path] = result
                    if self.debug:
                        print(f"   ✓ {relative_path}: {len(result['statements'])} statements, "
                              f"{len(result['procedures'])} procedures, "
                              f"{len(result['functions'])} functions")

            except Exception as e:
                print(f"   Warning: Error cleaning {sql_file.name}: {e}")
                self.stats['errors'] += 1

        self._print_stats()
        return cleaned_results

    def _clean_file(self, filepath: Path) -> Dict[str, List]:
        """Clean a single SQL file and categorize content"""
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Step 1: Remove comments
        content = self._remove_comments(content)
        self.stats['comments_removed'] += 1

        # Step 2: Remove noise statements
        content = self._remove_noise(content)

        # Step 3: Split into batches (Snowflake uses CREATE/ALTER blocks)
        batches = self._split_into_batches(content)

        # Step 4: Classify and extract batches
        result = {
            'statements': [],
            'procedures': [],
            'functions': [],
            'views': [],
            'tasks': [],
            'streams': [],
            'temp_tables': []
        }

        for batch in batches:
            classified = self._classify_batch(batch)

            if classified.batch_type == 'procedure':
                result['procedures'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number
                })
                self.stats['procedures_found'] += 1

            elif classified.batch_type == 'function':
                # Detect function type (scalar vs table-valued)
                func_type = self._detect_function_type(classified.content)
                result['functions'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number,
                    'type': func_type
                })
                self.stats['functions_found'] += 1

            elif classified.batch_type == 'view':
                result['views'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number
                })
                self.stats['views_found'] += 1

            elif classified.batch_type == 'task':
                result['tasks'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number
                })
                self.stats['tasks_found'] += 1

            elif classified.batch_type == 'stream':
                result['streams'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number
                })
                self.stats['streams_found'] += 1

            else:
                # Regular statements
                statements = self._extract_statements(classified.content)
                result['statements'].extend(statements)

                # Track temp tables
                temp_tables = self._extract_temp_tables(classified.content)
                result['temp_tables'].extend(temp_tables)

        return result

    def _remove_comments(self, content: str) -> str:
        """Remove SQL comments while preserving string literals"""
        # Remove multiline comments
        content = self.multiline_comment.sub('', content)
        # Remove single line comments
        content = self.single_line_comment.sub('', content)
        return content

    def _remove_noise(self, content: str) -> str:
        """Remove non-DML/DDL statements"""
        # USE DATABASE/SCHEMA/WAREHOUSE/ROLE
        content = self.use_database.sub('', content)

        # ALTER SESSION
        content = self.alter_session.sub('', content)

        # SHOW statements
        content = self.show_statement.sub('', content)

        # DESCRIBE statements
        content = self.describe_statement.sub('', content)

        return content

    def _split_into_batches(self, content: str) -> List[str]:
        """Split content into logical batches based on CREATE/ALTER statements"""
        batches = []
        current_batch = []
        lines = content.split('\n')

        # Patterns that start a new batch
        batch_starters = [
            r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:SECURE\s+)?(?:PROCEDURE|FUNCTION|VIEW|TASK|STREAM|PIPE|TABLE|MATERIALIZED)',
            r'ALTER\s+(?:PROCEDURE|FUNCTION|VIEW|TABLE|TASK|STREAM)',
        ]
        batch_pattern = re.compile('|'.join(batch_starters), re.IGNORECASE)

        in_block = False
        block_depth = 0

        for line in lines:
            stripped = line.strip()

            # Check if this line starts a new batch
            if batch_pattern.match(stripped):
                # Save current batch if exists
                if current_batch:
                    batch_text = '\n'.join(current_batch).strip()
                    if batch_text:
                        batches.append(batch_text)
                current_batch = [line]
                in_block = True
                block_depth = 0

                # Count opening blocks
                block_depth += stripped.upper().count('BEGIN')
                block_depth += stripped.upper().count('$$')
            else:
                current_batch.append(line)

                if in_block:
                    # Track block depth for procedures/functions
                    block_depth += stripped.upper().count('BEGIN')
                    block_depth -= stripped.upper().count('END')

                    # Handle $$ delimiters (Snowflake procedure bodies)
                    if '$$' in stripped:
                        block_depth = 0 if block_depth > 0 else 1

        # Add final batch
        if current_batch:
            batch_text = '\n'.join(current_batch).strip()
            if batch_text:
                batches.append(batch_text)

        # If no clear batches found, treat as single batch
        if not batches:
            batches = [content.strip()] if content.strip() else []

        return batches

    def _classify_batch(self, batch: str) -> SQLBatch:
        """Classify what type of batch this is"""
        batch_stripped = batch.strip()

        # Check for procedures
        proc_match = self.create_proc.search(batch) or self.alter_proc.search(batch)
        if proc_match:
            return SQLBatch(
                content=batch,
                batch_type='procedure',
                object_name=proc_match.group(1).strip('"')
            )

        # Check for functions
        func_match = self.create_function.search(batch) or self.alter_function.search(batch)
        if func_match:
            return SQLBatch(
                content=batch,
                batch_type='function',
                object_name=func_match.group(1).strip('"')
            )

        # Check for views
        view_match = self.create_view.search(batch) or self.alter_view.search(batch)
        if view_match:
            return SQLBatch(
                content=batch,
                batch_type='view',
                object_name=view_match.group(1).strip('"')
            )

        # Check for tasks
        task_match = self.create_task.search(batch)
        if task_match:
            return SQLBatch(
                content=batch,
                batch_type='task',
                object_name=task_match.group(1).strip('"')
            )

        # Check for streams
        stream_match = self.create_stream.search(batch)
        if stream_match:
            return SQLBatch(
                content=batch,
                batch_type='stream',
                object_name=stream_match.group(1).strip('"')
            )

        # Default: regular statement batch
        return SQLBatch(
            content=batch,
            batch_type='statement'
        )

    def _extract_statements(self, batch: str) -> List[str]:
        """Extract valid SQL statements from a batch"""
        if not batch:
            return []

        statements = []
        current = []
        in_string = False
        string_char = None
        paren_depth = 0

        lines = batch.split('\n')

        for line in lines:
            stripped = line.strip()

            if not stripped:
                continue

            # Track string literals and parentheses
            i = 0
            while i < len(line):
                char = line[i]

                if char in ('"', "'") and not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char and in_string:
                    # Check for escaped quotes
                    if i + 1 < len(line) and line[i + 1] == string_char:
                        i += 1  # Skip escaped quote
                    else:
                        in_string = False
                        string_char = None
                elif not in_string:
                    if char == '(':
                        paren_depth += 1
                    elif char == ')':
                        paren_depth -= 1

                i += 1

            current.append(line)

            # Check if statement is complete
            if self._is_statement_complete(stripped, in_string, paren_depth):
                stmt = '\n'.join(current).strip()
                if self._is_valid_statement(stmt):
                    statements.append(stmt)
                    self.stats['statements_extracted'] += 1
                current = []
                paren_depth = 0

        # Handle remaining content
        if current:
            stmt = '\n'.join(current).strip()
            if self._is_valid_statement(stmt):
                statements.append(stmt)
                self.stats['statements_extracted'] += 1

        return statements

    def _is_statement_complete(self, line: str, in_string: bool, paren_depth: int) -> bool:
        """Check if statement is complete"""
        if in_string or paren_depth > 0:
            return False

        return line.endswith(';')

    def _is_valid_statement(self, stmt: str) -> bool:
        """Check if statement should be processed"""
        if not stmt or len(stmt) < 10:
            return False

        stmt_upper = stmt.upper().strip()

        # Skip variable declarations (unless they're useful)
        if stmt_upper.startswith('LET') or stmt_upper.startswith('DECLARE'):
            # Keep if it contains a SELECT or other data operation
            if any(kw in stmt_upper for kw in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                return True
            self.stats['declares_skipped'] += 1
            return False

        # Skip SET statements (session variables)
        if stmt_upper.startswith('SET') and '=' in stmt_upper:
            self.stats['sets_skipped'] += 1
            return False

        # Skip standalone transaction control
        if stmt_upper.startswith(('BEGIN TRANSACTION', 'COMMIT', 'ROLLBACK')):
            self.stats['transactions_skipped'] += 1
            return False

        # Skip CALL statements (procedure calls without useful info)
        # But keep EXECUTE IMMEDIATE as it may contain dynamic SQL

        # Valid statement types
        valid_starts = [
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE',
            'CREATE TABLE', 'CREATE VIEW', 'CREATE OR REPLACE', 'CREATE INDEX',
            'CREATE TEMPORARY', 'CREATE TRANSIENT',
            'ALTER TABLE', 'ALTER VIEW',
            'WITH',  # CTEs
            'DROP', 'TRUNCATE',
            'COPY', 'PUT', 'GET',  # Snowflake data loading
            'EXECUTE IMMEDIATE'
        ]

        is_valid = any(stmt_upper.startswith(start) for start in valid_starts)

        if not is_valid:
            self.stats['invalid_start'] += 1

        return is_valid

    def _detect_function_type(self, content: str) -> str:
        """Detect if function is scalar or table-valued based on RETURNS clause"""
        content_upper = content.upper()

        # Check for RETURNS TABLE (table-valued function)
        if re.search(r'RETURNS\s+TABLE\s*\(', content_upper):
            return 'TABLE_FUNCTION'

        # Check for RETURNS with a data type (scalar function)
        if re.search(r'RETURNS\s+(?:VARCHAR|STRING|NUMBER|INTEGER|FLOAT|BOOLEAN|DATE|TIMESTAMP|VARIANT|OBJECT|ARRAY)', content_upper):
            return 'SCALAR_FUNCTION'

        # Default to FUNCTION if we can't determine
        return 'FUNCTION'

    def _extract_temp_tables(self, batch: str) -> List[Dict[str, str]]:
        """Extract temp table references"""
        temp_tables = []

        # Find CREATE TEMPORARY/TRANSIENT TABLE statements
        if self.temp_table.search(batch):
            # Extract table name
            name_match = re.search(r'(?:TEMPORARY|TEMP|TRANSIENT)\s+TABLE\s+([\w\.\"]+)', batch, re.IGNORECASE)
            if name_match:
                temp_tables.append({
                    'name': name_match.group(1).strip('"'),
                    'type': 'temporary'
                })

        # Find tables with temp naming convention
        for match in self.temp_table_name.finditer(batch):
            table_name = match.group(0)
            if not any(t['name'] == table_name for t in temp_tables):
                temp_tables.append({
                    'name': table_name,
                    'type': 'naming_convention'
                })

        return temp_tables

    def _print_stats(self):
        """Print cleaning statistics"""
        if self.debug:
            print("\n   Cleaning Statistics:")
            for key, value in sorted(self.stats.items()):
                print(f"      {key:30s}: {value:6d}")
            print()


if __name__ == "__main__":
    cleaner = EnhancedSQLCleaner("./sql_files", debug=True)
    results = cleaner.clean_all_files(max_files=5)

    for file_path, content in results.items():
        print(f"\n{file_path}:")
        print(f"  Statements: {len(content['statements'])}")
        print(f"  Procedures: {len(content['procedures'])}")
        print(f"  Functions: {len(content['functions'])}")
        print(f"  Views: {len(content['views'])}")
        print(f"  Tasks: {len(content.get('tasks', []))}")
        print(f"  Streams: {len(content.get('streams', []))}")
