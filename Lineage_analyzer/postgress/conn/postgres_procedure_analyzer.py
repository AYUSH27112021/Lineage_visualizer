"""
Enhanced PostgreSQL Procedure and Function Analyzer
Properly tracks tables and columns used within procedures and functions
Designed to run AFTER table/view analysis so it knows what exists
"""

import sqlglot
from sqlglot import exp, parse_one
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import re


@dataclass
class Parameter:
    """Procedure/function parameter"""
    name: str
    data_type: str
    is_output: bool = False
    default_value: Optional[str] = None


@dataclass
class ColumnReference:
    """Column reference in procedure/function"""
    table: str
    column: str
    operation: str  # 'READ', 'WRITE', 'UPDATE'
    statement_type: str  # 'SELECT', 'INSERT', 'UPDATE', etc.


@dataclass
class ProcedureLineage:
    """Lineage for a stored procedure or function"""
    file_path: str
    object_name: str
    object_type: str  # 'PROCEDURE', 'FUNCTION', 'TRIGGER'
    parameters: List[Parameter] = field(default_factory=list)
    return_type: Optional[str] = None
    creates_temp_tables: List[str] = field(default_factory=list)
    reads_tables: List[str] = field(default_factory=list)
    writes_tables: List[str] = field(default_factory=list)
    calls_procedures: List[str] = field(default_factory=list)
    internal_statements: List[Dict] = field(default_factory=list)
    output_columns: List[Dict] = field(default_factory=list)
    column_references: List[ColumnReference] = field(default_factory=list)
    parse_error: Optional[str] = None
    is_table_valued: bool = False
    body_sql: str = ""


