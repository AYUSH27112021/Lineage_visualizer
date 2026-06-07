"""
Enhanced T-SQL Specific Cleaner
Handles SQL Server specific syntax, batch separators, procedures, functions, and complex patterns
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
    batch_type: str  # 'statement', 'procedure', 'function', 'view', 'trigger'
    object_name: Optional[str] = None
    line_number: int = 0


class EnhancedSQLCleaner:
    """Enhanced T-SQL specific SQL file cleaner with procedure/function awareness"""
    
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
        
        # T-SQL specific patterns
        self.go_separator = re.compile(r'^\s*GO\s*(?:\d+)?\s*$', re.IGNORECASE | re.MULTILINE)
        self.exec_dynamic = re.compile(r'EXEC(?:UTE)?\s*\(', re.IGNORECASE)
        self.sp_executesql = re.compile(r'sp_executesql\s+', re.IGNORECASE)
        
        # Object creation patterns
        self.create_proc = re.compile(
            r'CREATE\s+(?:OR\s+ALTER\s+)?(?:PROCEDURE|PROC)\s+(\[?[\w\.\[\]]+\]?)',
            re.IGNORECASE
        )
        self.alter_proc = re.compile(
            r'ALTER\s+(?:PROCEDURE|PROC)\s+(\[?[\w\.\[\]]+\]?)',
            re.IGNORECASE
        )
        self.create_function = re.compile(
            r'CREATE\s+(?:OR\s+ALTER\s+)?FUNCTION\s+(\[?[\w\.\[\]]+\]?)',
            re.IGNORECASE
        )
        self.alter_function = re.compile(
            r'ALTER\s+FUNCTION\s+(\[?[\w\.\[\]]+\]?)',
            re.IGNORECASE
        )
        self.create_view = re.compile(
            r'CREATE\s+(?:OR\s+ALTER\s+)?VIEW\s+(\[?[\w\.\[\]]+\]?)',
            re.IGNORECASE
        )
        self.alter_view = re.compile(
            r'ALTER\s+VIEW\s+(\[?[\w\.\[\]]+\]?)',
            re.IGNORECASE
        )
        self.create_trigger = re.compile(
            r'CREATE\s+(?:OR\s+ALTER\s+)?TRIGGER\s+(\[?[\w\.\[\]]+\]?)',
            re.IGNORECASE
        )
        
        # Noise patterns
        self.use_database = re.compile(r'USE\s+\[?\w+\]?\s*;?', re.IGNORECASE)
        self.set_nocount = re.compile(r'SET\s+NOCOUNT\s+(ON|OFF)\s*;?', re.IGNORECASE)
        self.set_ansi = re.compile(r'SET\s+ANSI_\w+\s+(ON|OFF)\s*;?', re.IGNORECASE)
        self.set_quoted = re.compile(r'SET\s+QUOTED_IDENTIFIER\s+(ON|OFF)\s*;?', re.IGNORECASE)
        self.print_statement = re.compile(r'PRINT\s+[^\n]+', re.IGNORECASE)
        
        # Transaction control
        self.begin_tran = re.compile(r'BEGIN\s+(TRAN|TRANSACTION)\s*[\w@]*\s*;?', re.IGNORECASE)
        self.commit_tran = re.compile(r'COMMIT\s+(TRAN|TRANSACTION)?\s*[\w@]*\s*;?', re.IGNORECASE)
        self.rollback_tran = re.compile(r'ROLLBACK\s+(TRAN|TRANSACTION)?\s*[\w@]*\s*;?', re.IGNORECASE)
        self.save_tran = re.compile(r'SAVE\s+(TRAN|TRANSACTION)\s+[\w@]+\s*;?', re.IGNORECASE)
        
        # Error handling
        self.try_catch = re.compile(r'BEGIN\s+TRY.*?END\s+CATCH', re.IGNORECASE | re.DOTALL)
        self.raiserror = re.compile(r'RAISERROR\s*\([^)]+\)', re.IGNORECASE)
        
        # Conditional blocks
        self.if_exists = re.compile(r'IF\s+(?:NOT\s+)?EXISTS\s*\(', re.IGNORECASE)
        self.if_object_id = re.compile(r'IF\s+OBJECT_ID\s*\(', re.IGNORECASE)
        
        # Temp table patterns
        self.temp_table = re.compile(r'#[\w]+')
        self.global_temp = re.compile(r'##[\w]+')
        
        # Table variable patterns
        self.table_variable = re.compile(r'DECLARE\s+@\w+\s+TABLE', re.IGNORECASE)
    
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
        
        # Step 2: Remove noise statements (but preserve them for context in procedures)
        original_content = content
        content = self._remove_noise(content)
        
        # Step 3: Split by GO statements
        batches = self._split_by_go(content)
        self.stats['go_splits'] += len(batches) - 1
        
        # Step 4: Classify and extract batches
        result = {
            'statements': [],
            'procedures': [],
            'functions': [],
            'views': [],
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
        # USE database
        content = self.use_database.sub('', content)
        
        # SET statements (except important ones)
        content = self.set_nocount.sub('', content)
        content = self.set_ansi.sub('', content)
        content = self.set_quoted.sub('', content)
        
        # PRINT statements
        content = self.print_statement.sub('', content)
        
        # Transaction control (keep BEGIN/COMMIT in procedures, remove standalone)
        # content = self.begin_tran.sub('', content)
        # content = self.commit_tran.sub('', content)
        # content = self.rollback_tran.sub('', content)
        
        return content
    
    def _split_by_go(self, content: str) -> List[str]:
        """Split content by GO batch separator"""
        batches = self.go_separator.split(content)
        return [b.strip() for b in batches if b.strip()]
    
    def _classify_batch(self, batch: str) -> SQLBatch:
        """Classify what type of batch this is"""
        batch_upper = batch.upper().strip()
        
        # Check for procedures
        proc_match = self.create_proc.search(batch) or self.alter_proc.search(batch)
        if proc_match:
            return SQLBatch(
                content=batch,
                batch_type='procedure',
                object_name=proc_match.group(1).strip('[]')
            )
        
        # Check for functions
        func_match = self.create_function.search(batch) or self.alter_function.search(batch)
        if func_match:
            return SQLBatch(
                content=batch,
                batch_type='function',
                object_name=func_match.group(1).strip('[]')
            )
        
        # Check for views
        view_match = self.create_view.search(batch) or self.alter_view.search(batch)
        if view_match:
            return SQLBatch(
                content=batch,
                batch_type='view',
                object_name=view_match.group(1).strip('[]')
            )
        
        # Check for triggers
        trigger_match = self.create_trigger.search(batch)
        if trigger_match:
            return SQLBatch(
                content=batch,
                batch_type='trigger',
                object_name=trigger_match.group(1).strip('[]')
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
        bracket_depth = 0
        
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
                    elif char == '[':
                        bracket_depth += 1
                    elif char == ']':
                        bracket_depth -= 1
                
                i += 1
            
            current.append(line)
            
            # Check if statement is complete
            if self._is_statement_complete(stripped, in_string, paren_depth, bracket_depth):
                stmt = '\n'.join(current).strip()
                if self._is_valid_statement(stmt):
                    statements.append(stmt)
                    self.stats['statements_extracted'] += 1
                current = []
                paren_depth = 0
                bracket_depth = 0
        
        # Handle remaining content
        if current:
            stmt = '\n'.join(current).strip()
            if self._is_valid_statement(stmt):
                statements.append(stmt)
                self.stats['statements_extracted'] += 1
        
        return statements
    
    def _is_statement_complete(self, line: str, in_string: bool, paren_depth: int, bracket_depth: int) -> bool:
        """Check if statement is complete"""
        if in_string or paren_depth > 0 or bracket_depth > 0:
            return False
        
        return line.endswith(';')
    
    def _is_valid_statement(self, stmt: str) -> bool:
        """Check if statement should be processed"""
        if not stmt or len(stmt) < 10:
            return False
        
        stmt_upper = stmt.upper().strip()
        
        # Skip variable declarations (unless table variables)
        if stmt_upper.startswith('DECLARE'):
            if 'TABLE' in stmt_upper:
                return True  # Table variable
            self.stats['declares_skipped'] += 1
            return False
        
        # Skip SET statements (unless SET IDENTITY_INSERT)
        if stmt_upper.startswith('SET') and 'IDENTITY_INSERT' not in stmt_upper:
            self.stats['sets_skipped'] += 1
            return False
        
        # Skip standalone transaction control
        if stmt_upper.startswith(('BEGIN TRAN', 'COMMIT', 'ROLLBACK', 'SAVE TRAN')):
            self.stats['transactions_skipped'] += 1
            return False
        
        # Valid statement types
        valid_starts = [
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE',
            'CREATE TABLE', 'CREATE VIEW', 'CREATE OR REPLACE', 'CREATE INDEX',
            'ALTER TABLE', 'ALTER VIEW',
            'WITH',  # CTEs
            'DROP', 'TRUNCATE',
            'EXEC', 'EXECUTE'
        ]
        
        is_valid = any(stmt_upper.startswith(start) for start in valid_starts)
        
        # Handle IF EXISTS/IF OBJECT_ID blocks
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
        
        # Check for RETURNS @table_variable TABLE (table-valued function)
        if re.search(r'RETURNS\s+@\w+\s+TABLE', content_upper):
            return 'TABLE_FUNCTION'
        
        # Check for RETURNS with a data type (scalar function)
        if re.search(r'RETURNS\s+[\w\[\]()]+', content_upper):
            return 'SCALAR_FUNCTION'
        
        # Default to FUNCTION if we can't determine
        return 'FUNCTION'
    
    def _extract_temp_tables(self, batch: str) -> List[Dict[str, str]]:
        """Extract temp table references"""
        temp_tables = []
        
        # Find all temp table references
        for match in self.temp_table.finditer(batch):
            temp_tables.append({
                'name': match.group(0),
                'type': 'local'
            })
        
        for match in self.global_temp.finditer(batch):
            temp_tables.append({
                'name': match.group(0),
                'type': 'global'
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
    cleaner = EnhancedSQLCleaner("./sql_files", debug=True)
    results = cleaner.clean_all_files(max_files=5)
    
    for file_path, content in results.items():
        print(f"\n{file_path}:")
        print(f"  Statements: {len(content['statements'])}")
        print(f"  Procedures: {len(content['procedures'])}")
        print(f"  Functions: {len(content['functions'])}")
        print(f"  Views: {len(content['views'])}")