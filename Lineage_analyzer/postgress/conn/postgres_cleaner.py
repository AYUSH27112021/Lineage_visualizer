"""
Enhanced PostgreSQL Specific Cleaner
Handles PostgreSQL specific syntax, procedures, functions, and complex patterns
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
    batch_type: str  # 'statement', 'procedure', 'function', 'view', 'trigger', 'materialized_view'
    object_name: Optional[str] = None
    line_number: int = 0


class PostgreSQLCleaner:
    """Enhanced PostgreSQL specific SQL file cleaner with procedure/function awareness"""
    
    def __init__(self, sql_directory: str, debug: bool = False):
        self.sql_directory = Path(sql_directory)
        self.debug = debug
        self.stats = defaultdict(int)
        
        # Compile regex patterns for performance
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile all regex patterns for PostgreSQL"""
        # Comment patterns
        self.multiline_comment = re.compile(r'/\*.*?\*/', re.DOTALL)
        self.single_line_comment = re.compile(r'--[^\n]*')
        
        # PostgreSQL-specific patterns
        # Dollar-quoted strings: $tag$...$tag$ or $$...$$
        self.dollar_quote = re.compile(r'\$\w*\$.*?\$\w*\$', re.DOTALL | re.IGNORECASE)
        
        # Object creation patterns with OR REPLACE support
        self.create_function = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([\w\.]+)',
            re.IGNORECASE
        )
        self.create_procedure = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+([\w\.]+)',
            re.IGNORECASE
        )
        self.create_view = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+([\w\.]+)',
            re.IGNORECASE
        )
        self.create_materialized_view = re.compile(
            r'CREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\.]+)',
            re.IGNORECASE
        )
        self.create_trigger = re.compile(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+([\w\.]+)',
            re.IGNORECASE
        )
        
        # ALTER patterns
        self.alter_function = re.compile(
            r'ALTER\s+FUNCTION\s+([\w\.]+)',
            re.IGNORECASE
        )
        self.alter_procedure = re.compile(
            r'ALTER\s+PROCEDURE\s+([\w\.]+)',
            re.IGNORECASE
        )
        self.alter_view = re.compile(
            r'ALTER\s+VIEW\s+([\w\.]+)',
            re.IGNORECASE
        )
        
        # Noise patterns specific to PostgreSQL
        self.set_statement = re.compile(
            r'SET\s+(?:LOCAL\s+|SESSION\s+)?[\w\.]+\s*(?:=|TO)\s*[^;]+;?',
            re.IGNORECASE
        )
        self.show_statement = re.compile(r'SHOW\s+[\w\.]+\s*;?', re.IGNORECASE)
        self.reset_statement = re.compile(r'RESET\s+[\w\.]+\s*;?', re.IGNORECASE)
        
        # Schema operations
        self.create_schema = re.compile(r'CREATE\s+SCHEMA\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w\.]+\s*;?', re.IGNORECASE)
        self.drop_schema = re.compile(r'DROP\s+SCHEMA\s+(?:IF\s+EXISTS\s+)?[\w\.]+(?:\s+CASCADE)?\s*;?', re.IGNORECASE)
        self.set_search_path = re.compile(r'SET\s+search_path\s+(?:=|TO)\s+[^;]+;?', re.IGNORECASE)
        
        # Extension operations
        self.create_extension = re.compile(r'CREATE\s+EXTENSION\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w]+(?:\s+WITH\s+SCHEMA\s+[\w]+)?\s*;?', re.IGNORECASE)
        self.drop_extension = re.compile(r'DROP\s+EXTENSION\s+(?:IF\s+EXISTS\s+)?[\w]+(?:\s+CASCADE)?\s*;?', re.IGNORECASE)
        
        # Transaction control
        self.begin_transaction = re.compile(r'BEGIN\s*(?:TRANSACTION|WORK)?\s*;?', re.IGNORECASE)
        self.commit_transaction = re.compile(r'COMMIT\s*(?:TRANSACTION|WORK)?\s*;?', re.IGNORECASE)
        self.rollback_transaction = re.compile(r'ROLLBACK\s*(?:TRANSACTION|WORK)?(?:\s+TO\s+SAVEPOINT\s+\w+)?\s*;?', re.IGNORECASE)
        self.savepoint = re.compile(r'SAVEPOINT\s+\w+\s*;?', re.IGNORECASE)
        
        # Vacuum and analyze
        self.vacuum_statement = re.compile(r'VACUUM\s+(?:FULL\s+|ANALYZE\s+)?[^;]*;?', re.IGNORECASE)
        self.analyze_statement = re.compile(r'ANALYZE\s+[^;]*;?', re.IGNORECASE)
        
        # COPY statements
        self.copy_statement = re.compile(r'COPY\s+.*?FROM\s+.*?;', re.IGNORECASE | re.DOTALL)
        
        # LISTEN/NOTIFY
        self.listen_statement = re.compile(r'LISTEN\s+[\w]+\s*;?', re.IGNORECASE)
        self.notify_statement = re.compile(r'NOTIFY\s+[\w]+(?:\s*,\s*[^;]+)?\s*;?', re.IGNORECASE)
        
        # PostgreSQL specific blocks
        self.do_block = re.compile(r'DO\s+\$\$.*?\$\$\s*;?', re.IGNORECASE | re.DOTALL)
        
        # Temp table patterns (PostgreSQL uses TEMP or TEMPORARY)
        self.temp_table_create = re.compile(r'CREATE\s+(?:TEMP|TEMPORARY)\s+TABLE', re.IGNORECASE)
        
        # CTE patterns
        self.with_clause = re.compile(r'WITH\s+(?:RECURSIVE\s+)?', re.IGNORECASE)
    
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
        
        # Step 1: Extract and preserve dollar-quoted strings
        dollar_quotes, content = self._extract_dollar_quotes(content)
        
        # Step 2: Remove comments
        content = self._remove_comments(content)
        self.stats['comments_removed'] += 1
        
        # Step 3: Restore dollar-quoted strings
        content = self._restore_dollar_quotes(content, dollar_quotes)
        
        # Step 4: Remove noise statements
        content = self._remove_noise(content)
        
        # Step 5: Split into logical batches (PostgreSQL doesn't have GO, uses semicolons)
        batches = self._split_into_batches(content)
        
        # Step 6: Classify and extract batches
        result = {
            'statements': [],
            'procedures': [],
            'functions': [],
            'views': [],
            'materialized_views': [],
            'triggers': [],
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
                result['functions'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number
                })
                self.stats['functions_found'] += 1
            
            elif classified.batch_type == 'view':
                result['views'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number
                })
                self.stats['views_found'] += 1
            
            elif classified.batch_type == 'materialized_view':
                result['materialized_views'].append({
                    'name': classified.object_name,
                    'content': classified.content,
                    'line_number': classified.line_number
                })
                self.stats['materialized_views_found'] += 1
            
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
                
                # Track temp tables
                if self.temp_table_create.search(classified.content):
                    temp_tables = self._extract_temp_tables(classified.content)
                    result['temp_tables'].extend(temp_tables)
        
        return result
    
    def _extract_dollar_quotes(self, content: str) -> Tuple[Dict[str, str], str]:
        """Extract dollar-quoted strings and replace with placeholders"""
        dollar_quotes = {}
        counter = 0
        
        def replace_quote(match):
            nonlocal counter
            placeholder = f"__DOLLAR_QUOTE_{counter}__"
            dollar_quotes[placeholder] = match.group(0)
            counter += 1
            return placeholder
        
        content = self.dollar_quote.sub(replace_quote, content)
        return dollar_quotes, content
    
    def _restore_dollar_quotes(self, content: str, dollar_quotes: Dict[str, str]) -> str:
        """Restore dollar-quoted strings"""
        for placeholder, original in dollar_quotes.items():
            content = content.replace(placeholder, original)
        return content
    
    def _remove_comments(self, content: str) -> str:
        """Remove SQL comments while preserving string literals"""
        # Remove multiline comments
        content = self.multiline_comment.sub('', content)
        # Remove single line comments
        content = self.single_line_comment.sub('', content)
        return content
    
    def _remove_noise(self, content: str) -> str:
        """Remove PostgreSQL noise patterns"""
        # SET statements
        content = self.set_statement.sub('', content)
        content = self.show_statement.sub('', content)
        content = self.reset_statement.sub('', content)
        content = self.set_search_path.sub('', content)
        
        # Extension operations
        content = self.create_extension.sub('', content)
        content = self.drop_extension.sub('', content)
        
        # Transaction control
        content = self.begin_transaction.sub('', content)
        content = self.commit_transaction.sub('', content)
        content = self.rollback_transaction.sub('', content)
        content = self.savepoint.sub('', content)
        
        # Vacuum and analyze
        content = self.vacuum_statement.sub('', content)
        content = self.analyze_statement.sub('', content)
        
        # LISTEN/NOTIFY
        content = self.listen_statement.sub('', content)
        content = self.notify_statement.sub('', content)
        
        return content
    
    def _split_into_batches(self, content: str) -> List[str]:
        """Split content into logical batches (PostgreSQL uses semicolons, not GO)"""
        batches = []
        current_batch = []
        in_function = False
        in_do_block = False
        dollar_depth = 0
        
        lines = content.split('\n')
        
        for line in lines:
            stripped = line.strip().upper()
            
            # Detect function/procedure start
            if any(pattern in stripped for pattern in [
                'CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION',
                'CREATE PROCEDURE', 'CREATE OR REPLACE PROCEDURE',
                'CREATE TRIGGER', 'CREATE OR REPLACE TRIGGER'
            ]):
                if current_batch and not in_function:
                    batches.append('\n'.join(current_batch))
                    current_batch = []
                in_function = True
                dollar_depth = 0
            
            # Detect DO block
            if 'DO $$' in stripped or 'DO $' in stripped:
                if current_batch and not in_do_block:
                    batches.append('\n'.join(current_batch))
                    current_batch = []
                in_do_block = True
                dollar_depth = 0
            
            current_batch.append(line)
            
            # Track dollar quotes for function bodies
            if '$$' in line:
                dollar_depth += line.count('$$')
                # If we have even number of $$, the block is closed
                if dollar_depth >= 2 and (in_function or in_do_block):
                    in_function = False
                    in_do_block = False
                    batches.append('\n'.join(current_batch))
                    current_batch = []
                    dollar_depth = 0
            
            # Regular statement ending
            if not in_function and not in_do_block and line.strip().endswith(';'):
                batches.append('\n'.join(current_batch))
                current_batch = []
        
        # Add remaining content
        if current_batch:
            batches.append('\n'.join(current_batch))
        
        return [b.strip() for b in batches if b.strip()]
    
    def _classify_batch(self, batch: str) -> SQLBatch:
        """Classify what type of batch this is"""
        # Check for functions
        func_match = self.create_function.search(batch) or self.alter_function.search(batch)
        if func_match:
            return SQLBatch(
                content=batch,
                batch_type='function',
                object_name=func_match.group(1).strip('"')
            )
        
        # Check for procedures
        proc_match = self.create_procedure.search(batch) or self.alter_procedure.search(batch)
        if proc_match:
            return SQLBatch(
                content=batch,
                batch_type='procedure',
                object_name=proc_match.group(1).strip('"')
            )
        
        # Check for materialized views
        mat_view_match = self.create_materialized_view.search(batch)
        if mat_view_match:
            return SQLBatch(
                content=batch,
                batch_type='materialized_view',
                object_name=mat_view_match.group(1).strip('"')
            )
        
        # Check for views
        view_match = self.create_view.search(batch) or self.alter_view.search(batch)
        if view_match:
            return SQLBatch(
                content=batch,
                batch_type='view',
                object_name=view_match.group(1).strip('"')
            )
        
        # Check for triggers
        trigger_match = self.create_trigger.search(batch)
        if trigger_match:
            return SQLBatch(
                content=batch,
                batch_type='trigger',
                object_name=trigger_match.group(1).strip('"')
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
        in_dollar_quote = False
        dollar_tag = None
        paren_depth = 0
        
        lines = batch.split('\n')
        
        for line in lines:
            stripped = line.strip()
            
            if not stripped:
                continue
            
            # Track dollar quotes
            i = 0
            while i < len(line):
                char = line[i]
                
                if char == '$' and not in_string:
                    # Check for dollar quote start/end
                    if not in_dollar_quote:
                        # Find the tag
                        end_idx = i + 1
                        while end_idx < len(line) and (line[end_idx].isalnum() or line[end_idx] == '_'):
                            end_idx += 1
                        if end_idx < len(line) and line[end_idx] == '$':
                            dollar_tag = line[i:end_idx + 1]
                            in_dollar_quote = True
                            i = end_idx
                    elif dollar_tag and line[i:i+len(dollar_tag)] == dollar_tag:
                        in_dollar_quote = False
                        dollar_tag = None
                        i += len(dollar_tag) - 1
                
                # Track string literals (when not in dollar quote)
                if not in_dollar_quote:
                    if char in ('"', "'") and not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char and in_string:
                        # Check for escaped quotes
                        if i + 1 < len(line) and line[i + 1] == string_char:
                            i += 1
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
            if self._is_statement_complete(stripped, in_string, in_dollar_quote, paren_depth):
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
    
    def _is_statement_complete(self, line: str, in_string: bool, in_dollar_quote: bool, paren_depth: int) -> bool:
        """Check if statement is complete"""
        if in_string or in_dollar_quote or paren_depth > 0:
            return False
        
        return line.endswith(';')
    
    def _is_valid_statement(self, stmt: str) -> bool:
        """Check if statement should be processed"""
        if not stmt or len(stmt) < 10:
            return False
        
        stmt_upper = stmt.upper().strip()
        
        # Skip standalone transaction control
        if stmt_upper.startswith(('BEGIN;', 'COMMIT;', 'ROLLBACK;', 'SAVEPOINT')):
            self.stats['transactions_skipped'] += 1
            return False
        
        # Skip SET statements
        if stmt_upper.startswith('SET '):
            self.stats['sets_skipped'] += 1
            return False
        
        # Valid statement types
        valid_starts = [
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE',
            'CREATE TABLE', 'CREATE TEMP', 'CREATE TEMPORARY', 
            'CREATE OR REPLACE VIEW', 'CREATE VIEW', 'CREATE MATERIALIZED VIEW',
            'CREATE INDEX', 'CREATE UNIQUE INDEX',
            'ALTER TABLE', 'ALTER VIEW',
            'WITH',  # CTEs
            'DROP', 'TRUNCATE',
            'COPY',
            'DO'  # DO blocks
        ]
        
        is_valid = any(stmt_upper.startswith(start) for start in valid_starts)
        
        if not is_valid:
            self.stats['invalid_start'] += 1
        
        return is_valid
    
    def _extract_temp_tables(self, batch: str) -> List[Dict[str, str]]:
        """Extract temp table references from CREATE TEMP TABLE statements"""
        temp_tables = []
        
        # PostgreSQL temp tables: CREATE TEMP TABLE name or CREATE TEMPORARY TABLE name
        pattern = re.compile(r'CREATE\s+(?:TEMP|TEMPORARY)\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\.]+)', re.IGNORECASE)
        
        for match in pattern.finditer(batch):
            temp_tables.append({
                'name': match.group(1).strip('"'),
                'type': 'temporary'
            })
        
        return list({t['name']: t for t in temp_tables}.values())  # Deduplicate
    
    def _print_stats(self):
        """Print cleaning statistics"""
        if self.debug:
            print("\n   Cleaning Statistics:")
            for key, value in sorted(self.stats.items()):
                print(f"      {key:30s}: {value:6d}")
            print()


if __name__ == "__main__":
    cleaner = PostgreSQLCleaner("./sql_files", debug=True)
    results = cleaner.clean_all_files(max_files=5)
    
    for file_path, content in results.items():
        print(f"\n{file_path}:")
        print(f"  Statements: {len(content['statements'])}")
        print(f"  Procedures: {len(content['procedures'])}")
        print(f"  Functions: {len(content['functions'])}")
        print(f"  Views: {len(content['views'])}")
        print(f"  Materialized Views: {len(content['materialized_views'])}")