class PostgreSQLProcedureAnalyzer:
    """Analyze stored procedures, functions, and triggers with full column tracking"""
    
    def __init__(self, dialect: str = "postgres", debug: bool = False, known_tables: Dict[str, List[str]] = None):
        self.dialect = dialect
        self.debug = debug
        self.stats = defaultdict(int)
        
        # Known tables and their columns (from previous table analysis)
        self.known_tables = known_tables or {}
        
        # Compile patterns
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns (PostgreSQL-specific)"""
        # Parameter pattern: matches "argname type [DEFAULT expr]" entries (no @ in PG)
        self.param_pattern = re.compile(
            r'(\w+)\s+([\w\"\[\]()",\s]+?)(?:\s+DEFAULT\s+([^,)]+?))?\s*(?:,|\))',
            re.IGNORECASE
        )
        
        # Return type for functions
        self.returns_pattern = re.compile(
            r'RETURNS\s+(@?\w+\s+)?(TABLE|[\w\[\](),\s]+)',
            re.IGNORECASE
        )
        
        # Procedure calls (CALL proc(...))
        self.exec_proc_pattern = re.compile(
            r'\bCALL\s+("?[\w\.]+"?)',
            re.IGNORECASE
        )
        
        # Temp table creation: CREATE TEMP/TEMPORARY TABLE name
        self.temp_table_create = re.compile(
            r'CREATE\s+(?:TEMP|TEMPORARY)\s+TABLE\s+("?[\w\.]+"?)',
            re.IGNORECASE
        )
        
        # SELECT ... INTO new_table
        self.select_into_temp = re.compile(
            r'\bINTO\s+("?[\w\.]+"?)',
            re.IGNORECASE
        )
        
        # No table variables in PostgreSQL; compile a never-matching pattern
        self.table_var_pattern = re.compile(r'\bTHIS_PATTERN_NEVER_MATCHES\b')
        
        # FROM clause pattern (quoted identifiers and aliases)
        self.from_pattern = re.compile(
            r'\bFROM\s+("?[\w\.]+"?)(?:\s+(?:AS\s+)?("?[\w]+"?))?',
            re.IGNORECASE
        )
        
        # JOIN patterns
        self.join_pattern = re.compile(
            r'\b(?:INNER|LEFT|RIGHT|FULL|CROSS)?\s*(?:OUTER\s+)?JOIN\s+("?[\w\.]+"?)(?:\s+(?:AS\s+)?("?[\w]+"?))?',
            re.IGNORECASE
        )
        
        # INSERT INTO pattern
        self.insert_pattern = re.compile(
            r'INSERT\s+(?:INTO\s+)?("?[\w\.]+"?)',
            re.IGNORECASE
        )
        
        # UPDATE pattern
        self.update_pattern = re.compile(
            r'UPDATE\s+("?[\w\.]+"?)',
            re.IGNORECASE
        )
        
        # DELETE pattern
        self.delete_pattern = re.compile(
            r'DELETE\s+FROM\s+("?[\w\.]+"?)',
            re.IGNORECASE
        )
        
        # Column reference pattern (table.column or alias.column) with quoted identifiers
        self.column_ref_pattern = re.compile(
            r'\b("?[\w#]+"?)\.("?[\w]+"?)\b',
            re.IGNORECASE
        )
    
    def set_known_tables(self, known_tables: Dict[str, List[str]]):
        """Update known tables from table analysis"""
        self.known_tables = known_tables
        if self.debug:
            print(f"   Loaded {len(known_tables)} known tables")
    
    def analyze_procedures(self, file_path: str, procedures: List[Dict]) -> List[ProcedureLineage]:
        """Analyze all procedures in a file"""
        results = []
        
        for proc_info in procedures:
            try:
                lineage = self._analyze_procedure(
                    file_path,
                    proc_info['name'],
                    proc_info['content'],
                    'PROCEDURE'
                )
                if lineage:
                    results.append(lineage)
                    self.stats['procedures_analyzed'] += 1
            except Exception as e:
                if self.debug:
                    print(f"      Warning: Error analyzing procedure {proc_info['name']}: {e}")
                self.stats['procedure_errors'] += 1
                
                results.append(ProcedureLineage(
                    file_path=file_path,
                    object_name=proc_info['name'],
                    object_type='PROCEDURE',
                    parse_error=str(e)
                ))
        
        return results
    
    def analyze_functions(self, file_path: str, functions: List[Dict]) -> List[ProcedureLineage]:
        """Analyze all functions in a file"""
        results = []
        
        for func_info in functions:
            try:
                lineage = self._analyze_procedure(
                    file_path,
                    func_info['name'],
                    func_info['content'],
                    'FUNCTION'
                )
                if lineage:
                    results.append(lineage)
                    self.stats['functions_analyzed'] += 1
            except Exception as e:
                if self.debug:
                    print(f"      Warning: Error analyzing function {func_info['name']}: {e}")
                self.stats['function_errors'] += 1
                
                results.append(ProcedureLineage(
                    file_path=file_path,
                    object_name=func_info['name'],
                    object_type='FUNCTION',
                    parse_error=str(e)
                ))
        
        return results
    
    def analyze_triggers(self, file_path: str, triggers: List[Dict]) -> List[ProcedureLineage]:
        """Analyze all triggers in a file"""
        results = []
        
        for trigger_info in triggers:
            try:
                lineage = self._analyze_procedure(
                    file_path,
                    trigger_info['name'],
                    trigger_info['content'],
                    'TRIGGER'
                )
                if lineage:
                    results.append(lineage)
                    self.stats['triggers_analyzed'] += 1
            except Exception as e:
                if self.debug:
                    print(f"      Warning: Error analyzing trigger {trigger_info['name']}: {e}")
                self.stats['trigger_errors'] += 1
                
                results.append(ProcedureLineage(
                    file_path=file_path,
                    object_name=trigger_info['name'],
                    object_type='TRIGGER',
                    parse_error=str(e)
                ))
        
        return results
    
    def _analyze_procedure(self, file_path: str, object_name: str, content: str, object_type: str) -> ProcedureLineage:
        """Analyze a procedure, function, or trigger with full column tracking"""
        # Extract parameters
        parameters = self._extract_parameters(content)
        
        # Extract return type (for functions)
        return_type = None
        is_table_valued = False
        if object_type == 'FUNCTION':
            return_type, is_table_valued = self._extract_return_type(content)
        
        # Extract body SQL
        body_sql = self._extract_body(content)
        
        # Extract temp tables and table variables
        temp_tables = self._extract_temp_tables(body_sql)
        
        # Track all table and column references
        reads_tables = set()
        writes_tables = set()
        column_references = []
        
        # Build alias map (table aliases used in the procedure)
        alias_map = self._build_alias_map(body_sql)
        
        # Analyze internal statements with full column tracking
        internal_statements = []
        
        try:
            # Split into statements
            statements = self._split_statements(body_sql)
            
            for stmt in statements:
                stmt_analysis = self._analyze_internal_statement(stmt, alias_map)
                if stmt_analysis:
                    internal_statements.append(stmt_analysis)
                    
                    # Collect table references
                    if stmt_analysis.get('type') == 'SELECT':
                        for table in stmt_analysis.get('tables', []):
                            reads_tables.add(table)
                        
                        # Collect column references from SELECT
                        for col_ref in stmt_analysis.get('column_references', []):
                            column_references.append(ColumnReference(
                                table=col_ref['table'],
                                column=col_ref['column'],
                                operation='READ',
                                statement_type='SELECT'
                            ))
                    
                    elif stmt_analysis.get('type') == 'INSERT':
                        target = stmt_analysis.get('target_table')
                        if target:
                            writes_tables.add(target)
                        
                        for table in stmt_analysis.get('source_tables', []):
                            reads_tables.add(table)
                        
                        # Collect column references
                        for col_ref in stmt_analysis.get('column_references', []):
                            column_references.append(ColumnReference(
                                table=col_ref['table'],
                                column=col_ref['column'],
                                operation='WRITE' if col_ref['table'] == target else 'READ',
                                statement_type='INSERT'
                            ))
                    
                    elif stmt_analysis.get('type') == 'UPDATE':
                        target = stmt_analysis.get('target_table')
                        if target:
                            writes_tables.add(target)
                        
                        for table in stmt_analysis.get('source_tables', []):
                            reads_tables.add(table)
                        
                        # Collect column references
                        for col_ref in stmt_analysis.get('column_references', []):
                            column_references.append(ColumnReference(
                                table=col_ref['table'],
                                column=col_ref['column'],
                                operation='UPDATE' if col_ref['table'] == target else 'READ',
                                statement_type='UPDATE'
                            ))
                    
                    elif stmt_analysis.get('type') == 'DELETE':
                        target = stmt_analysis.get('target_table')
                        if target:
                            writes_tables.add(target)
                        
                        for table in stmt_analysis.get('source_tables', []):
                            reads_tables.add(table)
        
        except Exception as e:
            if self.debug:
                print(f"        Warning: Could not fully parse statements: {e}")
        
        # Extract procedure calls
        calls_procedures = self._extract_procedure_calls(body_sql)
        
        # For table-valued functions, extract output columns
        output_columns = []
        if is_table_valued:
            output_columns = self._extract_output_columns(content)
        
        return ProcedureLineage(
            file_path=file_path,
            object_name=object_name,
            object_type=object_type,
            parameters=parameters,
            return_type=return_type,
            creates_temp_tables=temp_tables,
            reads_tables=list(reads_tables),
            writes_tables=list(writes_tables),
            calls_procedures=calls_procedures,
            internal_statements=internal_statements,
            output_columns=output_columns,
            column_references=column_references,
            is_table_valued=is_table_valued,
            body_sql=body_sql[:500]  # Store snippet
        )
    
    def _extract_body(self, content: str) -> str:
        """Extract procedure/function body"""
        # Find AS or BEGIN
        as_match = re.search(r'\bAS\b|\bBEGIN\b', content, re.IGNORECASE)
        if not as_match:
            return content
        
        return content[as_match.end():]
    
    def _build_alias_map(self, sql: str) -> Dict[str, str]:
        """Build map of table aliases to table names"""
        alias_map = {}
        
        # FROM clauses
        for match in self.from_pattern.finditer(sql):
            table = match.group(1).strip('"')
            alias = match.group(2)
            if alias:
                alias_map[alias.lower().strip('"')] = table
            else:
                # Use table name as its own alias
                table_short = table.split('.')[-1]
                alias_map[table_short.lower()] = table
        
        # JOIN clauses
        for match in self.join_pattern.finditer(sql):
            table = match.group(1).strip('"')
            alias = match.group(2)
            if alias:
                alias_map[alias.lower().strip('"')] = table
            else:
                table_short = table.split('.')[-1]
                alias_map[table_short.lower()] = table
        
        return alias_map
    
    def _analyze_internal_statement(self, stmt: str, alias_map: Dict[str, str]) -> Optional[Dict]:
        """Analyze a single statement inside procedure with column tracking"""
        stmt_upper = stmt.upper().strip()
        
        if not stmt or len(stmt) < 5:
            return None
        
        try:
            # Determine statement type
            if stmt_upper.startswith('SELECT'):
                return self._analyze_select_statement(stmt, alias_map)
            
            elif stmt_upper.startswith('INSERT'):
                return self._analyze_insert_statement(stmt, alias_map)
            
            elif stmt_upper.startswith('UPDATE'):
                return self._analyze_update_statement(stmt, alias_map)
            
            elif stmt_upper.startswith('DELETE'):
                return self._analyze_delete_statement(stmt, alias_map)
        
        except Exception as e:
            if self.debug:
                print(f"          Warning: Could not analyze statement: {e}")
        
        return None
    
    def _analyze_select_statement(self, stmt: str, alias_map: Dict[str, str]) -> Dict:
        """Analyze SELECT statement"""
        # Extract tables
        tables = []
        for match in self.from_pattern.finditer(stmt):
            table = match.group(1).strip('"')
            tables.append(table)
        
        for match in self.join_pattern.finditer(stmt):
            table = match.group(1).strip('"')
            tables.append(table)
        
        # Extract column references
        column_references = []
        for match in self.column_ref_pattern.finditer(stmt):
            table_or_alias = match.group(1)
            column = match.group(2)
            
            # Resolve alias to table name
            table = alias_map.get(table_or_alias.lower(), table_or_alias)
            
            # Skip if it's a variable or function
            if not table.startswith('@') and column.upper() not in ['NOCOUNT', 'IDENTITY_INSERT']:
                column_references.append({
                    'table': table,
                    'column': column,
                    'alias_used': table_or_alias if table_or_alias.lower() in alias_map else None
                })
        
        return {
            'type': 'SELECT',
            'tables': list(set(tables)),
            'column_references': column_references,
            'has_into': 'INTO' in stmt.upper()
        }
    
    def _analyze_insert_statement(self, stmt: str, alias_map: Dict[str, str]) -> Dict:
        """Analyze INSERT statement"""
        target_match = self.insert_pattern.search(stmt)
        target = target_match.group(1).strip('"') if target_match else None
        
        # Extract source tables (from SELECT part)
        source_tables = []
        if 'SELECT' in stmt.upper():
            for match in self.from_pattern.finditer(stmt):
                table = match.group(1).strip('"')
                source_tables.append(table)
            
            for match in self.join_pattern.finditer(stmt):
                table = match.group(1).strip('"')
                source_tables.append(table)
        
        # Extract column references
        column_references = []
        
        # Target columns (from INSERT INTO table (col1, col2))
        target_cols_match = re.search(r'INSERT\s+(?:INTO\s+)?[\w\.\[\]#@]+\s*\(([^)]+)\)', stmt, re.IGNORECASE)
        if target_cols_match and target:
            cols = target_cols_match.group(1).split(',')
            for col in cols:
                col = col.strip().strip('[]')
                if col:
                    column_references.append({
                        'table': target,
                        'column': col,
                        'alias_used': None
                    })
        
        # Source columns (from SELECT part)
        for match in self.column_ref_pattern.finditer(stmt):
            table_or_alias = match.group(1)
            column = match.group(2)
            
            table = alias_map.get(table_or_alias.lower(), table_or_alias)
            
            if not table.startswith('@'):
                column_references.append({
                    'table': table,
                    'column': column,
                    'alias_used': table_or_alias if table_or_alias.lower() in alias_map else None
                })
        
        return {
            'type': 'INSERT',
            'target_table': target,
            'source_tables': list(set(source_tables)),
            'column_references': column_references
        }
    
    def _analyze_update_statement(self, stmt: str, alias_map: Dict[str, str]) -> Dict:
        """Analyze UPDATE statement"""
        target_match = self.update_pattern.search(stmt)
        target = target_match.group(1).strip('"') if target_match else None
        
        # Extract source tables (from FROM or JOIN)
        source_tables = []
        for match in self.from_pattern.finditer(stmt):
            table = match.group(1).strip('"')
            if table != target:
                source_tables.append(table)
        
        for match in self.join_pattern.finditer(stmt):
            table = match.group(1).strip('"')
            source_tables.append(table)
        
        # Extract column references
        column_references = []
        for match in self.column_ref_pattern.finditer(stmt):
            table_or_alias = match.group(1)
            column = match.group(2)
            
            table = alias_map.get(table_or_alias.lower(), table_or_alias)
            
            if not table.startswith('@'):
                column_references.append({
                    'table': table,
                    'column': column,
                    'alias_used': table_or_alias if table_or_alias.lower() in alias_map else None
                })
        
        return {
            'type': 'UPDATE',
            'target_table': target,
            'source_tables': list(set(source_tables)),
            'column_references': column_references
        }
    
    def _analyze_delete_statement(self, stmt: str, alias_map: Dict[str, str]) -> Dict:
        """Analyze DELETE statement"""
        target_match = self.delete_pattern.search(stmt)
        target = target_match.group(1).strip('"') if target_match else None
        
        # Extract source tables (from joins in WHERE clause)
        source_tables = []
        for match in self.join_pattern.finditer(stmt):
            table = match.group(1).strip('"')
            source_tables.append(table)
        
        return {
            'type': 'DELETE',
            'target_table': target,
            'source_tables': list(set(source_tables))
        }
    
    def _extract_parameters(self, content: str) -> List[Parameter]:
        """Extract procedure/function parameters"""
        parameters = []
        
        # Find parameter block
        param_section_match = re.search(
            r'(?:PROCEDURE|FUNCTION)\s+[\w\.\[\]]+\s*(?:\(([^)]+)\)|([^)]*?)(?=\s+(?:RETURNS|AS)))',
            content,
            re.IGNORECASE | re.DOTALL
        )
        
        if param_section_match:
            param_text = param_section_match.group(1) or param_section_match.group(2)
            if param_text:
                # Extract each parameter
                for match in self.param_pattern.finditer(param_text + ','):  # Add comma to match last param
                    param_name = match.group(1)
                    data_type = match.group(2).strip()
                    default_value = match.group(3).strip() if match.group(3) else None
                    
                    # Check if OUTPUT is in the full match
                    full_match = match.group(0)
                    is_output = 'OUTPUT' in full_match.upper()
                    
                    parameters.append(Parameter(
                        name=param_name,
                        data_type=data_type,
                        is_output=is_output,
                        default_value=default_value
                    ))
        
        return parameters
    
    def _extract_return_type(self, content: str) -> Tuple[Optional[str], bool]:
        """Extract function return type"""
        match = self.returns_pattern.search(content)
        if match:
            return_type = match.group(2) if match.group(2) else match.group(1)
            return_type = return_type.strip() if return_type else None
            is_table_valued = return_type and 'TABLE' in return_type.upper()
            return return_type, is_table_valued
        return None, False
    
    def _extract_temp_tables(self, body_sql: str) -> List[str]:
        """Extract temp tables created in procedure"""
        temp_tables = []
        
        # CREATE TABLE temp_temp
        for match in self.temp_table_create.finditer(body_sql):
            temp_tables.append(match.group(1))
        
        # SELECT INTO temp_temp
        for match in self.select_into_temp.finditer(body_sql):
            temp_tables.append(match.group(1))
        
        # DECLARE @table TABLE
        for match in self.table_var_pattern.finditer(body_sql):
            temp_tables.append(match.group(1))
        
        return list(set(temp_tables))
    
    def _extract_procedure_calls(self, content: str) -> List[str]:
        """Extract other procedures called"""
        calls = []
        
        for match in self.exec_proc_pattern.finditer(content):
            proc_name = match.group(1).strip('[]')
            
            # Filter out dynamic SQL and system procedures
            if not proc_name.startswith(('sp_', 'sys.', '@', 'xp_')):
                calls.append(proc_name)
        
        return list(set(calls))
    
    def _split_statements(self, content: str) -> List[str]:
        """Split procedure body into statements"""
        # Find AS or BEGIN
        as_match = re.search(r'\bAS\b|\bBEGIN\b', content, re.IGNORECASE)
        if not as_match:
            body = content
        else:
            body = content[as_match.end():]
        
        # Simple split by semicolon (not perfect but workable)
        statements = []
        current = []
        in_string = False
        string_char = None
        
        for i, char in enumerate(body):
            if char in ('"', "'") and (i == 0 or body[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
            elif char == ';' and not in_string:
                current.append(char)
                stmt = ''.join(current).strip()
                if stmt and len(stmt) > 5:
                    statements.append(stmt)
                current = []
                continue
            
            current.append(char)
        
        # Add remaining
        if current:
            stmt = ''.join(current).strip()
            if stmt and len(stmt) > 5:
                statements.append(stmt)
        
        return statements
    
    def _extract_output_columns(self, content: str) -> List[Dict]:
        """Extract output columns from table-valued function"""
        columns = []
        
        # RETURNS TABLE or RETURNS @var TABLE (col definitions)
        returns_match = re.search(
            r'RETURNS\s+(?:@\w+\s+)?TABLE\s*\((.*?)\)',
            content,
            re.IGNORECASE | re.DOTALL
        )
        
        if returns_match:
            columns_text = returns_match.group(1)
            
            # Parse column definitions
            for line in columns_text.split(','):
                line = line.strip()
                if line:
                    parts = line.split()
                    if len(parts) >= 2:
                        col_name = parts[0].strip('[]')
                        data_type = ' '.join(parts[1:]).split()[0]  # Get data type
                        columns.append({
                            'name': col_name,
                            'data_type': data_type
                        })
        
        return columns


if __name__ == "__main__":
    analyzer = PostgreSQLProcedureAnalyzer(debug=True)
    
    test_proc = """
    CREATE PROCEDURE usp_Test
        @CustomerID INT
    AS
    BEGIN
        SELECT c.CustomerID, c.Name, o.OrderID
        FROM Customers AS c
        INNER JOIN Orders AS o ON c.CustomerID = o.CustomerID
        WHERE c.CustomerID = @CustomerID;
    END
    """
    
    results = analyzer.analyze_procedures("test.sql", [{'name': 'usp_Test', 'content': test_proc}])
    for result in results:
        print(f"\nProcedure: {result.object_name}")
        print(f"Reads: {result.reads_tables}")
        print(f"Column References: {len(result.column_references)}")
        for col_ref in result.column_references:
            print(f"  - {col_ref.table}.{col_ref.column} ({col_ref.operation})")