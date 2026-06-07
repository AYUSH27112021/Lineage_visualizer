"""Example usage of the Enhanced Teradata Metadata Extractor.

This script demonstrates various ways to use the metadata extractor.
"""

import sys
from pathlib import Path
from enhanced_metadata_extractor import (
    extract_enhanced_database_metadata,
    build_connection_params,
    save_metadata_to_file,
)


def example_basic_extraction():
    """Basic metadata extraction example."""
    print("=" * 70)
    print("Example 1: Basic Metadata Extraction")
    print("=" * 70)

    try:
        metadata, file_path = extract_enhanced_database_metadata(
            host="teradata.company.com",
            database="SAMPLE_DB",
            username="your_username",
            password="your_password",
            logmech="TD2",
        )

        print(f"\nExtraction successful!")
        print(f"Metadata saved to: {file_path}")
        print(f"\nSummary:")
        for key, value in metadata["summary"].items():
            print(f"  {key}: {value}")

    except Exception as e:
        print(f"Error: {e}")


def example_with_statistics():
    """Metadata extraction with table statistics."""
    print("\n" + "=" * 70)
    print("Example 2: Metadata Extraction with Statistics")
    print("=" * 70)

    try:
        metadata, file_path = extract_enhanced_database_metadata(
            host="teradata.company.com",
            database="SAMPLE_DB",
            username="your_username",
            password="your_password",
            logmech="TD2",
            extract_statistics=True,  # Extract row counts and space usage
        )

        print(f"\nExtraction successful!")
        print(f"Metadata saved to: {file_path}")

        # Show table statistics
        print("\nTable Statistics:")
        for table in metadata["tables"][:5]:  # Show first 5 tables
            stats = table.get("statistics", {})
            print(f"  {table['name']}:")
            print(f"    Rows: {stats.get('row_count', 'N/A')}")
            print(f"    Size: {stats.get('current_perm_bytes', 0):,} bytes")

    except Exception as e:
        print(f"Error: {e}")


def example_with_ldap_authentication():
    """Metadata extraction using LDAP authentication."""
    print("\n" + "=" * 70)
    print("Example 3: LDAP Authentication")
    print("=" * 70)

    try:
        metadata, file_path = extract_enhanced_database_metadata(
            host="teradata.company.com",
            database="SAMPLE_DB",
            username="domain\\username",  # LDAP username format
            password="your_password",
            logmech="LDAP",  # Use LDAP authentication
            encryptdata=True,  # Enable encryption
        )

        print(f"\nExtraction successful!")
        print(f"Metadata saved to: {file_path}")

    except Exception as e:
        print(f"Error: {e}")


def example_custom_connection_params():
    """Using custom connection parameters."""
    print("\n" + "=" * 70)
    print("Example 4: Custom Connection Parameters")
    print("=" * 70)

    # Build connection parameters separately
    conn_params = build_connection_params(
        host="teradata.company.com",
        database="SAMPLE_DB",
        username="your_username",
        password="your_password",
        logmech="TD2",
        encryptdata=True,
        charset="UTF8",
        tmode="ANSI",  # Can be ANSI or TERA
    )

    print("Connection parameters:")
    for key, value in conn_params.items():
        if key != "password":  # Don't print password
            print(f"  {key}: {value}")


def example_custom_output_directory():
    """Metadata extraction with custom output directory."""
    print("\n" + "=" * 70)
    print("Example 5: Custom Output Directory")
    print("=" * 70)

    output_dir = Path("/tmp/teradata_metadata")

    try:
        metadata, file_path = extract_enhanced_database_metadata(
            host="teradata.company.com",
            database="SAMPLE_DB",
            username="your_username",
            password="your_password",
            logmech="TD2",
            output_dir=output_dir,
        )

        print(f"\nExtraction successful!")
        print(f"Metadata saved to: {file_path}")

    except Exception as e:
        print(f"Error: {e}")


