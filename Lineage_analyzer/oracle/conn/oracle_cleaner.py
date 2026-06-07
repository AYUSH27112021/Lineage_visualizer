"""
Enhanced Oracle-Specific SQL Cleaner
Handles Oracle-specific syntax, PL/SQL blocks, packages, procedures, functions, and complex patterns
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
    batch_type: str  # 'statement', 'procedure', 'function', 'package', 'view', 'trigger'
    object_name: Optional[str] = None
    line_number: int = 0


class OracleSQLCleaner:
    """Enhanced Oracle-specific SQL file cleaner with PL/SQL awareness"""

    def __init__(self, sql_directory: str, debug: bool = False):
        self.sql_directory = Path(sql_directory)
        self.debug = debug
        self.stats = defaultdict(int)

        # Compile regex patterns for performance
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile all Oracle-specific regex patterns"""
        # Comment patterns
        self.multiline_comment = re.compile(r'/\*.*?\*/', re.DOTALL)
        self.single_line_comment = re.compile(r'--[^\n]*')

        # Oracle batch separator (slash on its own line or semicolon)
        self.slash_separator = re.compile(r'^\s*/\s*$', re.MULTILINE)
        self.semicolon_separator = re.compile(r';')

        # SQL*Plus commands to remove
        self.sqlplus_command = re.compile(
            r'^\s*(?:SET|SHOW|SPOOL|COLUMN|DEFINE|WHENEVER|PROMPT|ACCEPT|PAUSE|CLEAR|BREAK|COMPUTE|TTITLE|BTITLE|REPFOOTER|REPHEADER|HOST|START|@|@@)\s+.*$',
            re.IGNORECASE | re.MULTILINE
        )

        # Oracle PACKAGE patterns
        self.create_package_spec = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+([\w\.\"\`]+)(?:\s+(?:AUTHID\s+(?:CURRENT_USER|DEFINER)))?\s+(?:IS|AS)',
            re.IGNORECASE
        )
        self.create_package_body = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+BODY\s+([\w\.\"\`]+)\s+(?:IS|AS)',
            re.IGNORECASE
        )

        # Oracle PROCEDURE patterns
        self.create_proc = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Oracle FUNCTION patterns
        self.create_function = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Oracle TYPE patterns (object types)
        self.create_type = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?TYPE\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )
        self.create_type_body = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?TYPE\s+BODY\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Oracle VIEW patterns
        self.create_view = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:FORCE\s+)?VIEW\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Oracle MATERIALIZED VIEW patterns
        self.create_mview = re.compile(
            r'CREATE\s+MATERIALIZED\s+VIEW\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Oracle TRIGGER patterns
        self.create_trigger = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Oracle temp table patterns
        # GLOBAL TEMPORARY tables
        self.global_temp_table = re.compile(
            r'CREATE\s+GLOBAL\s+TEMPORARY\s+TABLE\s+([\w\.\"\`]+)',
            re.IGNORECASE
        )

        # Oracle-specific noise patterns to remove
        self.alter_session = re.compile(r'ALTER\s+SESSION\s+.*?;', re.IGNORECASE | re.DOTALL)
        self.analyze_stmt = re.compile(r'ANALYZE\s+(?:TABLE|INDEX|CLUSTER)\s+.*?;', re.IGNORECASE | re.DOTALL)
        self.grant_stmt = re.compile(r'GRANT\s+.*?;', re.IGNORECASE | re.DOTALL)
        self.revoke_stmt = re.compile(r'REVOKE\s+.*?;', re.IGNORECASE | re.DOTALL)

        # Oracle explain plan
        self.explain_plan = re.compile(r'EXPLAIN\s+PLAN\s+.*?;', re.IGNORECASE | re.DOTALL)

        # Oracle transaction control
        self.commit_trans = re.compile(r'COMMIT\s*(?:WORK)?\s*;?', re.IGNORECASE)
        self.rollback_trans = re.compile(r'ROLLBACK\s*(?:WORK)?\s*(?:TO\s+SAVEPOINT\s+[\w]+)?\s*;?', re.IGNORECASE)
        self.savepoint_trans = re.compile(r'SAVEPOINT\s+[\w]+\s*;?', re.IGNORECASE)

        # Oracle PL/SQL block markers
        self.plsql_block_begin = re.compile(r'\bBEGIN\b', re.IGNORECASE)
        self.plsql_block_end = re.compile(r'\bEND\s*;', re.IGNORECASE)
        self.plsql_declare = re.compile(r'\bDECLARE\b', re.IGNORECASE)

        # Oracle MERGE statement
        self.merge_stmt = re.compile(r'\bMERGE\s+INTO\b', re.IGNORECASE)

        # Oracle SELECT FOR UPDATE
        self.select_for_update = re.compile(r'\bFOR\s+UPDATE\b', re.IGNORECASE)

        # Oracle CONNECT BY (hierarchical queries)
        self.connect_by = re.compile(r'\bCONNECT\s+BY\b', re.IGNORECASE)

        # Oracle PIVOT/UNPIVOT
        self.pivot_stmt = re.compile(r'\b(?:PIVOT|UNPIVOT)\b', re.IGNORECASE)

        # Oracle MODEL clause
        self.model_clause = re.compile(r'\bMODEL\b', re.IGNORECASE)

        # Oracle Flashback queries
        self.flashback_query = re.compile(r'\bAS\s+OF\s+(?:SCN|TIMESTAMP)\b', re.IGNORECASE)
        self.versions_between = re.compile(r'\bVERSIONS\s+BETWEEN\b', re.IGNORECASE)

        # Oracle external table
        self.external_table = re.compile(r'CREATE\s+TABLE\s+[\w\.\"\`]+\s+.*?\bORGANIZATION\s+EXTERNAL\b', re.IGNORECASE | re.DOTALL)

        # Oracle database link reference
        self.db_link = re.compile(r'@[\w\.\-]+', re.IGNORECASE)

    def clean_sql(self, content: str) -> Dict[str, List]:
        """
        Clean SQL content and return structured dict (matching T-SQL format)

        Args:
            content: SQL content string

        Returns:
            Dict with keys: statements, procedures, functions, views, triggers, packages, temp_tables
        """
        # Remove comments
        content = self._remove_comments(content)

        # Remove SQL*Plus commands
        content = self.sqlplus_command.sub('', content)

        # Remove transaction control statements
        content = self.commit_trans.sub('', content)
        content = self.rollback_trans.sub('', content)
        content = self.savepoint_trans.sub('', content)

        # Remove noise statements
        content = self.alter_session.sub('', content)
        content = self.analyze_stmt.sub('', content)
        content = self.grant_stmt.sub('', content)
        content = self.revoke_stmt.sub('', content)
        content = self.explain_plan.sub('', content)

        # Split into batches
        batches = self._split_into_batches(content)

        # Categorize batches (like T-SQL cleaner)
        result = {
            'statements': [],
            'procedures': [],
            'functions': [],
            'views': [],
            'triggers': [],
            'packages': [],
            'temp_tables': []
        }

        for batch in batches:
            cleaned = self._clean_batch(batch)
            if not cleaned or len(cleaned.strip()) <= 10:
                continue

            # Categorize by batch type
            if batch.batch_type == 'procedure':
                result['procedures'].append({
                    'name': batch.object_name or 'unnamed_procedure',
                    'content': cleaned,
                    'line_number': batch.line_number
                })
                self.stats['procedures_found'] = self.stats.get('procedures_found', 0) + 1

            elif batch.batch_type == 'function':
                result['functions'].append({
                    'name': batch.object_name or 'unnamed_function',
                    'content': cleaned,
                    'line_number': batch.line_number,
                    'type': 'FUNCTION'
                })
                self.stats['functions_found'] = self.stats.get('functions_found', 0) + 1

            elif batch.batch_type == 'view':
                result['views'].append({
                    'name': batch.object_name or 'unnamed_view',
                    'content': cleaned,
                    'line_number': batch.line_number
                })
                self.stats['views_found'] = self.stats.get('views_found', 0) + 1

            elif batch.batch_type == 'trigger':
                result['triggers'].append({
                    'name': batch.object_name or 'unnamed_trigger',
                    'content': cleaned,
                    'line_number': batch.line_number
                })
                self.stats['triggers_found'] = self.stats.get('triggers_found', 0) + 1

            elif batch.batch_type in ['package', 'package_body']:
                result['packages'].append({
                    'name': batch.object_name or 'unnamed_package',
                    'content': cleaned,
                    'line_number': batch.line_number,
                    'package_type': batch.batch_type
                })
                self.stats['packages_found'] = self.stats.get('packages_found', 0) + 1

            else:
                # Regular statement
                result['statements'].append(cleaned)
                self.stats['statements_extracted'] += 1

        return result

    def clean_sql_file(self, file_path: Path) -> List[str]:
        """
        Clean a single SQL file and return list of statements

        Args:
            file_path: Path to SQL file

        Returns:
            List of cleaned SQL statements
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            if self.debug:
                print(f"Error reading {file_path}: {e}")
            self.stats['file_errors'] += 1
            return []

        self.stats['files_processed'] += 1
        return self.clean_sql(content)

    def _remove_comments(self, content: str) -> str:
        """Remove SQL comments"""
        # Remove multiline comments
        content = self.multiline_comment.sub('', content)
        # Remove single-line comments
        content = self.single_line_comment.sub('', content)
        return content

    def _split_into_batches(self, content: str) -> List[SQLBatch]:
        """
        Split content into batches based on Oracle delimiters

        Oracle uses:
        - Semicolon (;) for single SQL statements
        - Slash (/) on its own line for PL/SQL blocks, packages, procedures, functions
        """
        batches = []

        # First, try to identify complete PL/SQL blocks (CREATE PROCEDURE, PACKAGE, etc.)
        plsql_objects = self._extract_plsql_objects(content)

        # Add PL/SQL objects
        batches.extend(plsql_objects)

        # Extract remaining statements (tables, inserts, etc.) that aren't part of PL/SQL objects
        remaining_content = content
        for plsql_obj in plsql_objects:
            remaining_content = remaining_content.replace(plsql_obj.content, '')

        # Split remaining content by semicolon
        if remaining_content.strip():
            statements = remaining_content.split(';')
            for stmt in statements:
                stmt = stmt.strip()
                if stmt and len(stmt) > 10:  # Min length filter
                    batch_type, obj_name = self._get_object_info(stmt)
                    batches.append(SQLBatch(
                        content=stmt + ';',
                        batch_type=batch_type if batch_type != 'statement' else 'statement',
                        object_name=obj_name,
                        line_number=content[:content.find(stmt)].count('\n') + 1 if stmt in content else 0
                    ))

        return batches

    def _find_statement_end(self, content: str, start_pos: int) -> int:
        """Find the end of a SQL statement (next semicolon outside of parentheses/strings)"""
        paren_depth = 0
        in_string = False
        string_char = None

        i = start_pos
        while i < len(content):
            char = content[i]

            # Handle string literals
            if char in ("'", '"') and (i == 0 or content[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None

            # Track parentheses depth (only outside strings)
            elif not in_string:
                if char == '(':
                    paren_depth += 1
                elif char == ')':
                    paren_depth -= 1
                elif char == ';' and paren_depth == 0:
                    return i + 1  # Include the semicolon

            i += 1

        # If we didn't find an ending semicolon, return end of content
        return len(content)

    def _extract_plsql_objects(self, content: str) -> List[SQLBatch]:
        """Extract complete PL/SQL objects (packages, procedures, functions)"""
        batches = []

        # Pattern to match CREATE OR REPLACE ... END; blocks
        plsql_patterns = [
            (self.create_package_spec, 'package'),
            (self.create_package_body, 'package_body'),
            (self.create_proc, 'procedure'),
            (self.create_function, 'function'),
            (self.create_trigger, 'trigger'),
            (self.create_view, 'view'),
            (self.create_mview, 'materialized_view'),
            (self.create_type, 'type'),
            (self.create_type_body, 'type_body'),
        ]

        for pattern, obj_type in plsql_patterns:
            matches = pattern.finditer(content)
            for match in matches:
                obj_name = match.group(1)
                start_pos = match.start()

                # Find the end of this object
                # Views/MVs end with semicolon, procedures/functions end with END;
                if obj_type in ['view', 'materialized_view']:
                    # For views, find the next semicolon that's not inside parentheses
                    end_pos = self._find_statement_end(content, start_pos)
                else:
                    # For procedures/functions/triggers, look for END;
                    end_pattern = re.compile(
                        rf'\bEND\s+(?:{re.escape(obj_name)})?\s*;',
                        re.IGNORECASE
                    )
                    end_match = end_pattern.search(content, start_pos)
                    if end_match:
                        end_pos = end_match.end()
                    else:
                        continue  # Skip if we can't find the end

                obj_content = content[start_pos:end_pos].strip()

                batches.append(SQLBatch(
                    content=obj_content,
                    batch_type=obj_type,
                    object_name=obj_name,
                    line_number=content[:start_pos].count('\n') + 1
                ))

        # Sort by line number to maintain order
        batches.sort(key=lambda x: x.line_number)

        return batches

    def _is_plsql_object(self, content: str) -> bool:
        """Check if content is a PL/SQL object"""
        return bool(
            self.create_package_spec.search(content) or
            self.create_package_body.search(content) or
            self.create_proc.search(content) or
            self.create_function.search(content) or
            self.create_trigger.search(content) or
            self.create_type.search(content) or
            self.create_type_body.search(content)
        )

    def _get_object_info(self, content: str) -> Tuple[str, Optional[str]]:
        """Get object type and name from content"""
        patterns = [
            (self.create_package_spec, 'package'),
            (self.create_package_body, 'package_body'),
            (self.create_proc, 'procedure'),
            (self.create_function, 'function'),
            (self.create_trigger, 'trigger'),
            (self.create_view, 'view'),
            (self.create_mview, 'materialized_view'),
            (self.create_type, 'type'),
            (self.create_type_body, 'type_body'),
        ]

        for pattern, obj_type in patterns:
            match = pattern.search(content)
            if match:
                obj_name = match.group(1)
                return obj_type, obj_name

        return 'statement', None

    def _clean_batch(self, batch: SQLBatch) -> str:
        """Clean individual batch"""
        content = batch.content.strip()

        if not content:
            return ""

        # Normalize whitespace
        content = re.sub(r'\s+', ' ', content)

        # Remove trailing semicolon if present (we'll add it back)
        content = content.rstrip(';').strip()

        # Ensure statement ends with semicolon
        if not content.endswith(';'):
            content += ';'

        return content

    def clean_all_files(self, max_files: int = None) -> Dict[str, List[str]]:
        """
        Clean all SQL files in the directory

        Args:
            max_files: Maximum number of files to process (None = all files)

        Returns:
            Dictionary mapping file paths to lists of cleaned statements
        """
        results = {}

        if not self.sql_directory.exists():
            if self.debug:
                print(f"Directory not found: {self.sql_directory}")
            return results

        # Find all SQL files
        sql_files = list(self.sql_directory.rglob('*.sql'))
        sql_files.extend(self.sql_directory.rglob('*.pls'))  # PL/SQL files
        sql_files.extend(self.sql_directory.rglob('*.pkb'))  # Package bodies
        sql_files.extend(self.sql_directory.rglob('*.pks'))  # Package specs

        # Limit files if max_files is specified
        if max_files is not None and max_files > 0:
            sql_files = sql_files[:max_files]

        if self.debug:
            print(f"Found {len(sql_files)} SQL files")

        for file_path in sql_files:
            if self.debug:
                print(f"Processing: {file_path}")

            statements = self.clean_sql_file(file_path)
            if statements:
                results[str(file_path)] = statements

        return results

    def get_stats(self) -> Dict[str, int]:
        """Get cleaning statistics"""
        return dict(self.stats)


def clean_oracle_sql_directory(
    sql_directory: str,
    output_file: Optional[str] = None,
    debug: bool = False
) -> Dict[str, List[str]]:
    """
    Convenience function to clean Oracle SQL directory

    Args:
        sql_directory: Path to directory containing SQL files
        output_file: Optional JSON file to save results
        debug: Enable debug output

    Returns:
        Dictionary mapping file paths to cleaned statements
    """
    cleaner = OracleSQLCleaner(sql_directory, debug=debug)
    results = cleaner.clean_all_files()

    if debug:
        stats = cleaner.get_stats()
        print("\nCleaning Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")

    if output_file:
        import json
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        if debug:
            print(f"\nResults saved to: {output_file}")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python oracle_cleaner.py <sql_directory> [output_file]")
        sys.exit(1)

    sql_dir = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else None

    results = clean_oracle_sql_directory(sql_dir, output, debug=True)
    print(f"\nProcessed {len(results)} files")
