"""
Metadata View Analyzer for Oracle
Analyzes views and query history SQL using traditional parsing (sqlglot).

This module provides the same analysis capabilities as EnhancedSQLAnalyzer
but optimized for working with database metadata instead of SQL files.

Oracle-specific features:
- CONNECT BY hierarchical queries
- PIVOT/UNPIVOT transformations
- MODEL clause for spreadsheet-like calculations
- Flashback queries (AS OF, VERSIONS BETWEEN)
- MERGE statements
- Oracle analytic functions (KEEP, WITHIN GROUP)
- Database link references (@dblink)
- Oracle outer join syntax (+)
"""

import re
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict

import sqlglot
from sqlglot import exp, parse_one


@dataclass
class ColumnLineage:
    """Column lineage information"""
    target_column: str
    target_table: str
    source_columns: List[Dict[str, str]] = field(default_factory=list)
    transform_type: str = "direct"
    expression: str = ""
    is_aggregate: bool = False
    is_calculated: bool = False
    cte_dependency: Optional[str] = None
    has_connect_by: bool = False
    has_pivot: bool = False
    has_model: bool = False


@dataclass
class ViewLineage:
    """Lineage for a view or query"""
    name: str
    sql_type: str
    target_table: Optional[str] = None
    source_tables: List[str] = field(default_factory=list)
    column_lineage: List[ColumnLineage] = field(default_factory=list)
    cte_definitions: Dict[str, Any] = field(default_factory=dict)
    temp_tables: List[str] = field(default_factory=list)
    global_temp_tables: List[str] = field(default_factory=list)
    is_dynamic: bool = False
    parse_error: Optional[str] = None
    statement_subtype: Optional[str] = None
    oracle_features: List[str] = field(default_factory=list)