def example_analyzing_metadata():
    """Analyzing extracted metadata."""
    print("\n" + "=" * 70)
    print("Example 6: Analyzing Extracted Metadata")
    print("=" * 70)

    try:
        metadata, file_path = extract_enhanced_database_metadata(
            host="teradata.company.com",
            database="SAMPLE_DB",
            username="your_username",
            password="your_password",
            logmech="TD2",
        )

        print(f"\nExtraction successful!")

        # Analyze tables
        print("\nTable Analysis:")
        tables_with_fk = [t for t in metadata["tables"] if t["foreign_keys"]]
        tables_with_pk = [t for t in metadata["tables"] if t["primary_key"]]

        print(f"  Total tables: {len(metadata['tables'])}")
        print(f"  Tables with primary keys: {len(tables_with_pk)}")
        print(f"  Tables with foreign keys: {len(tables_with_fk)}")

        # Analyze columns
        print("\nColumn Analysis:")
        total_columns = sum(len(t["columns"]) for t in metadata["tables"])
        nullable_columns = sum(
            sum(1 for c in t["columns"] if c["is_nullable"])
            for t in metadata["tables"]
        )

        print(f"  Total columns: {total_columns}")
        print(f"  Nullable columns: {nullable_columns}")
        print(f"  Not nullable columns: {total_columns - nullable_columns}")

        # Analyze data types
        print("\nData Type Distribution:")
        data_types = {}
        for table in metadata["tables"]:
            for column in table["columns"]:
                dtype = column["data_type"]
                data_types[dtype] = data_types.get(dtype, 0) + 1

        for dtype, count in sorted(data_types.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {dtype}: {count}")

        # Analyze procedures and functions
        print("\nProcedures and Functions:")
        print(f"  Procedures: {len(metadata['procedures'])}")
        print(f"  Functions: {len(metadata['functions'])}")
        print(f"  Macros: {len(metadata['macros'])}")

        # Find tables with most dependencies
        print("\nTables with Most Dependencies:")
        tables_by_deps = sorted(
            metadata["tables"],
            key=lambda t: len(t["dependencies"]["depends_on"]),
            reverse=True
        )

        for table in tables_by_deps[:5]:
            deps = table["dependencies"]["depends_on"]
            refs = table["dependencies"]["referenced_by"]
            print(f"  {table['name']}:")
            print(f"    Depends on: {len(deps)} tables")
            print(f"    Referenced by: {len(refs)} tables")

    except Exception as e:
        print(f"Error: {e}")


def example_parser_support():
    """Using parser support features."""
    print("\n" + "=" * 70)
    print("Example 7: Parser Support Features")
    print("=" * 70)

    try:
        metadata, file_path = extract_enhanced_database_metadata(
            host="teradata.company.com",
            database="SAMPLE_DB",
            username="your_username",
            password="your_password",
            logmech="TD2",
        )

        print(f"\nExtraction successful!")

        # Use table disambiguation
        print("\nTable Disambiguation:")
        table_map = metadata["parser_support"]["table_disambiguation"]

        print(f"  Unique tables: {len(table_map['unique_tables'])}")
        print(f"  Ambiguous tables: {len(table_map['ambiguous_tables'])}")

        # Show some ambiguous tables
        if table_map['ambiguous_tables']:
            print("\n  Example ambiguous table names:")
            for table_name, qualified_names in list(table_map['ambiguous_tables'].items())[:3]:
                print(f"    {table_name}: {qualified_names}")

        # Use column map
        print("\nColumn Map:")
        column_map = metadata["parser_support"]["column_map"]

        print(f"  Unique columns: {len(column_map['unique_columns'])}")
        print(f"  Total column names: {len(column_map['by_column_name'])}")

        # Show most common column names
        print("\n  Most common column names:")
        common_columns = sorted(
            column_map['by_column_name'].items(),
            key=lambda x: len(x[1]),
            reverse=True
        )

        for col_name, tables in common_columns[:5]:
            print(f"    {col_name}: appears in {len(tables)} tables")

    except Exception as e:
        print(f"Error: {e}")


def example_error_handling():
    """Demonstrating error handling and retries."""
    print("\n" + "=" * 70)
    print("Example 8: Error Handling with Retries")
    print("=" * 70)

    try:
        metadata, file_path = extract_enhanced_database_metadata(
            host="teradata.company.com",
            database="SAMPLE_DB",
            username="your_username",
            password="your_password",
            logmech="TD2",
            max_retries=5,
            initial_retry_delay=3.0,
        )

        print(f"\nExtraction successful!")
        print(f"Metadata saved to: {file_path}")

    except Exception as e:
        print(f"Error: {e}")
        print("\nPossible solutions:")
        print("  1. Check network connectivity")
        print("  2. Verify credentials")
        print("  3. Ensure user has necessary privileges")
        print("  4. Check if database name is correct")


def example_save_metadata():
    """Saving metadata to custom location."""
    print("\n" + "=" * 70)
    print("Example 9: Saving Metadata with Custom Filename")
    print("=" * 70)

    # Assume we already have metadata
    metadata = {
        "database": "SAMPLE_DB",
        "host": "teradata.company.com",
        "tables": [],
        "views": [],
        "procedures": [],
        "functions": [],
        "macros": [],
        "summary": {},
    }

    try:
        # Save with custom filename
        file_path = save_metadata_to_file(
            metadata=metadata,
            output_dir=Path("/tmp/teradata_metadata"),
            filename="my_custom_metadata.json",
        )

        print(f"Metadata saved to: {file_path}")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Enhanced Teradata Metadata Extractor - Usage Examples")
    print("=" * 70)
    print("\nNote: These examples use placeholder credentials.")
    print("Replace with actual credentials before running.")
    print("\n" + "=" * 70)

    # Run examples (commented out to avoid errors with placeholder credentials)
    # Uncomment the examples you want to run after updating credentials

    # example_basic_extraction()
    # example_with_statistics()
    # example_with_ldap_authentication()
    example_custom_connection_params()
    # example_custom_output_directory()
    # example_analyzing_metadata()
    # example_parser_support()
    # example_error_handling()
    example_save_metadata()

    print("\n" + "=" * 70)
    print("Examples complete!")
    print("=" * 70)
