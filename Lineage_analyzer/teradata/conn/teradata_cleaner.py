"""
Enhanced Teradata-Specific SQL Cleaner
Handles Teradata-specific syntax, batch separators, procedures, macros, functions, and complex patterns
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
    batch_type: str  # 'statement', 'procedure', 'macro', 'function', 'view', 'trigger'
    object_name: Optional[str] = None
    line_number: int = 0


class TeradataSQLCleaner:
    """Enhanced Teradata-specific SQL file cleaner with procedure/macro/function awareness"""

    def __init__(self, sql_directory: str, debug: bool = False):
        self.sql_directory = Path(sql_directory)
        self.debug = debug
        self.stats = defaultdict(int)

        # Compile regex patterns for performance
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile all Teradata-specific regex patterns"""
        # Comment patterns
        self.multiline_comment = re.compile(r'/\*.*?\*/', re.DOTALL)
        self.single_line_comment = re.compile(r'--[^\n]*')

        # Teradata batch separator (semicolon for most statements)
        self.semicolon_separator = re.compile(r';')

        # BTEQ-specific patterns
        self.bteq_command = re.compile(
            r'^\s*\.(LOGON|LOGOFF|RUN\s+FILE|QUIT|EXIT|SET|LABEL|EXPORT|IMPORT|IF|GOTO|REMARK)\b.*$',
            re.IGNORECASE | re.MULTILINE
        )
        self.bt_marker = re.compile(r'^\s*BT\s*;?\s*$', re.IGNORECASE | re.MULTILINE)
        self.et_marker = re.compile(r'^\s*ET\s*;?\s*$', re.IGNORECASE | re.MULTILINE)

        # Teradata PROCEDURE patterns
        self.create_proc = re.compile(
            r'CREATE\s+(?:OR\s+)?(?:REPLACE\s+)?(?:PROCEDURE|PROC)\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )
        self.replace_proc = re.compile(
            r'REPLACE\s+(?:PROCEDURE|PROC)\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Teradata MACRO patterns (Teradata-specific parameterized SQL)
        self.create_macro = re.compile(
            r'CREATE\s+(?:OR\s+)?(?:REPLACE\s+)?MACRO\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )
        self.replace_macro = re.compile(
            r'REPLACE\s+MACRO\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Teradata FUNCTION patterns
        self.create_function = re.compile(
            r'CREATE\s+(?:OR\s+)?(?:REPLACE\s+)?FUNCTION\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )
        self.replace_function = re.compile(
            r'REPLACE\s+FUNCTION\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Teradata VIEW patterns
        self.create_view = re.compile(
            r'CREATE\s+(?:OR\s+)?(?:REPLACE\s+)?VIEW\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )
        self.replace_view = re.compile(
            r'REPLACE\s+VIEW\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Teradata TRIGGER patterns
        self.create_trigger = re.compile(
            r'CREATE\s+(?:OR\s+)?(?:REPLACE\s+)?TRIGGER\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )
        self.replace_trigger = re.compile(
            r'REPLACE\s+TRIGGER\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Teradata temp table patterns
        # VOLATILE tables - session-specific temporary tables
        self.volatile_table = re.compile(
            r'(?:CREATE\s+)?(?:MULTISET\s+)?VOLATILE\s+TABLE\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # GLOBAL TEMPORARY tables
        self.global_temp_table = re.compile(
            r'CREATE\s+(?:MULTISET\s+)?GLOBAL\s+TEMPORARY\s+TABLE\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Teradata-specific noise patterns to remove
        self.database_stmt = re.compile(r'DATABASE\s+[\w\.\"\`]+\s*;?', re.IGNORECASE)
        self.collect_stats = re.compile(
            r'COLLECT\s+(?:STATISTICS|STAT)\s+(?:ON|FOR).*?;',
            re.IGNORECASE | re.DOTALL
        )
        self.help_stmt = re.compile(r'HELP\s+(?:TABLE|VIEW|MACRO|PROCEDURE|FUNCTION|DATABASE)\s+[\w\.\"\`]+\s*;?', re.IGNORECASE)
        self.show_stmt = re.compile(r'SHOW\s+(?:TABLE|VIEW|MACRO|PROCEDURE|FUNCTION|SELECT)\s+.*?;', re.IGNORECASE | re.DOTALL)

        # FastLoad/MultiLoad/TPump script markers
        self.fastload_marker = re.compile(
            r'\.(?:BEGIN\s+LOADING|END\s+LOADING|LOGON|LOGOFF)\b.*$',
            re.IGNORECASE | re.MULTILINE
        )
        self.multiload_marker = re.compile(
            r'\.(?:BEGIN\s+IMPORT|END\s+IMPORT|DML\s+LABEL|LOGTABLE)\b.*$',
            re.IGNORECASE | re.MULTILINE
        )
        self.tpump_marker = re.compile(
            r'\.(?:BEGIN\s+LOAD|END\s+LOAD|DML\s+LABEL)\b.*$',
            re.IGNORECASE | re.MULTILINE
        )

        # Teradata SET session parameters
        self.set_session = re.compile(r'SET\s+SESSION\s+.*?;', re.IGNORECASE | re.DOTALL)
        self.set_query_band = re.compile(r'SET\s+QUERY_BAND\s+=\s+.*?;', re.IGNORECASE | re.DOTALL)

        # Teradata diagnostic statements
        self.diagnostic_stmt = re.compile(r'DIAGNOSTIC\s+.*?;', re.IGNORECASE | re.DOTALL)
        self.explain_stmt = re.compile(r'EXPLAIN\s+.*?;', re.IGNORECASE | re.DOTALL)

        # Transaction control (Teradata uses BEGIN TRANSACTION, END TRANSACTION, COMMIT, ROLLBACK)
        self.begin_trans = re.compile(r'(?:BEGIN|BT)\s+(?:TRANSACTION|TRANS)\s*;?', re.IGNORECASE)
        self.end_trans = re.compile(r'(?:END|ET)\s+(?:TRANSACTION|TRANS)\s*;?', re.IGNORECASE)
        self.commit_trans = re.compile(r'COMMIT\s+(?:WORK)?\s*;?', re.IGNORECASE)
        self.rollback_trans = re.compile(r'ROLLBACK\s+(?:WORK)?\s*;?', re.IGNORECASE)

        # Teradata error handling
        self.signal_stmt = re.compile(r'SIGNAL\s+.*?;', re.IGNORECASE | re.DOTALL)
        self.resignal_stmt = re.compile(r'RESIGNAL\s+.*?;', re.IGNORECASE | re.DOTALL)

        # Teradata specific keywords for detection
        self.exec_macro = re.compile(r'EXEC(?:UTE)?\s+[\w\.\"\`]+\s*\(', re.IGNORECASE)
        self.call_proc = re.compile(r'CALL\s+[\w\.\"\`]+\s*\(', re.IGNORECASE)

        # Lock statements
        self.locking_stmt = re.compile(r'LOCKING\s+(?:TABLE|ROW|DATABASE)\s+.*?(?:FOR|IN)\s+.*?;', re.IGNORECASE | re.DOTALL)

    def clean_all_files(self, max_files: int = None) -> Dict[str, Dict[str, List]]:
        """Clean all SQL files in directory"""
        cleaned_results = {}
        sql_files = list(self.sql_directory.rglob("*.sql"))

        # Also look for .bteq files (common in Teradata environments)
        bteq_files = list(self.sql_directory.rglob("*.bteq"))
        sql_files.extend(bteq_files)

        if max_files:
            sql_files = sql_files[:max_files]

        print(f"   Found {len(sql_files)} SQL/BTEQ files")

        for sql_file in sql_files:
            try:
                relative_path = str(sql_file.relative_to(self.sql_directory))
                result = self._clean_file(sql_file)

                if (result['statements'] or result['procedures'] or
                    result['functions'] or result['macros'] or result['views']):
                    cleaned_results[relative_path] = result
                    if self.debug:
                        print(f"   ✓ {relative_path}: {len(result['statements'])} statements, "
                              f"{len(result['procedures'])} procedures, "
                              f"{len(result['macros'])} macros, "
                              f"{len(result['functions'])} functions, "
                              f"{len(result['views'])} views")

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

        # Step 2: Remove BTEQ markers and commands
        content = self._remove_bteq_commands(content)

        # Step 3: Remove noise statements
        content = self._remove_noise(content)

        # Step 4: Split by appropriate separator (semicolons for Teradata)
        batches = self._split_by_separator(content)
        self.stats['semicolon_splits'] += len(batches) - 1

        # Step 5: Classify and extract batches
        result = {
            'statements': [],
            'procedures': [],
            'macros': [],
            'functions': [],
            'views': [],
            'triggers': [],
            'volatile_tables': [],
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

            elif classified.batch_type == 'macro':
                result['macros'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number
                })
                self.stats['macros_found'] += 1

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

            elif classified.batch_type == 'trigger':
                result['triggers'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number
                })
                self.stats['triggers_found'] += 1

            else:
                # Regular statements
                statements = self._extract_statements(classified.content)
                result['statements'].extend(statements)

                # Track volatile tables
                volatile_tables = self._extract_volatile_tables(classified.content)
                result['volatile_tables'].extend(volatile_tables)

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

    def _remove_bteq_commands(self, content: str) -> str:
        """Remove BTEQ-specific commands and markers"""
        # Remove BTEQ commands (.LOGON, .RUN FILE, etc.)
        content = self.bteq_command.sub('', content)

        # Remove BT/ET transaction markers (keep actual BEGIN TRANSACTION/END TRANSACTION)
        content = self.bt_marker.sub('', content)
        content = self.et_marker.sub('', content)

        # Remove FastLoad/MultiLoad/TPump markers
        content = self.fastload_marker.sub('', content)
        content = self.multiload_marker.sub('', content)
        content = self.tpump_marker.sub('', content)

        return content

    def _remove_noise(self, content: str) -> str:
        """Remove non-DML/DDL statements specific to Teradata"""
        # DATABASE statements
        content = self.database_stmt.sub('', content)

        # COLLECT STATISTICS statements
        content = self.collect_stats.sub('', content)

        # HELP statements
        content = self.help_stmt.sub('', content)

        # SHOW statements
        content = self.show_stmt.sub('', content)

        # SET SESSION parameters
        content = self.set_session.sub('', content)
        content = self.set_query_band.sub('', content)

        # DIAGNOSTIC and EXPLAIN statements
        content = self.diagnostic_stmt.sub('', content)
        content = self.explain_stmt.sub('', content)

        # Lock statements (preserve for lineage but could be removed if too noisy)
        # content = self.locking_stmt.sub('', content)

        return content

    def _split_by_separator(self, content: str) -> List[str]:
        """Split content by semicolon separator (Teradata batch separator)"""
        # Split by semicolons but be careful with semicolons in procedures/macros/functions
        batches = []
        current_batch = []
        in_object_definition = False
        object_depth = 0

        lines = content.split('\n')

        for line in lines:
            line_upper = line.upper().strip()

            # Check if we're entering an object definition
            if any(pattern in line_upper for pattern in [
                'CREATE PROCEDURE', 'REPLACE PROCEDURE',
                'CREATE MACRO', 'REPLACE MACRO',
                'CREATE FUNCTION', 'REPLACE FUNCTION',
                'CREATE TRIGGER', 'REPLACE TRIGGER'
            ]):
                in_object_definition = True
                object_depth = 0

            # Track BEGIN/END depth in object definitions
            if in_object_definition:
                if line_upper.startswith('BEGIN'):
                    object_depth += 1
                elif line_upper.startswith('END'):
                    object_depth -= 1
                    if object_depth <= 0:
                        in_object_definition = False

            current_batch.append(line)

            # Split on semicolon if not in object definition
            if ';' in line and not in_object_definition:
                batch_text = '\n'.join(current_batch).strip()
                if batch_text:
                    batches.append(batch_text)
                current_batch = []

        # Handle remaining content
        if current_batch:
            batch_text = '\n'.join(current_batch).strip()
            if batch_text:
                batches.append(batch_text)

        return [b for b in batches if b.strip()]

    def _classify_batch(self, batch: str) -> SQLBatch:
        """Classify what type of batch this is"""
        batch_upper = batch.upper().strip()

        # Check for procedures
        proc_match = self.create_proc.search(batch) or self.replace_proc.search(batch)
        if proc_match:
            return SQLBatch(
                content=batch,
                batch_type='procedure',
                object_name=proc_match.group(1).strip('"').strip('`')
            )

        # Check for macros (Teradata-specific)
        macro_match = self.create_macro.search(batch) or self.replace_macro.search(batch)
        if macro_match:
            return SQLBatch(
                content=batch,
                batch_type='macro',
                object_name=macro_match.group(1).strip('"').strip('`')
            )

        # Check for functions
        func_match = self.create_function.search(batch) or self.replace_function.search(batch)
        if func_match:
            return SQLBatch(
                content=batch,
                batch_type='function',
                object_name=func_match.group(1).strip('"').strip('`')
            )

        # Check for views
        view_match = self.create_view.search(batch) or self.replace_view.search(batch)
        if view_match:
            return SQLBatch(
                content=batch,
                batch_type='view',
                object_name=view_match.group(1).strip('"').strip('`')
            )

        # Check for triggers
        trigger_match = self.create_trigger.search(batch) or self.replace_trigger.search(batch)
        if trigger_match:
            return SQLBatch(
                content=batch,
                batch_type='trigger',
                object_name=trigger_match.group(1).strip('"').strip('`')
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

        # Skip variable declarations
        if stmt_upper.startswith('DECLARE'):
            self.stats['declares_skipped'] += 1
            return False

        # Skip SET statements (unless SET table operations)
        if stmt_upper.startswith('SET') and not any(keyword in stmt_upper for keyword in ['SET TABLE', 'SET QUERY_BAND']):
            self.stats['sets_skipped'] += 1
            return False

        # Skip standalone transaction control
        if stmt_upper.startswith(('BEGIN TRAN', 'END TRAN', 'COMMIT', 'ROLLBACK', 'BT', 'ET')):
            self.stats['transactions_skipped'] += 1
            return False

        # Valid statement types for Teradata
        valid_starts = [
            'SELECT', 'SEL',  # SEL is Teradata shorthand for SELECT
            'INSERT', 'INS',  # INS is Teradata shorthand
            'UPDATE', 'UPD',  # UPD is Teradata shorthand
            'DELETE', 'DEL',  # DEL is Teradata shorthand
            'MERGE',
            'CREATE TABLE', 'CREATE MULTISET TABLE', 'CREATE SET TABLE',
            'CREATE VIEW', 'CREATE OR REPLACE', 'CREATE INDEX',
            'CREATE VOLATILE TABLE', 'CREATE GLOBAL TEMPORARY TABLE',
            'ALTER TABLE', 'ALTER VIEW',
            'WITH',  # CTEs
            'DROP', 'TRUNCATE',
            'EXEC', 'EXECUTE', 'CALL',  # Procedure/macro calls
            'LOCK', 'LOCKING'  # Teradata locking
        ]

        is_valid = any(stmt_upper.startswith(start) for start in valid_starts)

        # Handle conditional blocks
        if stmt_upper.startswith('IF'):
            if any(keyword in stmt_upper for keyword in ['CREATE', 'DROP', 'ALTER', 'INSERT', 'UPDATE', 'DELETE', 'SELECT']):
                is_valid = True

        if not is_valid:
            self.stats['invalid_start'] += 1

        return is_valid

    def _detect_function_type(self, content: str) -> str:
        """Detect if function is scalar or table-valued based on RETURNS clause"""
        content_upper = content.upper()

        # Check for RETURNS TABLE (table-valued function)
        if re.search(r'RETURNS\s+TABLE', content_upper):
            return 'TABLE_FUNCTION'

        # Check for RETURNS with a data type (scalar function)
        if re.search(r'RETURNS\s+[\w()]+', content_upper):
            return 'SCALAR_FUNCTION'

        # Default to FUNCTION if we can't determine
        return 'FUNCTION'

    def _detect_macro(self, content: str) -> bool:
        """Detect if content contains a macro definition"""
        return bool(self.create_macro.search(content) or self.replace_macro.search(content))

    def _extract_volatile_tables(self, batch: str) -> List[Dict[str, str]]:
        """Extract volatile table references (Teradata-specific temporary tables)"""
        volatile_tables = []

        # Find all volatile table references
        for match in self.volatile_table.finditer(batch):
            volatile_tables.append({
                'name': match.group(1).strip('"').strip('`'),
                'type': 'volatile'
            })

        return list({t['name']: t for t in volatile_tables}.values())  # Deduplicate

    def _extract_temp_tables(self, batch: str) -> List[Dict[str, str]]:
        """Extract temporary table references"""
        temp_tables = []

        # Find global temporary tables
        for match in self.global_temp_table.finditer(batch):
            temp_tables.append({
                'name': match.group(1).strip('"').strip('`'),
                'type': 'global_temporary'
            })

        return list({t['name']: t for t in temp_tables}.values())  # Deduplicate

    def _print_stats(self):
        """Print cleaning statistics"""
        if self.debug:
            print("\n   Teradata SQL Cleaning Statistics:")
            for key, value in sorted(self.stats.items()):
                print(f"      {key:30s}: {value:6d}")
            print()


# Backwards-compatible alias retained for legacy imports
class EnhancedSQLCleaner(TeradataSQLCleaner):
    """Alias to avoid breaking existing import paths."""
    pass


__all__ = ["SQLBatch", "TeradataSQLCleaner", "EnhancedSQLCleaner"]


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        sql_dir = sys.argv[1]
    else:
        sql_dir = "./sql_files"

    cleaner = TeradataSQLCleaner(sql_dir, debug=True)
    results = cleaner.clean_all_files(max_files=5)

    for file_path, content in results.items():
        print(f"\n{file_path}:")
        print(f"  Statements: {len(content['statements'])}")
        print(f"  Procedures: {len(content['procedures'])}")
        print(f"  Macros: {len(content['macros'])}")
        print(f"  Functions: {len(content['functions'])}")
        print(f"  Views: {len(content['views'])}")
        print(f"  Volatile Tables: {len(content['volatile_tables'])}")
        print(f"  Temp Tables: {len(content['temp_tables'])}")
