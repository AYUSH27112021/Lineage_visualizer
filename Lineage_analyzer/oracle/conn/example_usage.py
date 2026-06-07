"""
Example usage of Oracle Lineage Analyzer

This script demonstrates how to use the Oracle lineage analysis components.
"""

import sys
import getpass
from pathlib import Path

# Import the main components
from enhanced_metadata_extractor import extract_enhanced_database_metadata
from metadata_lineage_main import MetadataLineageOrchestrator


def example_1_full_analysis():
    """Example 1: Complete lineage analysis from database connection"""
    print("=" * 70)
    print("Example 1: Full Lineage Analysis")
    print("=" * 70)

    # Get connection parameters
    host = input("Oracle Host: ").strip() or "localhost"
    service_name = input("Service Name: ").strip() or "ORCL"
    username = input("Username: ").strip() or "hr"
    password = getpass.getpass("Password: ")
    port = int(input("Port (default 1521): ").strip() or "1521")

    # Optional: specify target schemas
    schemas_input = input("Target schemas (comma-separated, blank for current user): ").strip()
    target_schemas = [s.strip() for s in schemas_input.split(",")] if schemas_input else None

    # Create orchestrator
    orchestrator = MetadataLineageOrchestrator(
        host=host,
        service_name=service_name,
        username=username,
        password=password,
        port=port,
        output_directory="./lineage_output",
        target_schemas=target_schemas,
        debug=True
    )

    # Run analysis
    try:
        report = orchestrator.run()
        print("\n✓ Analysis completed successfully!")
        print(f"Report location: {orchestrator.output_directory}")
        return report
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def example_2_metadata_only():
    """Example 2: Extract metadata only"""
    print("=" * 70)
    print("Example 2: Metadata Extraction Only")
    print("=" * 70)

    # Get connection parameters
    host = input("Oracle Host: ").strip() or "localhost"
    service_name = input("Service Name: ").strip() or "ORCL"
    username = input("Username: ").strip() or "hr"
    password = getpass.getpass("Password: ")

    # Extract metadata
    try:
        metadata, file_path = extract_enhanced_database_metadata(
            host=host,
            service_name=service_name,
            username=username,
            password=password,
            output_dir=Path("./metadata_cache")
        )

        print("\n✓ Metadata extracted successfully!")
        print(f"Metadata file: {file_path}")
        print(f"\nSummary:")
        for key, value in metadata['summary'].items():
            print(f"  {key}: {value}")

        return metadata, file_path

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def example_3_use_cached_metadata():
    """Example 3: Use previously extracted metadata"""
    print("=" * 70)
    print("Example 3: Use Cached Metadata")
    print("=" * 70)

    metadata_file = input("Path to metadata JSON file: ").strip()

    if not Path(metadata_file).exists():
        print(f"Error: File not found: {metadata_file}")
        return

    # Get minimal connection info (needed for some operations)
    host = input("Oracle Host: ").strip() or "localhost"
    service_name = input("Service Name: ").strip() or "ORCL"
    username = input("Username: ").strip() or "hr"

    # Create orchestrator with cached metadata
    orchestrator = MetadataLineageOrchestrator(
        host=host,
        service_name=service_name,
        username=username,
        password="",  # Not needed when using cached metadata
        metadata_file_path=metadata_file,
        output_directory="./lineage_output",
        debug=True
    )

    # Run analysis
    try:
        report = orchestrator.run()
        print("\n✓ Analysis completed successfully!")
        return report
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def example_4_analyze_specific_schemas():
    """Example 4: Analyze specific schemas only"""
    print("=" * 70)
    print("Example 4: Analyze Specific Schemas")
    print("=" * 70)

    # Connection parameters
    host = "oracle-prod.company.com"
    service_name = "PRODDB"
    username = "readonly_user"
    password = getpass.getpass("Password: ")

    # Specify schemas to analyze
    target_schemas = ["SALES", "FINANCE", "HR"]

    print(f"\nAnalyzing schemas: {', '.join(target_schemas)}")

    orchestrator = MetadataLineageOrchestrator(
        host=host,
        service_name=service_name,
        username=username,
        password=password,
        target_schemas=target_schemas,
        output_directory="./prod_lineage",
        debug=True
    )

    try:
        report = orchestrator.run()
        print("\n✓ Analysis completed successfully!")

        # Print some statistics
        print("\nOracle-Specific Features Found:")
        oracle_info = report.get('oracle_specific', {})
        for feature, count in oracle_info.get('feature_usage', {}).items():
            print(f"  {feature}: {count}")

        return report

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def example_5_view_analysis():
    """Example 5: Analyze views from metadata"""
    print("=" * 70)
    print("Example 5: View Analysis")
    print("=" * 70)

    from metadata_view_analyzer import MetadataViewAnalyzer
    import json

    metadata_file = input("Path to metadata JSON file: ").strip()

    if not Path(metadata_file).exists():
        print(f"Error: File not found: {metadata_file}")
        return

    # Load metadata
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)

    # Create analyzer
    analyzer = MetadataViewAnalyzer(
        dialect="oracle",
        metadata=metadata,
        debug=True
    )

    # Analyze views
    views = metadata.get('views', [])
    print(f"\nAnalyzing {len(views)} views...")

    lineages = analyzer.analyze_views(views)

    # Print results
    print(f"\nSuccessfully analyzed {len(lineages)} views")

    for lineage in lineages[:5]:  # Show first 5
        print(f"\nView: {lineage.name}")
        print(f"  Source tables: {', '.join(lineage.source_tables)}")
        print(f"  Column count: {len(lineage.column_lineage)}")
        print(f"  Oracle features: {', '.join(lineage.oracle_features)}")

    return lineages


def main():
    """Main menu"""
    examples = {
        '1': ('Full Lineage Analysis', example_1_full_analysis),
        '2': ('Metadata Extraction Only', example_2_metadata_only),
        '3': ('Use Cached Metadata', example_3_use_cached_metadata),
        '4': ('Analyze Specific Schemas', example_4_analyze_specific_schemas),
        '5': ('View Analysis from Metadata', example_5_view_analysis),
    }

    print("\n" + "=" * 70)
    print("Oracle Lineage Analyzer - Examples")
    print("=" * 70)
    print("\nAvailable Examples:")
    for key, (name, _) in examples.items():
        print(f"  {key}. {name}")
    print("  q. Quit")

    choice = input("\nSelect example (1-5, q to quit): ").strip()

    if choice.lower() == 'q':
        print("Goodbye!")
        return

    if choice in examples:
        name, func = examples[choice]
        print(f"\nRunning: {name}\n")
        result = func()

        if result:
            print("\n✓ Example completed successfully!")
        else:
            print("\n✗ Example failed")
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
