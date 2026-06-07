# How to Extend the Lineage Analyzer System

This guide shows you **exactly** how to extend the system in multiple ways:
- Adding new SQL patterns to existing dialects (T-SQL, PostgreSQL, Oracle, etc.)
- Adding new database dialects
- Extending metadata-based analysis connectors
- Adding new server endpoints

We'll use real examples from the existing code.

---

## Table of Contents

### Part 1: Extending Existing Dialects
1. [Adding New Patterns to Cleaner](#adding-new-patterns-to-cleaner)
2. [Adding New Analysis to Analyzer](#adding-new-analysis-to-analyzer)
3. [Updating JSON Builders](#updating-json-builders)
4. [Complete Example: Adding PIVOT Support](#complete-example-adding-pivot-support)

### Part 2: Adding New Database Dialects
5. [Adding a New Database Dialect - Overview](#adding-a-new-database-dialect---overview)
6. [File-based Analysis Components](#file-based-analysis-components)
7. [Metadata-based Connector Components](#metadata-based-connector-components)
8. [Registering in Server and Main Dispatcher](#registering-in-server-and-main-dispatcher)

### Part 3: Extending Metadata-based Analysis
9. [Extending Metadata Extractors](#extending-metadata-extractors)
10. [Extending Procedure Analyzers](#extending-procedure-analyzers)
11. [Adding New View Analysis Patterns](#adding-new-view-analysis-patterns)

### Part 4: Server Extensions
12. [Adding New API Endpoints](#adding-new-api-endpoints)
13. [Future Features List](#future-features-to-support-later)

---

## Adding New Patterns to Cleaner

### Step 1: Add Regex Pattern in `_compile_patterns()`

**Location**: `tsql_cleaner_enhanced.py` → `_compile_patterns()` method

**Example: How we handle CREATE PROCEDURE** (existing code)
```python
def _compile_patterns(self):
    """Compile all regex patterns"""
    # ... existing patterns ...
    
    # Object creation patterns
    self.create_proc = re.compile(
        r'CREATE\s+(?:OR\s+ALTER\s+)?(?:PROCEDURE|PROC)\s+(\[?[\w\.\[\]]+\]?)',
        re.IGNORECASE
    )
```

**New Example: Adding PIVOT/UNPIVOT support**
```python
def _compile_patterns(self):
    """Compile all regex patterns"""
    # ... existing patterns ...
    
    # Add PIVOT pattern
    self.pivot_pattern = re.compile(
        r'\bPIVOT\s*\(',
        re.IGNORECASE
    )
    
    # Add UNPIVOT pattern
    self.unpivot_pattern = re.compile(
        r'\bUNPIVOT\s*\(',
        re.IGNORECASE
    )
```

### Step 2: Add Validation/Detection Logic

**Location**: `tsql_cleaner_enhanced.py` → `_is_valid_statement()` or `_classify_batch()`

**Example: How we validate MERGE statements** (existing code)
```python
def _is_valid_statement(self, stmt: str) -> bool:
    """Check if statement should be processed"""
    # ... existing code ...
    
    # Valid statement types
    valid_starts = [
        'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE',  # <-- MERGE included
        'CREATE TABLE', 'CREATE VIEW', 'CREATE OR REPLACE', 'CREATE PROCEDURE',
        # ...
    ]
    
    is_valid = any(stmt_upper.startswith(start) for start in valid_starts)
    return is_valid
```

**New Example: Adding PIVOT validation**
```python
def _is_valid_statement(self, stmt: str) -> bool:
    """Check if statement should be processed"""
    # ... existing validation ...
    
    # Check for PIVOT/UNPIVOT (they're part of SELECT but need special handling)
    if self.pivot_pattern.search(stmt) or self.unpivot_pattern.search(stmt):
        is_valid = True
        self.stats['pivot_detected'] += 1
    
    return is_valid
```

### Step 3: Track Statistics (Optional)

**Location**: Throughout cleaner where you use the pattern

**Example: How we track procedures** (existing code)
```python
if classified.batch_type == 'procedure':
    result['procedures'].append({
        'name': classified.object_name,
        'content': classified.content,
        'line_number': classified.line_number
    })
    self.stats['procedures_found'] += 1  # <-- Tracking
```

---

## Adding New Analysis to Analyzer

### Step 1: Add Statement Type Recognition

**Location**: `tsql_analyzer_enhanced.py` → `_get_statement_type()` or `_get_statement_subtype()`

**Example: How we handle MERGE** (existing code)
```python
def _get_statement_type(self, tree: exp.Expression) -> str:
    """Get statement type"""
    type_map = {
        exp.Create: "CREATE",
        exp.Insert: "INSERT",
        exp.Update: "UPDATE",
        exp.Delete: "DELETE",
        exp.Select: "SELECT",
        exp.Merge: "MERGE",  # <-- MERGE type mapping
        # ...
    }
    
    for exp_type, name in type_map.items():
        if isinstance(tree, exp_type):
            return name
    
    return "UNKNOWN"
```

**New Example: Adding PIVOT subtype detection**
```python
def _get_statement_subtype(self, tree: exp.Expression, sql: str) -> Optional[str]:
    """Get statement subtype"""
    sql_upper = sql.upper()
    
    # ... existing subtypes ...
    
    # Add PIVOT detection
    if 'PIVOT' in sql_upper:
        return "SELECT_PIVOT"
    
    if 'UNPIVOT' in sql_upper:
        return "SELECT_UNPIVOT"
    
    return None
```

### Step 2: Create Specialized Analysis Method

**Location**: `tsql_analyzer_enhanced.py` → Add new method

**Example: How we analyze MERGE** (existing code)
```python
def _analyze_merge(self, tree: exp.Merge, file_path: str, cte_definitions: Dict) -> StatementLineage:
    """Analyze MERGE statement with MATCHED and NOT MATCHED clauses"""
    target_table = self._extract_target_table(tree)
    source_tables = []
    column_lineage = []
    
    # Get source table from USING clause
    using = tree.find(exp.Table)
    if using:
        source_tables.append(self._get_full_table_name(using))
    
    # Process WHEN MATCHED UPDATE
    for when in tree.find_all(exp.When):
        # Check if it's an UPDATE action
        for set_expr in when.find_all(exp.Set):
            target_col = set_expr.this.name if isinstance(set_expr.this, exp.Column) else str(set_expr.this)
            source_cols = self._find_source_columns(set_expr.expression, cte_definitions)
            
            column_lineage.append(ColumnLineage(
                target_column=target_col,
                target_table=target_table or "unknown",
                source_columns=source_cols,
                transform_type="merge_update",  # <-- Custom transform type
                expression=set_expr.expression.sql()[:200] if set_expr.expression else ""
            ))
    
    return StatementLineage(
        file_path=file_path,
        statement_type="MERGE",
        target_table=target_table,
        source_tables=list(set(source_tables)),
        column_lineage=column_lineage,
        cte_definitions=cte_definitions
    )
```

**New Example: Adding PIVOT analysis**
```python
def _analyze_pivot(self, tree: exp.Select, file_path: str, cte_definitions: Dict, sql: str) -> StatementLineage:
    """Analyze PIVOT/UNPIVOT operations"""
    target_table = None
    source_tables = []
    column_lineage = []
    
    # Extract source tables (before PIVOT)
    source_tables = self._extract_source_tables(tree)
    
    # For PIVOT, we need to parse the structure:
    # SELECT ... FROM ... PIVOT (AGG_FUNC(col) FOR pivot_col IN (val1, val2, ...))
    
    # Check if this has an INTO clause
    into = tree.args.get('into')
    if into:
        target_table = self._get_full_table_name(into) if isinstance(into, exp.Table) else str(into)
    
    # Parse PIVOT syntax - this is tricky with sqlglot
    # We'll use regex as fallback for PIVOT-specific parsing
    pivot_match = re.search(
        r'PIVOT\s*\(\s*(\w+)\s*\(\s*(\w+)\s*\)\s+FOR\s+(\w+)\s+IN\s*\(([^)]+)\)',
        sql,
        re.IGNORECASE | re.DOTALL
    )
    
    if pivot_match:
        agg_func = pivot_match.group(1)  # e.g., SUM
        agg_col = pivot_match.group(2)   # e.g., amount
        pivot_col = pivot_match.group(3) # e.g., month
        pivot_values = pivot_match.group(4).split(',')  # e.g., Jan, Feb, Mar
        
        # Create lineage for each pivoted column
        for value in pivot_values:
            value = value.strip().strip('[]')
            
            # Find source table for the aggregated column
            source_table = source_tables[0] if source_tables else "unknown"
            
            column_lineage.append(ColumnLineage(
                target_column=value,  # Pivoted column name
                target_table=target_table or "pivot_result",
                source_columns=[{
                    "table": source_table,
                    "column": agg_col
                }],
                transform_type="pivot_aggregate",  # New transform type
                expression=f"{agg_func}({agg_col}) WHERE {pivot_col}={value}",
                is_aggregate=True,
                is_calculated=True
            ))
    
    return StatementLineage(
        file_path=file_path,
        statement_type="SELECT",
        statement_subtype="SELECT_PIVOT",
        target_table=target_table,
        source_tables=source_tables,
        column_lineage=column_lineage,
        cte_definitions=cte_definitions
    )
```

### Step 3: Hook into Main Analysis Flow

**Location**: `tsql_analyzer_enhanced.py` → `_analyze_statement()` method

**Example: How MERGE is hooked in** (existing code)
```python
def _analyze_statement(self, sql: str, file_path: str) -> Optional[StatementLineage]:
    """Analyze a single SQL statement"""
    try:
        tree = parse_one(sql, dialect=self.dialect, error_level='ignore')
        if not tree:
            return None
        
        # ... CTE extraction ...
        
        # Extract lineage based on statement type
        if isinstance(tree, exp.Insert):
            return self._analyze_insert(tree, file_path, cte_definitions)
        
        elif isinstance(tree, exp.Update):
            return self._analyze_update(tree, file_path, cte_definitions)
        
        elif isinstance(tree, exp.Merge):  # <-- MERGE hook
            return self._analyze_merge(tree, file_path, cte_definitions)
        
        # ... other types ...
```

**New Example: Adding PIVOT hook**
```python
def _analyze_statement(self, sql: str, file_path: str) -> Optional[StatementLineage]:
    """Analyze a single SQL statement"""
    try:
        tree = parse_one(sql, dialect=self.dialect, error_level='ignore')
        if not tree:
            return None
        
        stmt_type = self._get_statement_type(tree)
        stmt_subtype = self._get_statement_subtype(tree, sql)
        cte_definitions = self._extract_ctes(tree)
        
        # ... existing handlers ...
        
        elif isinstance(tree, exp.Select):
            # Check if this is a PIVOT/UNPIVOT
            if stmt_subtype in ["SELECT_PIVOT", "SELECT_UNPIVOT"]:
                return self._analyze_pivot(tree, file_path, cte_definitions, sql)
            else:
                return self._analyze_select(tree, file_path, cte_definitions, stmt_subtype)
```

### Step 4: Add Transform Classification

**Location**: `tsql_analyzer_enhanced.py` → `_classify_transform()` method

**Example: How we classify MERGE transforms** (existing code)
```python
def _classify_transform(self, expr: exp.Expression) -> str:
    """Classify transformation type"""
    if isinstance(expr, exp.Column):
        return "direct"
    elif expr.find(exp.AggFunc):
        return "aggregate"
    elif expr.find(exp.Case):
        return "case"
    # ... more classifications ...
    return "expression"
```

**New Example: Adding PIVOT transform classification**
```python
def _classify_transform(self, expr: exp.Expression) -> str:
    """Classify transformation type"""
    # ... existing classifications ...
    
    # Check for PIVOT (this would be in context of the statement)
    # Since PIVOT is statement-level, we handle it differently
    # But we can detect if an expression is part of a pivot
    
    return "expression"

# OR add a parameter to pass context:
def _classify_transform(self, expr: exp.Expression, context: str = None) -> str:
    """Classify transformation type"""
    if context == "pivot":
        return "pivot_aggregate"
    
    # ... existing classifications ...
```

---

## Updating JSON Builders

### Step 1: Update Data Structures (if needed)

**Location**: `json_builder_enhanced.py` → `ColumnInfo` dataclass

**Example: How we track aggregates** (existing code)
```python
@dataclass
class ColumnInfo:
    """Aggregated column information"""
    name: str
    table: str
    source_columns: Set[Tuple[str, str]] = field(default_factory=set)
    transforms: Set[str] = field(default_factory=set)
    is_derived: bool = False
    is_aggregate: bool = False  # <-- Aggregate tracking
    is_calculated: bool = False
    # ...
```

**New Example: Adding PIVOT tracking**
```python
@dataclass
class ColumnInfo:
    """Aggregated column information"""
    name: str
    table: str
    source_columns: Set[Tuple[str, str]] = field(default_factory=set)
    transforms: Set[str] = field(default_factory=set)
    is_derived: bool = False
    is_aggregate: bool = False
    is_calculated: bool = False
    is_pivoted: bool = False  # <-- NEW: Track if column is from PIVOT
    pivot_source_column: Optional[str] = None  # <-- NEW: Original column before pivot
    pivot_value: Optional[str] = None  # <-- NEW: The value this column represents
    # ...
```

### Step 2: Update Statistics Tracking

**Location**: `json_builder_enhanced.py` → `__init__()` method

**Example: How we track set operations** (existing code)
```python
def __init__(self, dialect: str, source_directory: str):
    # ... existing code ...
    
    # Statistics
    self.stats = {
        'total_scripts': 0,
        'total_statements': 0,
        'successful_parses': 0,
        'parse_errors': 0,
        'dynamic_sql_count': 0,
        'duplicate_columns_merged': 0,
        'cte_count': 0,
        'temp_table_count': 0,
        'circular_dependencies': [],
        'set_operations': 0,  # <-- Set operations tracking
        'subquery_count': 0
    }
```

**New Example: Adding PIVOT statistics**
```python
def __init__(self, dialect: str, source_directory: str):
    # ... existing code ...
    
    self.stats = {
        # ... existing stats ...
        'set_operations': 0,
        'subquery_count': 0,
        'pivot_operations': 0,  # <-- NEW: Count PIVOT/UNPIVOT
        'unpivot_operations': 0  # <-- NEW
    }
```

### Step 3: Update Processing Logic

**Location**: `json_builder_enhanced.py` → `_process_file_result()` method

**Example: How we track set operations** (existing code)
```python
def _process_file_result(self, result: Dict[str, Any]):
    """Process a single file's analysis results"""
    # ... existing code ...
    
    for lineage in result.get('lineages', []):
        if lineage.parse_error:
            self.stats['parse_errors'] += 1
            continue
        
        self.stats['successful_parses'] += 1
        
        # Track special features
        if lineage.is_dynamic:
            self.stats['dynamic_sql_count'] += 1
        
        if lineage.statement_subtype in ['UNION', 'INTERSECT', 'EXCEPT']:
            self.stats['set_operations'] += 1  # <-- Tracking
```

**New Example: Adding PIVOT processing**
```python
def _process_file_result(self, result: Dict[str, Any]):
    """Process a single file's analysis results"""
    # ... existing code ...
    
    for lineage in result.get('lineages', []):
        # ... existing processing ...
        
        # Track PIVOT operations
        if lineage.statement_subtype == 'SELECT_PIVOT':
            self.stats['pivot_operations'] += 1
        
        if lineage.statement_subtype == 'SELECT_UNPIVOT':
            self.stats['unpivot_operations'] += 1
        
        # Process column lineage with PIVOT awareness
        for col_lineage in lineage.column_lineage:
            self._register_column_lineage(col_lineage, file_path)
            
            # Special handling for pivoted columns
            if col_lineage.transform_type == 'pivot_aggregate':
                col_key = f"{col_lineage.target_table}.{col_lineage.target_column}"
                if col_key in self.columns:
                    self.columns[col_key].is_pivoted = True
```

### Step 4: Update Column Registration

**Location**: `json_builder_enhanced.py` → `_register_column_lineage()` method

**Example: How we track aggregates** (existing code)
```python
def _register_column_lineage(self, col_lineage, file_path: str):
    """Register column-level lineage with enhanced tracking"""
    # ... existing code ...
    
    # Update flags
    if col_lineage.source_columns:
        col_info.is_derived = True
    
    if col_lineage.is_aggregate:
        col_info.is_aggregate = True  # <-- Setting aggregate flag
    
    if col_lineage.is_calculated:
        col_info.is_calculated = True
```

**New Example: Adding PIVOT registration**
```python
def _register_column_lineage(self, col_lineage, file_path: str):
    """Register column-level lineage with enhanced tracking"""
    # ... existing code ...
    
    # Update flags
    if col_lineage.source_columns:
        col_info.is_derived = True
    
    if col_lineage.is_aggregate:
        col_info.is_aggregate = True
    
    if col_lineage.is_calculated:
        col_info.is_calculated = True
    
    # NEW: Handle PIVOT columns
    if col_lineage.transform_type == 'pivot_aggregate':
        col_info.is_pivoted = True
        # Extract pivot metadata from expression
        # e.g., "SUM(amount) WHERE month=Jan"
        if 'WHERE' in col_lineage.expression:
            parts = col_lineage.expression.split('WHERE')
            col_info.pivot_source_column = parts[0].strip()
            col_info.pivot_value = parts[1].strip() if len(parts) > 1 else None
```

### Step 5: Update JSON Output

**Location**: `json_builder_enhanced.py` → `_build_json_report()` method

**Example: How we output aggregate info** (existing code)
```python
def _build_json_report(self, execution_order: Dict) -> Dict:
    """Build final JSON report structure"""
    # ... existing code ...
    
    # Build columns section
    columns_json = {}
    for col_key, col_info in self.columns.items():
        columns_json[col_key] = {
            "table": col_info.table,
            "name": col_info.name,
            "source_columns": [f"{t}.{c}" for t, c in col_info.source_columns],
            "transforms": list(col_info.transforms),
            "is_derived": col_info.is_derived,
            "is_aggregate": col_info.is_aggregate,  # <-- Output aggregate flag
            "is_calculated": col_info.is_calculated,
            # ...
        }
```

**New Example: Adding PIVOT to output**
```python
def _build_json_report(self, execution_order: Dict) -> Dict:
    """Build final JSON report structure"""
    # ... existing code ...
    
    # Build columns section
    columns_json = {}
    for col_key, col_info in self.columns.items():
        col_dict = {
            "table": col_info.table,
            "name": col_info.name,
            "source_columns": [f"{t}.{c}" for t, c in col_info.source_columns],
            "transforms": list(col_info.transforms),
            "is_derived": col_info.is_derived,
            "is_aggregate": col_info.is_aggregate,
            "is_calculated": col_info.is_calculated,
            "cte_dependencies": list(col_info.cte_dependencies),
            "defining_scripts": list(col_info.defining_scripts),
            "confidence_score": col_info.confidence_score,
            "sample_expressions": col_info.expressions[:3]
        }
        
        # NEW: Add PIVOT-specific info
        if col_info.is_pivoted:
            col_dict["is_pivoted"] = True
            col_dict["pivot_source_column"] = col_info.pivot_source_column
            col_dict["pivot_value"] = col_info.pivot_value
        
        columns_json[col_key] = col_dict
    
    # ... build final report ...
    
    report = {
        # ... existing sections ...
        "summary": {
            # ... existing stats ...
            "pivot_operations": self.stats['pivot_operations'],  # <-- NEW
            "unpivot_operations": self.stats['unpivot_operations']  # <-- NEW
        },
        # ...
    }
```

### Step 6: Update Confidence Scoring (if needed)

**Location**: `json_builder_enhanced.py` → `_calculate_confidence_scores()` method

**Example: How we score aggregates** (existing code)
```python
def _calculate_confidence_scores(self):
    """Calculate confidence scores for column lineage"""
    for col_info in self.columns.values():
        # Start with base confidence
        confidence = 1.0
        
        # Direct mapping = high confidence
        if 'direct' in col_info.transforms:
            confidence = 1.0
        
        # Aggregate = medium-high confidence
        elif col_info.is_aggregate:
            confidence = 0.85  # <-- Aggregate confidence
```

**New Example: Adding PIVOT confidence scoring**
```python
def _calculate_confidence_scores(self):
    """Calculate confidence scores for column lineage"""
    for col_info in self.columns.values():
        # Start with base confidence
        confidence = 1.0
        
        # Direct mapping = high confidence
        if 'direct' in col_info.transforms:
            confidence = 1.0
        
        # Aggregate = medium-high confidence
        elif col_info.is_aggregate:
            confidence = 0.85
        
        # NEW: PIVOT operations have slightly lower confidence
        # because they involve transformation and aggregation
        elif col_info.is_pivoted:
            confidence = 0.80  # Slightly lower due to complexity
        
        # ... rest of scoring logic ...
        
        col_info.confidence_score = round(confidence, 2)
```

---

## Complete Example: Adding PIVOT Support

Here's a complete walkthrough of adding PIVOT/UNPIVOT support to the system:

### File 1: `tsql_cleaner_enhanced.py`

```python
# In _compile_patterns() method
def _compile_patterns(self):
    # ... existing patterns ...
    
    # PIVOT/UNPIVOT detection
    self.pivot_pattern = re.compile(r'\bPIVOT\s*\(', re.IGNORECASE)
    self.unpivot_pattern = re.compile(r'\bUNPIVOT\s*\(', re.IGNORECASE)

# In _is_valid_statement() method
def _is_valid_statement(self, stmt: str) -> bool:
    # ... existing validation ...
    
    # PIVOT/UNPIVOT are part of SELECT but need tracking
    if self.pivot_pattern.search(stmt) or self.unpivot_pattern.search(stmt):
        self.stats['pivot_statements'] += 1
        is_valid = True
    
    return is_valid
```

### File 2: `tsql_analyzer_enhanced.py`

```python
# In _get_statement_subtype() method
def _get_statement_subtype(self, tree: exp.Expression, sql: str) -> Optional[str]:
    sql_upper = sql.upper()
    
    # ... existing subtypes ...
    
    if 'PIVOT' in sql_upper and 'UNPIVOT' not in sql_upper:
        return "SELECT_PIVOT"
    
    if 'UNPIVOT' in sql_upper:
        return "SELECT_UNPIVOT"
    
    return None

# Add new analysis method
def _analyze_pivot(self, tree: exp.Select, file_path: str, cte_definitions: Dict, sql: str) -> StatementLineage:
    """Analyze PIVOT/UNPIVOT operations"""
    target_table = None
    source_tables = self._extract_source_tables(tree)
    column_lineage = []
    
    # Check for INTO clause
    into = tree.args.get('into')
    if into:
        target_table = self._get_full_table_name(into) if isinstance(into, exp.Table) else str(into)
    
    # Parse PIVOT structure using regex (sqlglot may not fully support PIVOT)
    pivot_match = re.search(
        r'PIVOT\s*\(\s*(\w+)\s*\(\s*(\w+)\s*\)\s+FOR\s+(\w+)\s+IN\s*\(([^)]+)\)',
        sql,
        re.IGNORECASE | re.DOTALL
    )
    
    if pivot_match:
        agg_func = pivot_match.group(1)
        agg_col = pivot_match.group(2)
        pivot_col = pivot_match.group(3)
        pivot_values = [v.strip().strip('[]') for v in pivot_match.group(4).split(',')]
        
        source_table = source_tables[0] if source_tables else "unknown"
        
        # Create lineage for each pivoted column
        for value in pivot_values:
            column_lineage.append(ColumnLineage(
                target_column=value,
                target_table=target_table or "pivot_result",
                source_columns=[{"table": source_table, "column": agg_col}],
                transform_type="pivot_aggregate",
                expression=f"{agg_func}({agg_col}) FOR {pivot_col}={value}",
                is_aggregate=True,
                is_calculated=True
            ))
    
    return StatementLineage(
        file_path=file_path,
        statement_type="SELECT",
        statement_subtype="SELECT_PIVOT",
        target_table=target_table,
        source_tables=source_tables,
        column_lineage=column_lineage,
        cte_definitions=cte_definitions
    )

# In _analyze_statement() method - add hook
def _analyze_statement(self, sql: str, file_path: str) -> Optional[StatementLineage]:
    # ... existing code ...
    
    elif isinstance(tree, exp.Select):
        if stmt_subtype in ["SELECT_PIVOT", "SELECT_UNPIVOT"]:
            return self._analyze_pivot(tree, file_path, cte_definitions, sql)
        else:
            return self._analyze_select(tree, file_path, cte_definitions, stmt_subtype)
```

### File 3: `json_builder_enhanced.py`

```python
# Update ColumnInfo dataclass
@dataclass
class ColumnInfo:
    # ... existing fields ...
    is_pivoted: bool = False
    pivot_source_column: Optional[str] = None
    pivot_value: Optional[str] = None

# Update stats dictionary in __init__
def __init__(self, dialect: str, source_directory: str):
    # ... existing code ...
    self.stats = {
        # ... existing stats ...
        'pivot_operations': 0,
        'unpivot_operations': 0
    }

# Update _process_file_result()
def _process_file_result(self, result: Dict[str, Any]):
    # ... existing code ...
    
    for lineage in result.get('lineages', []):
        # ... existing processing ...
        
        if lineage.statement_subtype == 'SELECT_PIVOT':
            self.stats['pivot_operations'] += 1
        
        if lineage.statement_subtype == 'SELECT_UNPIVOT':
            self.stats['unpivot_operations'] += 1

# Update _register_column_lineage()
def _register_column_lineage(self, col_lineage, file_path: str):
    # ... existing code ...
    
    if col_lineage.transform_type == 'pivot_aggregate':
        col_info.is_pivoted = True
        # Parse expression to extract metadata
        if 'FOR' in col_lineage.expression:
            parts = col_lineage.expression.split('FOR')
            col_info.pivot_source_column = parts[0].strip()
            if len(parts) > 1:
                col_info.pivot_value = parts[1].strip()

# Update _build_json_report()
def _build_json_report(self, execution_order: Dict) -> Dict:
    # ... existing code ...
    
    columns_json = {}
    for col_key, col_info in self.columns.items():
        col_dict = {
            # ... existing fields ...
            "is_pivoted": col_info.is_pivoted,
        }
        
        if col_info.is_pivoted:
            col_dict["pivot_details"] = {
                "source_column": col_info.pivot_source_column,
                "pivot_value": col_info.pivot_value
            }
        
        columns_json[col_key] = col_dict
    
    # Update summary
    report = {
        # ... existing sections ...
        "summary": {
            # ... existing stats ...
            "pivot_operations": self.stats['pivot_operations'],
            "unpivot_operations": self.stats['unpivot_operations']
        }
    }

# Update confidence scoring
def _calculate_confidence_scores(self):
    for col_info in self.columns.values():
        confidence = 1.0
        
        # ... existing scoring ...
        
        if col_info.is_pivoted:
            confidence = 0.80  # PIVOT has medium confidence
        
        # ... rest of logic ...
        
        col_info.confidence_score = round(confidence, 2)
```

### Testing Your New Feature

Create a test file `test_pivot.py`:

```python
from main_orchestrator import LineageOrchestrator
import tempfile
from pathlib import Path

# Create test SQL with PIVOT
test_sql = """
SELECT *
INTO #pivot_result
FROM (
    SELECT customer_id, month, amount
    FROM sales
) AS source_data
PIVOT (
    SUM(amount)
    FOR month IN ([Jan], [Feb], [Mar])
) AS pivot_table;
"""

# Write to temp file
temp_dir = tempfile.mkdtemp()
test_file = Path(temp_dir) / "pivot_test.sql"
test_file.write_text(test_sql)

# Run analysis
orchestrator = LineageOrchestrator(
    sql_directory=temp_dir,
    output_directory=temp_dir + "/output",
    debug=True
)

results = orchestrator.run_full_analysis()

# Check results
report = results['statement_report']
print(f"PIVOT operations found: {report['summary']['pivot_operations']}")
print(f"Columns: {list(report['columns'].keys())}")
```

---

## Part 2: Adding New Database Dialects

### Adding a New Database Dialect - Overview

To add support for a new database dialect (e.g., MySQL, DB2, Redshift), you need to implement both file-based and metadata-based analysis paths.

**Directory Structure**:
```
Lineage_analyzer/
└── {new_dialect}/
    ├── {new_dialect}_main.py          # File-based entry point
    ├── {new_dialect}_cleaner.py       # File cleaning
    ├── {new_dialect}_analyzer.py      # SQL parsing
    ├── {new_dialect}_json_builder.py # Report generation
    └── conn/                          # Metadata-based connector
        ├── metadata_lineage_main.py      # MetadataLineageOrchestrator
        ├── enhanced_metadata_extractor.py # Database metadata extraction
        ├── enhanced_procedure_analyzer.py # LLM-based procedure analysis
        ├── metadata_view_analyzer.py     # View/query analysis
        ├── metadata_statement_builder.py # Statement lineage builder
        └── enhanced_json_builder.py     # Final JSON builder
```

---

### File-based Analysis Components

#### Step 1: Create Dialect Main Module

**Location**: `{new_dialect}/{new_dialect}_main.py`

**Example**: Based on `postgress/postgres_main.py`:

```python
"""
{New Dialect} Lineage Analyzer - File-based Entry Point
"""
import argparse
from pathlib import Path
from typing import Optional

from .{new_dialect}_cleaner import {NewDialect}Cleaner
from .{new_dialect}_analyzer import {NewDialect}Analyzer
from .{new_dialect}_json_builder import {NewDialect}JSONBuilder


def main():
    parser = argparse.ArgumentParser(description="{New Dialect} Lineage Analyzer")
    parser.add_argument("sql_directory", help="Directory containing SQL files")
    parser.add_argument("--output", "-o", default="./lineage_output", help="Output directory")
    parser.add_argument("--dialect", "-d", default="{new_dialect}", help="SQL dialect")
    parser.add_argument("--max-files", "-m", type=int, help="Maximum files to process")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Initialize components
    cleaner = {NewDialect}Cleaner(dialect=args.dialect, debug=args.debug)
    analyzer = {NewDialect}Analyzer(dialect=args.dialect, debug=args.debug)
    json_builder = {NewDialect}JSONBuilder(dialect=args.dialect, source_directory=args.sql_directory)
    
    # Process files
    sql_files = list(Path(args.sql_directory).glob("**/*.sql"))
    if args.max_files:
        sql_files = sql_files[:args.max_files]
    
    for sql_file in sql_files:
        # Clean
        cleaned = cleaner.clean_file(sql_file)
        
        # Analyze
        results = analyzer.analyze_file(cleaned)
        
        # Build JSON
        json_builder.process_file_result(results)
    
    # Generate reports
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_builder.write_reports(str(output_dir))


if __name__ == "__main__":
    main()
```

#### Step 2: Create Cleaner

**Location**: `{new_dialect}/{new_dialect}_cleaner.py`

Follow the pattern from `tsql/tsql_cleaner_enhanced.py` or `postgress/conn/postgres_cleaner.py`:

- Implement batch splitting logic (dialect-specific separators)
- Remove comments (dialect-specific comment syntax)
- Classify statements (CREATE, SELECT, INSERT, etc.)
- Handle dialect-specific features

#### Step 3: Create Analyzer

**Location**: `{new_dialect}/{new_dialect}_analyzer.py`

Use `sqlglot` with your dialect:

```python
from sqlglot import parse_one, exp

class {NewDialect}Analyzer:
    def __init__(self, dialect: str = "{new_dialect}", debug: bool = False):
        self.dialect = dialect
        self.debug = debug
    
    def analyze_file(self, cleaned_content: dict) -> dict:
        """Analyze SQL file and extract lineage"""
        lineages = []
        
        for statement in cleaned_content.get('statements', []):
            try:
                tree = parse_one(statement['content'], dialect=self.dialect)
                if tree:
                    lineage = self._analyze_statement(tree, statement['file_path'])
                    if lineage:
                        lineages.append(lineage)
            except Exception as e:
                if self.debug:
                    print(f"Parse error: {e}")
        
        return {'lineages': lineages}
    
    def _analyze_statement(self, tree: exp.Expression, file_path: str):
        """Extract lineage from parsed SQL tree"""
        # Implement dialect-specific analysis
        # See existing analyzers for patterns
        pass
```

#### Step 4: Create JSON Builder

**Location**: `{new_dialect}/{new_dialect}_json_builder.py`

Follow the pattern from existing JSON builders. The output format should match the standard three-report structure.

---

### Metadata-based Connector Components

#### Step 1: Create MetadataLineageOrchestrator

**Location**: `{new_dialect}/conn/metadata_lineage_main.py`

**Template** (based on Oracle/Teradata pattern):

```python
"""
Metadata-Based Lineage Analysis Orchestrator for {New Dialect}
"""
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

from .enhanced_metadata_extractor import extract_enhanced_database_metadata
from .metadata_view_analyzer import MetadataViewAnalyzer
from .metadata_statement_builder import MetadataStatementBuilder
from .enhanced_procedure_analyzer import EnhancedProcedureAnalyzer
from .enhanced_json_builder import EnhancedJSONBuilder


class MetadataLineageOrchestrator:
    """
    Main orchestrator for metadata-based lineage analysis in {New Dialect}.
    
    Uses database connection instead of SQL files:
    1. Extracts metadata via enhanced_metadata_extractor
    2. Analyzes views/queries with traditional parsing
    3. Analyzes procedures/functions with LLM
    4. Outputs in same format as file-based analysis
    """
    
    def __init__(
        self,
        # Database connection parameters (dialect-specific)
        host: str,
        database: str,
        username: str,
        password: str,
        port: int = 5432,  # Adjust for your dialect
        # Output configuration
        output_directory: str = "./lineage_output",
        dialect: str = "{new_dialect}",
        debug: bool = False,
        # LLM Configuration
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:14b",
        openai_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
        batch_size: int = 10,
        timeout: int = 300,
        # Optional: Pre-loaded metadata
        metadata_file_path: Optional[str] = None,
    ):
        """Initialize the metadata-based lineage orchestrator."""
        # Store connection parameters
        self.host = host
        self.database = database
        self.username = username
        self.password = password
        self.port = port
        
        # Store configuration
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.dialect = dialect
        self.debug = debug
        
        # LLM configuration
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.batch_size = batch_size
        self.timeout = timeout
        
        # Metadata
        self.metadata = None
        self.metadata_file_path = metadata_file_path
        
        # Initialize components (will be created in run_full_analysis)
        self.view_analyzer = None
        self.statement_builder = None
        self.procedure_analyzer = None
        self.json_builder = None
    
    def run_full_analysis(self) -> Dict[str, Any]:
        """
        Run the complete metadata-based lineage analysis.
        
        Returns:
            Dictionary with statistics and results
        """
        start_time = datetime.now()
        
        # Step 1: Extract or load metadata
        if self.metadata_file_path and Path(self.metadata_file_path).exists():
            self._load_metadata_from_file()
        else:
            self._extract_metadata()
        
        # Step 2: Initialize analyzers
        self._initialize_analyzers()
        
        # Step 3: Analyze views and queries (traditional parsing)
        view_lineage = self._analyze_views()
        
        # Step 4: Analyze procedures/functions (LLM-based)
        procedure_lineage = self._analyze_procedures()
        
        # Step 5: Build statement lineage
        statement_lineage = self._build_statement_lineage(view_lineage, procedure_lineage)
        
        # Step 6: Generate JSON reports
        reports = self._generate_reports(statement_lineage, procedure_lineage)
        
        elapsed_time = (datetime.now() - start_time).total_seconds()
        
        return {
            "statistics": {
                "views_analyzed": len(view_lineage),
                "procedures_analyzed": len(procedure_lineage),
                "statements_analyzed": len(statement_lineage),
            },
            "elapsed_time": elapsed_time,
            "output_files": {
                "statement_report": str(reports.get("statement_path", "")),
                "procedure_report": str(reports.get("procedure_path", "")),
                "summary": str(reports.get("summary_path", "")),
            }
        }
    
    def _extract_metadata(self):
        """Extract metadata from database"""
        self.metadata, self.metadata_file_path = extract_enhanced_database_metadata(
            host=self.host,
            database=self.database,
            username=self.username,
            password=self.password,
            port=self.port,
            output_dir=None,  # Uses default metadata_cache directory
        )
    
    def _load_metadata_from_file(self):
        """Load metadata from cached file"""
        import json
        with open(self.metadata_file_path, 'r') as f:
            self.metadata = json.load(f)
    
    def _initialize_analyzers(self):
        """Initialize analysis components"""
        self.view_analyzer = MetadataViewAnalyzer(
            metadata=self.metadata,
            dialect=self.dialect,
            debug=self.debug
        )
        
        self.statement_builder = MetadataStatementBuilder(
            metadata=self.metadata,
            dialect=self.dialect,
            debug=self.debug
        )
        
        self.procedure_analyzer = EnhancedProcedureAnalyzer(
            metadata=self.metadata,
            dialect=self.dialect,
            ollama_url=self.ollama_url,
            ollama_model=self.ollama_model,
            openai_api_key=self.openai_api_key,
            openai_model=self.openai_model,
            batch_size=self.batch_size,
            timeout=self.timeout,
            debug=self.debug
        )
        
        self.json_builder = EnhancedJSONBuilder(
            metadata=self.metadata,
            dialect=self.dialect,
            debug=self.debug
        )
    
    def _analyze_views(self) -> List[Dict]:
        """Analyze views and materialized views"""
        return self.view_analyzer.analyze_all_views()
    
    def _analyze_procedures(self) -> List[Dict]:
        """Analyze procedures, functions, and triggers"""
        return self.procedure_analyzer.analyze_all_procedures()
    
    def _build_statement_lineage(self, view_lineage: List, procedure_lineage: List) -> List[Dict]:
        """Build combined statement lineage"""
        return self.statement_builder.build_lineage(view_lineage, procedure_lineage)
    
    def _generate_reports(self, statement_lineage: List, procedure_lineage: List) -> Dict[str, Path]:
        """Generate final JSON reports"""
        return self.json_builder.build_all_reports(
            statement_lineage=statement_lineage,
            procedure_lineage=procedure_lineage,
            output_directory=str(self.output_directory)
        )
```

#### Step 2: Create Enhanced Metadata Extractor

**Location**: `{new_dialect}/conn/enhanced_metadata_extractor.py`

**Key Function**:

```python
def extract_enhanced_database_metadata(
    host: str,
    database: str,
    username: str,
    password: str,
    port: int = 5432,
    output_dir: Optional[str] = None,
) -> Tuple[Dict, Path]:
    """
    Extract comprehensive metadata from {New Dialect} database.
    
    Returns:
        Tuple of (metadata_dict, output_file_path)
    """
    # Connect to database using dialect-specific driver
    # Query system catalogs for:
    # - Tables and columns
    # - Views and materialized views
    # - Procedures, functions, triggers
    # - Constraints, indexes
    # - Query history (if available)
    
    metadata = {
        "database": {
            "name": database,
            "host": host,
            "dialect": "{new_dialect}"
        },
        "tables": [...],  # List of table metadata
        "views": [...],   # List of view definitions
        "procedures": [...],  # List of procedure definitions
        "functions": [...],   # List of function definitions
        "summary": {
            "table_count": 0,
            "view_count": 0,
            "procedure_count": 0,
            # ...
        }
    }
    
    # Save to metadata_cache/ directory
    if output_dir is None:
        output_dir = Path.cwd() / "metadata_cache"
    else:
        output_dir = Path(output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"{new_dialect}_metadata_{timestamp}.json"
    
    with open(output_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return metadata, output_file
```

#### Step 3: Create Other Connector Components

Follow the patterns from existing dialects:

- **`metadata_view_analyzer.py`**: Analyzes view definitions using traditional SQL parsing
- **`enhanced_procedure_analyzer.py`**: Uses LLM to analyze procedure/function bodies
- **`metadata_statement_builder.py`**: Combines view and procedure lineage
- **`enhanced_json_builder.py`**: Generates the three standard JSON reports

---

### Registering in Server and Main Dispatcher

#### Step 1: Register in `main.py`

**Location**: `Lineage_analyzer/main.py`

```python
def run_{new_dialect}(
    sql_directory: str,
    output: str,
    dialect: str,
    max_files: int | None,
    debug: bool,
    openai_key: str | None = None,
) -> int:
    """Execute the {New Dialect} analyzer entrypoint."""
    {new_dialect}_entry = Path(__file__).parent / "{new_dialect}" / "{new_dialect}_main.py"
    forwarded_argv: list[str] = [
        str({new_dialect}_entry),
        sql_directory,
        "--output", output,
        "--dialect", dialect
    ]
    if max_files is not None:
        forwarded_argv += ["--max-files", str(max_files)]
    if debug:
        forwarded_argv += ["--debug"]
    if openai_key:
        forwarded_argv += ["--openai-key", openai_key]
    
    return _run_module(
        "Lineage_analyzer.{new_dialect}.{new_dialect}_main",
        {new_dialect}_entry,
        forwarded_argv
    )

# In main() function, add routing:
if dialect in {"{new_dialect}"}:
    return run_{new_dialect}(
        sql_directory=args.sql_directory,
        output=args.output,
        dialect=args.dialect,
        max_files=args.max_files,
        debug=args.debug,
        openai_key=getattr(args, 'openai_key', None),
    )
```

#### Step 2: Register in `server.py`

**Location**: `Lineage_analyzer/server.py`

**A. Add Request Models**:

```python
class {NewDialect}ConnectionInfo(BaseModel):
    host: str = Field(..., description="{New Dialect} server hostname")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    port: int = Field(5432, description="{New Dialect} port")

class {NewDialect}MetadataAnalysisRequest(BaseModel):
    host: str = Field(..., description="{New Dialect} server hostname")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Login username")
    password: str = Field(..., description="Login password")
    port: int = Field(5432, description="{New Dialect} port")
    dialect: str = Field("{new_dialect}", description="SQL dialect")
    debug: bool = Field(False, description="Enable debug logging")
    ollama_url: Optional[str] = Field("http://localhost:11434", description="Ollama API URL")
    ollama_model: Optional[str] = Field("qwen2.5-coder:14b", description="Ollama model name")
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    openai_model: Optional[str] = Field("gpt-4o-mini", description="OpenAI model name")
    batch_size: int = Field(10, description="Parallel processing batch size")
    timeout: int = Field(300, description="LLM timeout in seconds")
    metadata_file_path: Optional[str] = Field(None, description="Path to cached metadata JSON file")
    output_directory: Optional[str] = Field(None, description="Optional output directory override")
```

**B. Add Imports**:

```python
from .{new_dialect}.conn.metadata_lineage_main import (
    MetadataLineageOrchestrator as {NewDialect}MetadataLineageOrchestrator,
)
from .{new_dialect}.conn.enhanced_metadata_extractor import (
    extract_enhanced_database_metadata as extract_{new_dialect}_enhanced_metadata,
)
```

**C. Add Metadata Extraction Endpoint**:

```python
@app.post("/api/metadata/{new_dialect}")
async def extract_{new_dialect}_metadata(info: {NewDialect}ConnectionInfo):
    """Extract database metadata for {New Dialect} and persist it for lineage analysis."""
    try:
        metadata, file_path = extract_{new_dialect}_enhanced_metadata(
            host=info.host,
            database=info.database,
            username=info.username,
            password=info.password,
            port=info.port,
            output_dir=None,
        )
        
        response_payload = {
            "status": "success",
            "saved_to": str(file_path),
            "summary": metadata.get("summary", {}),
            "database": metadata.get("database", {}),
        }
        return JSONResponse(response_payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("{New Dialect} metadata extraction failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

**D. Add Metadata Analysis Endpoint**:

```python
@app.post("/api/analyze/metadata/{new_dialect}")
async def analyze_{new_dialect}_metadata(request: {NewDialect}MetadataAnalysisRequest):
    """Run metadata-based lineage analysis for {New Dialect} databases."""
    logger.info("/api/analyze/metadata/{new_dialect} called: host=%s, database=%s", request.host, request.database)
    
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            if request.output_directory:
                output_dir = Path(request.output_directory).expanduser().resolve()
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                output_dir = Path(tmp_dir) / "lineage_output"
                output_dir.mkdir(parents=True, exist_ok=True)
            
            orchestrator = {NewDialect}MetadataLineageOrchestrator(
                host=request.host,
                database=request.database,
                username=request.username,
                password=request.password,
                port=request.port,
                output_directory=str(output_dir),
                dialect=request.dialect,
                debug=request.debug,
                ollama_url=request.ollama_url or "http://localhost:11434",
                ollama_model=request.ollama_model or "qwen2.5-coder:14b",
                openai_api_key=request.openai_api_key,
                openai_model=request.openai_model or "gpt-4o-mini",
                batch_size=request.batch_size,
                timeout=request.timeout,
                metadata_file_path=request.metadata_file_path,
            )
            
            logger.info("Starting {New Dialect} metadata-based lineage analysis...")
            results = orchestrator.run_full_analysis()
            logger.info("{New Dialect} analysis completed successfully")
            
            # Load and return reports (same pattern as other dialects)
            # ... (see existing endpoints for pattern)
            
    except RuntimeError as exc:
        logger.exception("{New Dialect} metadata analysis failed with runtime error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("{New Dialect} metadata analysis failed: %s", exc)
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {exc}. Traceback: {tb}"
        ) from exc
```

**E. Update Dynamic Routing**:

```python
@app.post("/api/analyze/metadata/{dialect}")
async def analyze_metadata_dynamic(dialect: str, request: Request):
    """Flexible metadata endpoint that routes requests based on dialect in the path."""
    payload = await request.json()
    dialect_lower = (dialect or "").lower()
    
    # ... existing dialects ...
    
    if dialect_lower in {"{new_dialect}"}:
        model = {NewDialect}MetadataAnalysisRequest(**payload)
        return await analyze_{new_dialect}_metadata(model)
    
    raise HTTPException(status_code=400, detail=f"Dialect '{dialect}' is not supported for metadata analysis yet.")
```

**F. Update File-based Analysis Routing**:

```python
@app.post("/api/analyze")
async def analyze_directory(...):
    # ... existing code ...
    
    elif d in {"{new_dialect}"}:
        exit_code = analyzer_entry.run_{new_dialect}(
            sql_directory=str(base),
            output=str(output_dir),
            dialect="{new_dialect}",
            max_files=None,
            debug=False,
            openai_key=openai_key if openai_key else None,
        )
```

---

## Part 3: Extending Metadata-based Analysis

### Extending Metadata Extractors

To add new metadata extraction capabilities:

**Location**: `{dialect}/conn/enhanced_metadata_extractor.py`

**Example**: Adding query history extraction

```python
def extract_query_history(connection, limit: int = 1000) -> List[Dict]:
    """
    Extract recent query history from database.
    Dialect-specific implementation.
    """
    # Query system views/tables for query history
    # Return list of query dictionaries with:
    # - query_text
    # - execution_time
    # - timestamp
    # - user
    pass
```

### Extending Procedure Analyzers

To improve LLM-based procedure analysis:

**Location**: `{dialect}/conn/enhanced_procedure_analyzer.py`

**Example**: Adding custom prompts for specific procedure types

```python
def _build_analysis_prompt(self, procedure: Dict) -> str:
    """Build LLM prompt for procedure analysis"""
    # Customize prompt based on procedure type
    if procedure.get('type') == 'trigger':
        return self._build_trigger_prompt(procedure)
    elif procedure.get('type') == 'function':
        return self._build_function_prompt(procedure)
    else:
        return self._build_default_prompt(procedure)
```

### Adding New View Analysis Patterns

**Location**: `{dialect}/conn/metadata_view_analyzer.py`

Add support for dialect-specific view features:

```python
def _analyze_materialized_view(self, view_def: Dict) -> Dict:
    """Analyze materialized view with refresh logic"""
    # Extract refresh strategy
    # Analyze underlying query
    # Track dependencies
    pass
```

---

## Part 4: Server Extensions

### Adding New API Endpoints

**Location**: `Lineage_analyzer/server.py`

**Example**: Adding a batch analysis endpoint

```python
@app.post("/api/analyze/batch")
async def analyze_batch(
    requests: List[Dict],
    dialect: str = Query(...)
):
    """Analyze multiple databases in batch"""
    results = []
    for req in requests:
        # Route to appropriate analyzer
        result = await analyze_metadata_dynamic(dialect, Request(...))
        results.append(result)
    return JSONResponse({"results": results})
```

---

## Summary

### To Add New SQL Patterns to Existing Dialects:

1. **Cleaner**: Add regex pattern + validation (10-30 lines)
2. **Analyzer**: Add detection + specialized analysis method (50-100 lines)
3. **JSON Builder**: Update data structures + statistics + output (30-60 lines)

**Total**: ~100-200 lines per feature

### To Add New Database Dialect:

1. **File-based components**: ~500-800 lines
   - Main module, cleaner, analyzer, JSON builder

2. **Metadata-based components**: ~1000-1500 lines
   - MetadataLineageOrchestrator
   - Enhanced metadata extractor
   - View analyzer, procedure analyzer
   - Statement builder, JSON builder

3. **Server registration**: ~200-300 lines
   - Request models, endpoints, routing

**Total**: ~1700-2600 lines for complete dialect support

### Best Practices:

- Follow existing patterns from similar dialects
- Ensure output JSON format matches standard structure
- Test with real database connections
- Document dialect-specific features
- Add examples in `example_test.py` files

---

## Future Features List

- Additional database dialects (MySQL, DB2, Redshift, BigQuery)
- Incremental analysis (track changes over time)
- Real-time lineage updates
- Advanced visualization features
- Integration with data catalog tools
- Performance optimization for large databases
- Caching and incremental metadata updates
