"""
Enhanced Procedure Analyzer with LLM-based Lineage Extraction for Snowflake
Primary method: LLM analysis with table metadata context
Supports: Ollama and OpenAI with parallel async processing
Filters: Only procedures and functions (Snowflake stored procedures and UDFs)

Snowflake-specific features:
- JavaScript/Python/Java stored procedures
- SQL/JavaScript/Python UDFs
- Variant/JSON handling
- Streams and Tasks
"""

import json
import re
import asyncio
import aiohttp
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict
import sys
from concurrent.futures import ThreadPoolExecutor

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


class EnhancedLLMLineageAnalyzer:
    """
    Advanced SQL lineage analyzer using LLM as primary analysis method.
    Supports parallel async processing with both Ollama and OpenAI.
    Only processes stored procedures and functions.

    Snowflake-specific handling for:
    - Multi-language procedures (JavaScript, Python, Java, Scala, SQL)
    - UDFs (scalar and table-valued)
    - Variant/semi-structured data access
    """

    def __init__(
        self,
        metadata: Dict[str, Any],
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:14b",
        openai_api_key: Optional[str] = None,
        openai_model: str = "gpt-4o-mini",
        batch_size: int = 10,
        timeout: int = 300,
    ):
        """
        Initialize the analyzer.

        Args:
            metadata: Database metadata dictionary with tables, procedures, functions
            ollama_url: Ollama API endpoint
            ollama_model: Ollama model name
            openai_api_key: OpenAI API key (if provided, uses OpenAI; otherwise Ollama)
            openai_model: OpenAI model name
            batch_size: Number of parallel requests (default: 10)
            timeout: Request timeout in seconds
        """
        self.metadata = metadata
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.openai_api_key = openai_api_key
        self.openai_model = openai_model
        self.batch_size = batch_size
        self.timeout = timeout

        # Determine which API to use
        self.use_openai = bool(openai_api_key)

        # Initialize AsyncOpenAI client if OpenAI is being used
        if self.use_openai:
            if AsyncOpenAI is None:
                raise ImportError("openai library is required for OpenAI support. Install it with: pip install openai")
            self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
        else:
            self.openai_client = None

        # Build comprehensive table metadata index for LLM context
        self.table_metadata_index = self._build_table_metadata_index()

        # Statistics
        self.stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'procedures': 0,
            'functions': 0,
            'skipped': 0
        }

    def _build_table_metadata_index(self) -> Dict[str, Dict[str, Any]]:
        """
        Build a comprehensive table metadata index with full column details.
        """
        index = {}

        # Index tables
        tables = self.metadata.get("tables", [])
        for table in tables:
            schema = table.get("schema") or table.get("schema_name") or "PUBLIC"
            name = table.get("name") or table.get("table_name")

            if not name:
                continue

            # Create various name formats for flexible lookup
            qualified_name = f"{schema}.{name}"
            qualified_name_quoted = f'"{schema}"."{name}"'

            # Extract column information with data types
            columns = []
            for col in table.get("columns", []):
                if isinstance(col, dict):
                    col_info = {
                        "name": col.get("name") or col.get("column_name"),
                        "data_type": col.get("data_type"),
                        "is_nullable": col.get("is_nullable"),
                        "is_primary_key": col.get("is_primary_key", False),
                        "is_foreign_key": col.get("is_foreign_key", False)
                    }
                    columns.append(col_info)

            # Store comprehensive table information
            table_entry = {
                "schema": schema,
                "name": name,
                "qualified_name": qualified_name,
                "qualified_name_quoted": qualified_name_quoted,
                "columns": columns,
                "type": "TABLE",
                "row_count": table.get("row_count", 0)
            }

            # Add multiple lookup keys for flexible matching
            index[qualified_name.lower()] = table_entry
            index[qualified_name_quoted.lower()] = table_entry
            index[name.lower()] = table_entry

        # Also index views
        views = self.metadata.get("views", [])
        for view in views:
            schema = view.get("schema_name") or "PUBLIC"
            name = view.get("view_name")

            if not name:
                continue

            qualified_name = f"{schema}.{name}"

            view_entry = {
                "schema": schema,
                "name": name,
                "qualified_name": qualified_name,
                "columns": [],
                "type": "VIEW"
            }

            index[qualified_name.lower()] = view_entry
            index[name.lower()] = view_entry

        unique_objects = len(set(id(v) for v in index.values()))
        print(f"✓ Built metadata index: {unique_objects} unique tables/views")
        return index

    def _extract_table_references(self, sql: str) -> List[str]:
        """Extract all table references from SQL."""
        if not sql:
            return []

        normalized_sql = sql.lower()
        referenced = set()

        # Pattern 1: schema.table (Snowflake style)
        dot_pattern = r'\b(\w+)\.(\w+)\b'
        for match in re.finditer(dot_pattern, normalized_sql):
            schema, table = match.groups()
            ref = f"{schema}.{table}"
            if ref.lower() in self.table_metadata_index:
                referenced.add(ref)

        # Pattern 2: "schema"."table" (quoted identifiers)
        quoted_pattern = r'"(\w+)"\.?"(\w+)"'
        for match in re.finditer(quoted_pattern, normalized_sql):
            schema, table = match.groups()
            ref = f"{schema}.{table}"
            referenced.add(ref)

        # Pattern 3: Standalone table names
        for table_key, table_info in self.table_metadata_index.items():
            table_name = table_info['name'].lower()
            pattern = rf'\b{re.escape(table_name)}\b'
            if re.search(pattern, normalized_sql):
                referenced.add(table_info['qualified_name'])

        return list(referenced)

    def _get_table_context(self, table_references: List[str]) -> Dict[str, Dict[str, Any]]:
        """Retrieve full table metadata for all referenced tables."""
        context = {}

        for table_ref in table_references:
            table_ref_lower = table_ref.lower()

            if table_ref_lower in self.table_metadata_index:
                table_info = self.table_metadata_index[table_ref_lower]
                key = table_info['qualified_name']
                context[key] = {
                    "schema": table_info['schema'],
                    "name": table_info['name'],
                    "columns": table_info['columns'],
                    "type": table_info['type']
                }

        return context

    def _format_table_context_for_prompt(self, table_context: Dict[str, Dict[str, Any]]) -> str:
        """Format table metadata context in a clear, LLM-friendly format."""
        if not table_context:
            return "No table metadata available."

        formatted = []
        for table_name, table_info in table_context.items():
            formatted.append(f"\nTable: {table_name}")
            formatted.append(f"  Type: {table_info['type']}")
            formatted.append(f"  Columns:")

            for col in table_info['columns']:
                col_name = col['name']
                col_type = col['data_type']
                nullable = "NULL" if col.get('is_nullable') else "NOT NULL"
                pk = " (PRIMARY KEY)" if col.get('is_primary_key') else ""
                fk = " (FOREIGN KEY)" if col.get('is_foreign_key') else ""

                formatted.append(f"    - {col_name}: {col_type} {nullable}{pk}{fk}")

        return "\n".join(formatted)

    def _get_all_tables_list(self) -> str:
        """Get a list of all available tables in the database."""
        if not self.table_metadata_index:
            return "No table metadata available."

        all_tables = []
        for table_info in self.table_metadata_index.values():
            table_name = table_info['qualified_name']
            all_tables.append(table_name)

        all_tables.sort()

        if len(all_tables) == 0:
            return "No tables found in metadata."

        return ", ".join(all_tables)

    def _create_enhanced_prompt(
        self,
        sql: str,
        statement_type: str,
        statement_name: str,
        table_context: Dict[str, Dict[str, Any]],
        language: str = "SQL"
    ) -> str:
        """Create an optimized prompt for LLM lineage analysis."""

        table_context_str = self._format_table_context_for_prompt(table_context)
        all_tables_list = self._get_all_tables_list()

        prompt = f"""Analyze this Snowflake {statement_type} and extract column level data lineage. Return ONLY valid JSON.

**{statement_type.upper()}:** {statement_name}
**LANGUAGE:** {language}

**CODE:**
```
{sql}
```

**ALL AVAILABLE TABLES:** {all_tables_list}

**TABLE METADATA:**
{table_context_str}

**REQUIRED JSON STRUCTURE:**
{{
  "source_tables": [
    {{
      "table_list": "schema.table_name",
      "columns_used": ["column1", "column2"]
    }}
  ],
  "target": {{
    "name": "schema.table_name",
    "operation": "INSERT|UPDATE|DELETE|CREATE|MERGE",
    "columns_affected": ["column1", "column2"]
  }},
  "column_lineage": [
    {{
      "target_column": "target_table.column_name",
      "source_columns": [
        {{
          "table_list": "source_table",
          "column": "column_name"
        }}
      ],
      "transformation": {{
        "type": "DIRECT|CALCULATION|AGGREGATION|CASE|JSON_ACCESS"
      }}
    }}
  ],
  "dependencies": {{
    "tables": ["schema.table1"],
    "procedures": ["procedure1"],
    "functions": ["function1"],
    "streams": ["stream1"],
    "tasks": ["task1"]
  }},
  "complexity_metrics": {{
    "num_tables": 0,
    "num_joins": 0,
    "num_calculations": 0,
    "has_aggregation": false,
    "has_window_functions": false,
    "has_subqueries": false,
    "has_cte": false,
    "has_variant_access": false,
    "has_lateral_flatten": false
  }}
}}

**SNOWFLAKE-SPECIFIC RULES:**

**TABLE AND SCHEMA:**
1. ONLY use tables from "ALL AVAILABLE TABLES" list
2. Default schema is PUBLIC if not specified
3. Fully qualify table names as schema.table_name
4. Use "table_list" key (not "table") in JSON response

**SEMI-STRUCTURED DATA (VARIANT/OBJECT/ARRAY):**
5. Handle variant/JSON access patterns: column:path:to:value or column['key']
6. Type casting with ::TYPE (e.g., col:data::STRING, col:amount::NUMBER)
7. Identify LATERAL FLATTEN operations on arrays/objects
8. Track PARSE_JSON, TO_VARIANT, TO_JSON, TRY_PARSE_JSON functions
9. Handle OBJECT_CONSTRUCT, ARRAY_CONSTRUCT, ARRAY_AGG, OBJECT_AGG
10. GET, GET_PATH for variant traversal

**TIME TRAVEL AND VERSIONING:**
11. Detect time travel queries: AT(TIMESTAMP=>...), BEFORE(STATEMENT=>...)
12. Track CHANGES clause for stream-like queries
13. CLONE operations with time travel

**STREAMS AND TASKS:**
14. Track stream dependencies and SYSTEM$STREAM_HAS_DATA()
15. Identify task chains and predecessors
16. METADATA$ACTION, METADATA$ISUPDATE, METADATA$ROW_ID columns

**DATA LOADING:**
17. COPY INTO from stages (@stage_name)
18. External table references
19. File format specifications

**WINDOW FUNCTIONS AND ANALYTICS:**
20. QUALIFY clause for window function filtering
21. MATCH_RECOGNIZE for pattern matching
22. All window functions: ROW_NUMBER, RANK, LAG, LEAD, etc.

**SNOWFLAKE FUNCTIONS:**
23. IFF, NVL, NVL2, DECODE, NULLIF, ZEROIFNULL
24. DATEADD, DATEDIFF, DATE_TRUNC, TIME_SLICE, CONVERT_TIMEZONE
25. SPLIT_PART, STRTOK, REGEXP_REPLACE, REGEXP_SUBSTR
26. TRY_CAST, TRY_TO_NUMBER, TRY_TO_DATE (safe casting)
27. HASH, MD5, SHA1, SHA2 for hashing
28. Geospatial: ST_* functions, TO_GEOGRAPHY, TO_GEOMETRY

**SET OPERATIONS AND SAMPLING:**
29. UNION, INTERSECT, EXCEPT, MINUS
30. SAMPLE and TABLESAMPLE clauses
31. PIVOT and UNPIVOT operations

**STORED PROCEDURES:**
32. For JavaScript procedures, extract SQL from: snowflake.execute({{sqlText: `...`}})
33. For Python procedures, extract SQL from: session.sql("...") or cursor.execute("...")
34. For Java/Scala procedures, extract SQL from String literals with SQL keywords

**POLICIES AND SECURITY:**
35. Track masking policy applications
36. Row access policy references
37. Secure views (SECURE VIEW)

**GENERATORS AND SEQUENCES:**
38. GENERATOR(ROWCOUNT => N) for test data
39. sequence_name.NEXTVAL for sequence usage

**RESULT PROCESSING:**
40. RESULT_SCAN(LAST_QUERY_ID()) for query result reuse

**OUTPUT FORMAT:**
- Return ONLY valid JSON, no markdown or other text
- All table names must exist in "ALL AVAILABLE TABLES"
- transformation.type should be: DIRECT, CALCULATION, AGGREGATION, CASE, JSON_ACCESS, FLATTEN, WINDOW, CAST, CONDITIONAL, or FUNCTION"""

        return prompt

    async def _call_ollama_async(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        procedure_name: str = "unknown",
        timeout_override: Optional[int] = None
    ) -> Dict[str, Any]:
        """Call Ollama API asynchronously for lineage analysis."""

        timeout_value = timeout_override if timeout_override is not None else self.timeout

        try:
            async with session.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_predict": 4096
                    }
                },
                timeout=aiohttp.ClientTimeout(total=timeout_value)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    return {"error": f"Ollama API error {response.status}: {error_text}"}

                result = await response.json()
                response_text = result.get("response", "")

                # Parse JSON response
                try:
                    response_text = response_text.strip()
                    if response_text.startswith("```json"):
                        response_text = response_text[7:]
                    if response_text.startswith("```"):
                        response_text = response_text[3:]
                    if response_text.endswith("```"):
                        response_text = response_text[:-3]
                    response_text = response_text.strip()

                    return json.loads(response_text)
                except json.JSONDecodeError as e:
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        try:
                            return json.loads(json_match.group())
                        except:
                            pass
                    return {"error": f"Failed to parse JSON: {str(e)}", "raw_response": response_text[:500]}

        except asyncio.TimeoutError:
            return {
                "error": f"Ollama request timeout after {timeout_value}s for procedure '{procedure_name}'.",
                "timeout_seconds": timeout_value,
                "procedure_name": procedure_name
            }
        except Exception as e:
            return {
                "error": f"Ollama API error for procedure '{procedure_name}': {str(e)}",
                "procedure_name": procedure_name
            }

    async def _call_openai_async(
        self,
        session: Optional[aiohttp.ClientSession],
        prompt: str,
        procedure_name: str = "unknown",
        timeout_override: Optional[int] = None
    ) -> Dict[str, Any]:
        """Call OpenAI API asynchronously for lineage analysis."""

        if not self.openai_client:
            return {
                "error": "OpenAI client not initialized",
                "procedure_name": procedure_name
            }

        timeout_value = timeout_override if timeout_override is not None else self.timeout

        try:
            response = await asyncio.wait_for(
                self.openai_client.chat.completions.create(
                    model=self.openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a Snowflake SQL lineage analysis expert. Return only valid JSON responses."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    temperature=0.1,
                    max_tokens=4096,
                    response_format={"type": "json_object"}
                ),
                timeout=timeout_value
            )

            content = response.choices[0].message.content or "{}"

            try:
                return json.loads(content)
            except json.JSONDecodeError as e:
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group())
                    except:
                        pass
                return {"error": f"Failed to parse JSON: {str(e)}", "raw_response": content[:500]}

        except asyncio.TimeoutError:
            return {
                "error": f"OpenAI request timeout after {timeout_value}s for procedure '{procedure_name}'.",
                "timeout_seconds": timeout_value,
                "procedure_name": procedure_name
            }
        except Exception as e:
            return {
                "error": f"OpenAI API error for procedure '{procedure_name}': {str(e)}",
                "procedure_name": procedure_name
            }

    def _is_procedure_or_function(self, statement: Dict[str, Any]) -> bool:
        """Filter to only process procedures, functions, and tasks."""
        stmt_type = statement.get('type', '').upper()

        accepted_types = ['PROCEDURE', 'FUNCTION', 'STORED_PROCEDURE', 'UDF',
                         'UDTF', 'SQL_FUNCTION', 'JAVASCRIPT_FUNCTION',
                         'PYTHON_FUNCTION', 'TASK']

        return stmt_type in accepted_types

    async def _analyze_statement_async(
        self,
        session: aiohttp.ClientSession,
        statement: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze a single SQL statement asynchronously using LLM."""

        if not self._is_procedure_or_function(statement):
            self.stats['skipped'] += 1
            return None

        sql = statement.get('modified_sql') or statement.get('original_sql', '')
        stmt_type = statement.get('type', 'UNKNOWN')
        stmt_name = statement.get('name', 'unnamed')
        language = statement.get('language', 'SQL')

        # Calculate dynamic timeout
        sql_length = len(sql)
        base_timeout = self.timeout
        dynamic_timeout = min(base_timeout + (sql_length // 1000), base_timeout * 2)

        # Extract all table references
        table_references = self._extract_table_references(sql)

        # Get full metadata for all referenced tables
        table_context = self._get_table_context(table_references)

        # Create enhanced prompt
        prompt = self._create_enhanced_prompt(sql, stmt_type, stmt_name, table_context, language)

        # Call appropriate LLM API
        if self.use_openai:
            lineage_result = await self._call_openai_async(session, prompt, stmt_name, dynamic_timeout)
        else:
            lineage_result = await self._call_ollama_async(session, prompt, stmt_name, dynamic_timeout)

        if isinstance(lineage_result, dict) and isinstance(lineage_result.get('raw_response'), str):
            llm_raw_response = lineage_result['raw_response']
        else:
            try:
                llm_raw_response = json.dumps(lineage_result, indent=2, ensure_ascii=False)
            except Exception:
                llm_raw_response = str(lineage_result)

        # Update statistics
        if stmt_type.upper() in ['PROCEDURE', 'STORED_PROCEDURE']:
            self.stats['procedures'] += 1
        elif 'FUNCTION' in stmt_type.upper() or stmt_type.upper() in ['UDF', 'UDTF']:
            self.stats['functions'] += 1

        # Build comprehensive result
        result = {
            **statement,
            'type': stmt_type,
            'lineage_analysis': lineage_result,
            'llm_prompt': prompt,
            'llm_raw_response': llm_raw_response,
            'analyzed_at': datetime.utcnow().isoformat(),
            'table_context_used': list(table_context.keys()),
            'analysis_method': 'LLM',
            'llm_provider': 'OpenAI' if self.use_openai else 'Ollama',
            'analysis_success': 'error' not in lineage_result
        }

        return result

    async def _process_batch(
        self,
        statements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Process a batch of statements."""

        processed_results = []

        if self.use_openai:
            tasks = [
                self._analyze_statement_async(None, stmt)
                for stmt in statements
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if result is None:
                    continue
                elif isinstance(result, Exception):
                    error_result = {
                        **statements[i],
                        'lineage_analysis': {'error': f'Processing exception: {str(result)}'},
                        'analyzed_at': datetime.utcnow().isoformat(),
                        'analysis_success': False
                    }
                    processed_results.append(error_result)
                else:
                    processed_results.append(result)
        else:
            async with aiohttp.ClientSession() as session:
                for i, stmt in enumerate(statements):
                    try:
                        result = await self._analyze_statement_async(session, stmt)
                        if result is not None:
                            processed_results.append(result)
                    except Exception as e:
                        error_result = {
                            **stmt,
                            'lineage_analysis': {'error': f'Processing exception: {str(e)}'},
                            'analyzed_at': datetime.utcnow().isoformat(),
                            'analysis_success': False
                        }
                        processed_results.append(error_result)

        return processed_results

    async def analyze_statements_async(
        self,
        statements: List[Dict[str, Any]],
        show_progress: bool = True
    ) -> List[Dict[str, Any]]:
        """Analyze multiple SQL statements with parallel LLM processing."""

        filtered_statements = [s for s in statements if self._is_procedure_or_function(s)]

        results = []
        total_statements = len(filtered_statements)
        original_count = len(statements)
        skipped_count = original_count - total_statements

        print(f"\n{'='*80}")
        print(f"LLM-BASED LINEAGE ANALYSIS (Snowflake)")
        print(f"{'='*80}")
        print(f"Total statements provided: {original_count}")
        print(f"Filtered (procedures & functions): {total_statements}")
        print(f"Skipped (views, queries, etc.): {skipped_count}")
        processing_mode = "parallel" if self.use_openai else "sequential"
        print(f"Batch size: {self.batch_size} ({processing_mode})")
        print(f"LLM Provider: {'OpenAI' if self.use_openai else 'Ollama'}")
        print(f"Model: {self.openai_model if self.use_openai else self.ollama_model}")
        print(f"{'='*80}\n")

        if total_statements == 0:
            print("⚠ No procedures or functions found to analyze.")
            return []

        for i in range(0, total_statements, self.batch_size):
            batch = filtered_statements[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (total_statements + self.batch_size - 1) // self.batch_size

            print(f"📦 Batch {batch_num}/{total_batches} ({len(batch)} statements)...", end=" ")
            sys.stdout.flush()

            try:
                batch_results = await self._process_batch(batch)
                results.extend(batch_results)

                self.stats['total_processed'] += len(batch)
                success_count = sum(1 for r in batch_results if r.get('analysis_success'))
                self.stats['successful'] += success_count
                self.stats['failed'] += len(batch_results) - success_count

                print(f"✓ Success: {success_count}/{len(batch)}")

            except Exception as e:
                print(f"✗ Error: {str(e)}")
                for stmt in batch:
                    error_result = {
                        **stmt,
                        'lineage_analysis': {'error': f'Batch processing error: {str(e)}'},
                        'analyzed_at': datetime.utcnow().isoformat(),
                        'analysis_success': False
                    }
                    results.append(error_result)
                self.stats['failed'] += len(batch)

        print(f"\n{'='*80}")
        self._print_final_statistics()
        print(f"{'='*80}\n")

        return results

    def analyze_statements(
        self,
        statements: List[Dict[str, Any]],
        show_progress: bool = True
    ) -> List[Dict[str, Any]]:
        """Synchronous wrapper for analyze_statements_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    lambda: asyncio.run(self.analyze_statements_async(statements, show_progress))
                )
                return future.result()

        return asyncio.run(self.analyze_statements_async(statements, show_progress))

    def _print_final_statistics(self):
        """Print final analysis statistics."""
        total = self.stats['total_processed']
        if total == 0:
            return

        success_rate = (self.stats['successful'] / total * 100) if total > 0 else 0

        print(f"\n📊 ANALYSIS SUMMARY:")
        print(f"   Total Processed: {total}")
        print(f"   ✓ Successful: {self.stats['successful']} ({success_rate:.1f}%)")
        print(f"   ✗ Failed: {self.stats['failed']} ({100-success_rate:.1f}%)")
        print(f"   📝 Procedures: {self.stats['procedures']}")
        print(f"   🔧 Functions: {self.stats['functions']}")
        if self.stats['skipped'] > 0:
            print(f"   ⊘ Skipped: {self.stats['skipped']}")

    def print_statistics(self):
        """Print detailed analysis statistics."""
        print(f"\n{'='*80}")
        print("ANALYSIS STATISTICS")
        print(f"{'='*80}")
        self._print_final_statistics()
        print(f"{'='*80}\n")


def main():
    """Main execution function for testing."""

    print("Enhanced LLM-Based Procedure Analyzer (Snowflake)")
    print("=" * 80)
    print("\nFeatures:")
    print("  ✓ LLM-based lineage analysis (primary method)")
    print("  ✓ Dual API support: Ollama & OpenAI")
    print("  ✓ Parallel async processing")
    print("  ✓ Snowflake-specific: Variant access, LATERAL FLATTEN")
    print("  ✓ Multi-language procedures (SQL, JavaScript, Python)")
    print("\nUsage:")
    print("  # With Ollama (default)")
    print("  analyzer = EnhancedLLMLineageAnalyzer(metadata=metadata)")
    print()
    print("  # With OpenAI")
    print("  analyzer = EnhancedLLMLineageAnalyzer(")
    print("      metadata=metadata,")
    print("      openai_api_key='your-key'")
    print("  )")
    print()
    print("  results = analyzer.analyze_statements(statements)")


if __name__ == "__main__":
    main()