class MetadataViewAnalyzer:
    """
    Analyze views and query history SQL extracted from Oracle metadata.

    Uses sqlglot for traditional parsing with full schema context from metadata.
    """

    def __init__(
        self,
        dialect: str = "oracle",
        metadata: Optional[Dict] = None,
        debug: bool = False
    ):
        """
        Initialize the analyzer.

        Args:
            dialect: SQL dialect (default: oracle)
            metadata: Database metadata for schema context
            debug: Enable debug output
        """
        self.dialect = dialect
        self.metadata = metadata or {}
        self.debug = debug

        # Build table and column lookup from metadata
        self.table_lookup = self._build_table_lookup()
        self.column_lookup = self._build_column_lookup()

        # Track temp tables
        self.global_temp_table_registry: Dict[str, Dict] = {}

        # Statistics
        self.stats = defaultdict(int)

        # Compile Oracle-specific patterns
        self._compile_patterns()

    def _build_table_lookup(self) -> Dict[str, Dict]:
        """Build table lookup from metadata"""
        lookup = {}

        if not self.metadata:
            return lookup

        # Index tables by name and qualified name
        for table in self.metadata.get('tables', []):
            owner = table.get('owner', '')
            name = table['name']
            qualified = f"{owner}.{name}" if owner else name

            lookup[name.upper()] = table
            lookup[qualified.upper()] = table

        return lookup

    def _build_column_lookup(self) -> Dict[str, List[str]]:
        """Build column lookup from metadata"""
        lookup = defaultdict(list)

        if not self.metadata:
            return lookup

        # Index columns by table
        for table in self.metadata.get('tables', []):
            owner = table.get('owner', '')
            table_name = table['name']
            qualified = f"{owner}.{table_name}" if owner else table_name

            for col in table.get('columns', []):
                col_name = col['name']
                lookup[qualified.upper()].append(col_name.upper())
                lookup[table_name.upper()].append(col_name.upper())

        return dict(lookup)

    def _compile_patterns(self):
        """Compile regex patterns for Oracle-specific detection"""
        # Oracle temporary tables
        self.global_temp_pattern = re.compile(
            r'CREATE\s+GLOBAL\s+TEMPORARY\s+TABLE\s+([\w\.\"]+)',
            re.IGNORECASE
        )

        # Oracle hierarchical queries
        self.connect_by_pattern = re.compile(r'\bCONNECT\s+BY\b', re.IGNORECASE)
        self.start_with_pattern = re.compile(r'\bSTART\s+WITH\b', re.IGNORECASE)
        self.prior_pattern = re.compile(r'\bPRIOR\b', re.IGNORECASE)
        self.level_pattern = re.compile(r'\bLEVEL\b', re.IGNORECASE)

        # PIVOT/UNPIVOT
        self.pivot_pattern = re.compile(r'\bPIVOT\b', re.IGNORECASE)
        self.unpivot_pattern = re.compile(r'\bUNPIVOT\b', re.IGNORECASE)

        # MODEL clause
        self.model_pattern = re.compile(r'\bMODEL\b', re.IGNORECASE)

        # Flashback queries
        self.flashback_pattern = re.compile(r'\bAS\s+OF\s+(?:SCN|TIMESTAMP)\b', re.IGNORECASE)
        self.versions_between_pattern = re.compile(r'\bVERSIONS\s+BETWEEN\b', re.IGNORECASE)

        # MERGE statement
        self.merge_pattern = re.compile(r'\bMERGE\s+INTO\b', re.IGNORECASE)

        # Database link references
        self.db_link_pattern = re.compile(r'@[\w\.\-]+', re.IGNORECASE)

        # Dual table
        self.dual_pattern = re.compile(r'\bFROM\s+DUAL\b', re.IGNORECASE)

        # Oracle outer join syntax
        self.oracle_outer_join_pattern = re.compile(r'\(\+\)', re.IGNORECASE)

        # Oracle-specific functions
        self.decode_pattern = re.compile(r'\bDECODE\s*\(', re.IGNORECASE)
        self.nvl_pattern = re.compile(r'\bNVL\s*\(', re.IGNORECASE)

    def analyze_view(self, view_name: str, view_sql: str, owner: str = "") -> ViewLineage:
        """
        Analyze a single view.

        Args:
            view_name: Name of the view
            view_sql: View SQL definition
            owner: Schema/owner of the view

        Returns:
            ViewLineage object
        """
        qualified_name = f"{owner}.{view_name}" if owner else view_name

        lineage = ViewLineage(
            name=qualified_name,
            sql_type="VIEW",
            target_table=qualified_name
        )

        # Detect Oracle features
        lineage.oracle_features = self._detect_oracle_features(view_sql)

        try:
            # Parse the SQL
            parsed = parse_one(view_sql, dialect=self.dialect)

            # Extract source tables
            lineage.source_tables = self._extract_tables(parsed)

            # Extract CTEs
            if isinstance(parsed, exp.Select) and parsed.args.get('with'):
                lineage.cte_definitions = self._extract_ctes(parsed.args['with'])

            # Extract column lineage
            lineage.column_lineage = self._extract_column_lineage(parsed, qualified_name, view_sql)

            self.stats['successful_parses'] += 1

        except Exception as e:
            if self.debug:
                print(f"Error parsing view {view_name}: {str(e)[:100]}")
            lineage.parse_error = str(e)
            self.stats['parse_errors'] += 1

        return lineage

    def analyze_views(self, views: List[Dict]) -> List[ViewLineage]:
        """
        Analyze multiple views from metadata.

        Args:
            views: List of view metadata dictionaries

        Returns:
            List of ViewLineage objects
        """
        results = []

        for view in views:
            view_name = view.get('view_name', '')
            owner = view.get('owner', '')
            definition = view.get('definition', '')

            if not definition:
                if self.debug:
                    print(f"Skipping view {view_name} - no definition")
                continue

            lineage = self.analyze_view(view_name, definition, owner)
            results.append(lineage)

        return results

    def _detect_oracle_features(self, sql: str) -> List[str]:
        """Detect Oracle-specific features in SQL"""
        features = []

        if self.connect_by_pattern.search(sql):
            features.append("CONNECT_BY")
        if self.pivot_pattern.search(sql):
            features.append("PIVOT")
        if self.unpivot_pattern.search(sql):
            features.append("UNPIVOT")
        if self.model_pattern.search(sql):
            features.append("MODEL")
        if self.flashback_pattern.search(sql):
            features.append("FLASHBACK")
        if self.versions_between_pattern.search(sql):
            features.append("VERSIONS_BETWEEN")
        if self.merge_pattern.search(sql):
            features.append("MERGE")
        if self.db_link_pattern.search(sql):
            features.append("DATABASE_LINK")
        if self.oracle_outer_join_pattern.search(sql):
            features.append("ORACLE_OUTER_JOIN")
        if self.dual_pattern.search(sql):
            features.append("DUAL_TABLE")
        if self.decode_pattern.search(sql):
            features.append("DECODE")

        return features

    def _extract_tables(self, expr: exp.Expression) -> List[str]:
        """Extract all table references from expression"""
        tables = set()

        for table in expr.find_all(exp.Table):
            table_name = self._get_table_name(table)
            if table_name and table_name.upper() != 'DUAL':
                tables.add(table_name)

        return sorted(list(tables))

    def _get_table_name(self, table: exp.Table) -> str:
        """Get fully qualified table name"""
        parts = []

        if table.catalog:
            parts.append(table.catalog)
        if table.db:
            parts.append(table.db)
        if table.name:
            parts.append(table.name)

        return '.'.join(parts) if parts else str(table)

    def _extract_ctes(self, with_expr: exp.With) -> Dict[str, Any]:
        """Extract CTE definitions"""
        ctes = {}

        for cte in with_expr.expressions:
            if isinstance(cte, exp.CTE):
                cte_name = cte.alias
                cte_query = cte.this

                cte_info = {
                    'name': cte_name,
                    'source_tables': self._extract_tables(cte_query),
                    'columns': []
                }

                # Try to get column names
                if hasattr(cte, 'args') and 'columns' in cte.args:
                    cte_info['columns'] = [col.name for col in cte.args['columns'].expressions]

                ctes[cte_name] = cte_info

        return ctes

    def _extract_column_lineage(
        self,
        select_expr: exp.Expression,
        target_table: str,
        sql: str
    ) -> List[ColumnLineage]:
        """Extract column-level lineage from SELECT"""
        lineages = []

        # Handle different expression types
        if isinstance(select_expr, exp.Select):
            if not hasattr(select_expr, 'expressions'):
                return lineages

            for projection in select_expr.expressions:
                col_lineage = self._analyze_projection(projection, target_table, sql)
                if col_lineage:
                    lineages.append(col_lineage)

        return lineages

    def _analyze_projection(
        self,
        projection: exp.Expression,
        target_table: str,
        sql: str
    ) -> Optional[ColumnLineage]:
        """Analyze a single projection/column"""
        # Get column alias or name
        if isinstance(projection, exp.Alias):
            col_name = projection.alias
            col_expr = projection.this
        elif isinstance(projection, exp.Column):
            col_name = projection.name
            col_expr = projection
        else:
            col_name = str(projection)
            col_expr = projection

        # Create lineage object
        lineage = ColumnLineage(
            target_column=col_name,
            target_table=target_table,
            expression=str(col_expr)
        )

        # Check for Oracle-specific features
        lineage.has_connect_by = bool(self.connect_by_pattern.search(str(col_expr)))
        lineage.has_pivot = bool(self.pivot_pattern.search(sql))
        lineage.has_model = bool(self.model_pattern.search(sql))

        # Detect column type
        if self._is_aggregate(col_expr):
            lineage.is_aggregate = True
            lineage.transform_type = "aggregate"
        elif self._is_calculated(col_expr):
            lineage.is_calculated = True
            lineage.transform_type = "calculated"

        # Extract source columns
        lineage.source_columns = self._extract_source_columns(col_expr)

        return lineage

    def _extract_source_columns(self, expr: exp.Expression) -> List[Dict[str, str]]:
        """Extract source columns from expression"""
        sources = []

        for col in expr.find_all(exp.Column):
            source = {
                'column': col.name,
                'table': col.table if hasattr(col, 'table') and col.table else 'UNKNOWN'
            }
            sources.append(source)

        return sources

    def _is_aggregate(self, expr: exp.Expression) -> bool:
        """Check if expression contains aggregate functions"""
        agg_functions = {
            exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max,
            exp.StddevPop, exp.StddevSamp, exp.VariancePop, exp.VarianceSamp
        }

        for func_type in agg_functions:
            if list(expr.find_all(func_type)):
                return True

        return False

    def _is_calculated(self, expr: exp.Expression) -> bool:
        """Check if expression is a calculation"""
        calc_types = {
            exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod,
            exp.Case, exp.If, exp.Coalesce
        }

        for calc_type in calc_types:
            if list(expr.find_all(calc_type)):
                return True

        return False

    def get_stats(self) -> Dict[str, int]:
        """Get analysis statistics"""
        return dict(self.stats)
