"""
Example Usage of Teradata Metadata Lineage Orchestrator

This file demonstrates various ways to use the MetadataLineageOrchestrator
for Teradata database lineage analysis.
"""

from metadata_lineage_main import MetadataLineageOrchestrator
import json
from pathlib import Path


def example_basic_usage():
    """
    Example 1: Basic usage with minimal configuration
    """
    print("\n" + "="*80)
    print("EXAMPLE 1: Basic Usage")
    print("="*80)

    orchestrator = MetadataLineageOrchestrator(
        host="teradata.company.com",
        user="analyst_user",
        password="secure_password",
        database="ANALYTICS_DB",
        output_directory="./lineage_output"
    )

    results = orchestrator.run_full_analysis()

    print(f"\nAnalysis complete!")
    print(f"Total tables: {results['statistics']['total_tables']}")
    print(f"Total views analyzed: {results['statistics']['total_views']}")
    print(f"Total procedures analyzed: {results['statistics']['total_procedures']}")
    print(f"Output files:")
    for key, path in results['output_files'].items():
        if path:
            print(f"  - {key}: {path}")


def example_with_openai():
    """
    Example 2: Using OpenAI for better LLM analysis
    """
    print("\n" + "="*80)
    print("EXAMPLE 2: Using OpenAI for LLM Analysis")
    print("="*80)

    orchestrator = MetadataLineageOrchestrator(
        # Connection settings
        host="teradata.company.com",
        user="analyst_user",
        password="secure_password",
        database="ANALYTICS_DB",

        # Output settings
        output_directory="./lineage_output",
        debug=True,

        # OpenAI configuration
        openai_api_key="sk-proj-...",
        openai_model="gpt-4o-mini",
        batch_size=10,
        timeout=300
    )

    results = orchestrator.run_full_analysis()

    # Access detailed procedure analysis
    procedure_report = results['procedure_report']
    print(f"\nProcedure Analysis Results:")
    print(f"Total analyzed: {procedure_report['summary']['total_analyzed']}")
    print(f"Success rate: {procedure_report['summary']['success_rate']}")

    # Show example of successful procedure analysis
    for proc_name, proc_data in list(procedure_report['procedures'].items())[:3]:
        print(f"\nProcedure: {proc_name}")
        if proc_data['analysis_success']:
            lineage = proc_data['lineage_analysis']
            print(f"  Source tables: {len(lineage.get('source_tables', []))}")
            print(f"  Target: {lineage.get('target', {}).get('name', 'N/A')}")
        else:
            print(f"  Analysis failed")


def example_with_ollama():
    """
    Example 3: Using local Ollama for LLM analysis
    """
    print("\n" + "="*80)
    print("EXAMPLE 3: Using Ollama (Local LLM)")
    print("="*80)

    orchestrator = MetadataLineageOrchestrator(
        # Connection settings
        host="teradata.company.com",
        user="analyst_user",
        password="secure_password",
        database="ANALYTICS_DB",

        # Ollama configuration
        ollama_url="http://localhost:11434",
        ollama_model="qwen2.5-coder:14b",
        batch_size=1,  # Sequential processing for Ollama
        timeout=600,   # Longer timeout for local processing

        output_directory="./lineage_output"
    )

    results = orchestrator.run_full_analysis()
    print(f"\nAnalysis complete with Ollama!")


def example_with_preloaded_metadata():
    """
    Example 4: Using pre-extracted metadata (no database connection needed)
    """
    print("\n" + "="*80)
    print("EXAMPLE 4: Using Pre-Extracted Metadata")
    print("="*80)

    # First run: Extract metadata
    print("\nStep 1: Extracting metadata...")
    orchestrator1 = MetadataLineageOrchestrator(
        host="teradata.company.com",
        user="analyst_user",
        password="secure_password",
        database="ANALYTICS_DB",
        output_directory="./lineage_output"
    )

    # Just extract metadata, don't run full analysis yet
    metadata = orchestrator1.extract_metadata()
    metadata_file = orchestrator1.metadata_file_path

    print(f"Metadata extracted to: {metadata_file}")

    # Second run: Analyze using pre-extracted metadata
    print("\nStep 2: Analyzing with pre-extracted metadata...")
    orchestrator2 = MetadataLineageOrchestrator(
        host="teradata.company.com",  # Still needed for connection info
        user="analyst_user",
        password="",  # Not needed with pre-loaded metadata
        database="ANALYTICS_DB",
        metadata_file_path=str(metadata_file),
        openai_api_key="sk-proj-...",
        output_directory="./lineage_output"
    )

    results = orchestrator2.run_full_analysis()
    print(f"\nAnalysis complete using cached metadata!")


def example_with_custom_authentication():
    """
    Example 5: Custom Teradata authentication
    """
    print("\n" + "="*80)
    print("EXAMPLE 5: Custom Authentication")
    print("="*80)

    orchestrator = MetadataLineageOrchestrator(
        # Teradata connection with LDAP authentication
        host="teradata.company.com",
        user="domain\\analyst_user",
        password="secure_password",
        database="ANALYTICS_DB",
        logmech="LDAP",  # Use LDAP authentication
        encryptdata="ON",  # Encrypt data transmission

        output_directory="./lineage_output"
    )

    results = orchestrator.run_full_analysis()
    print(f"\nAnalysis complete with LDAP authentication!")


def example_analyzing_specific_objects():
    """
    Example 6: Analyzing and inspecting specific database objects
    """
    print("\n" + "="*80)
    print("EXAMPLE 6: Analyzing Specific Objects")
    print("="*80)

    orchestrator = MetadataLineageOrchestrator(
        host="teradata.company.com",
        user="analyst_user",
        password="secure_password",
        database="ANALYTICS_DB",
        output_directory="./lineage_output",
        openai_api_key="sk-proj-...",
        debug=True
    )

    results = orchestrator.run_full_analysis()

    # Analyze specific view
    print("\n--- View Analysis ---")
    statement_report = results['statement_report']
    for view in statement_report['views']:
        if 'CUSTOMER' in view['name'].upper():
            print(f"\nView: {view['name']}")
            print(f"Source tables: {view.get('source_tables', [])}")
            print(f"Columns: {len(view.get('column_lineage', []))}")

            # Show column lineage
            for col in view.get('column_lineage', [])[:5]:
                print(f"  {col['target_column']} <- {col.get('source_columns', [])}")

    # Analyze specific procedure
    print("\n--- Procedure Analysis ---")
    procedure_report = results['procedure_report']
    for proc_name, proc_data in procedure_report['procedures'].items():
        if 'UPDATE' in proc_name.upper():
            print(f"\nProcedure: {proc_name}")
            print(f"Language: {proc_data.get('language', 'SQL')}")
            print(f"Analysis success: {proc_data.get('analysis_success', False)}")

            if proc_data.get('analysis_success'):
                lineage = proc_data['lineage_analysis']
                print(f"Source tables:")
                for src in lineage.get('source_tables', []):
                    print(f"  - {src.get('table_list')}: {src.get('columns_used', [])}")

                target = lineage.get('target', {})
                print(f"Target: {target.get('name')} ({target.get('operation')})")

    # Analyze macros (Teradata-specific)
    print("\n--- Macro Analysis ---")
    for macro_name, macro_data in procedure_report.get('macros', {}).items():
        print(f"\nMacro: {macro_name}")
        print(f"Analysis success: {macro_data.get('analysis_success', False)}")


def example_batch_processing():
    """
    Example 7: Batch processing with progress tracking
    """
    print("\n" + "="*80)
    print("EXAMPLE 7: Batch Processing")
    print("="*80)

    orchestrator = MetadataLineageOrchestrator(
        host="teradata.company.com",
        user="analyst_user",
        password="secure_password",
        database="ANALYTICS_DB",
        output_directory="./lineage_output",

        # OpenAI with batch processing
        openai_api_key="sk-proj-...",
        openai_model="gpt-4o-mini",
        batch_size=20,  # Process 20 procedures at a time
        timeout=600,    # 10 minutes per procedure

        debug=True
    )

    results = orchestrator.run_full_analysis()

    # Print statistics
    stats = results['statistics']
    print(f"\nBatch Processing Statistics:")
    print(f"Total procedures: {stats['total_procedures']}")
    print(f"Total functions: {stats['total_functions']}")
    print(f"Total macros: {stats['total_macros']}")
    print(f"LLM success rate: {stats['llm_success_rate']}")


def example_export_to_csv():
    """
    Example 8: Export lineage results to CSV
    """
    print("\n" + "="*80)
    print("EXAMPLE 8: Export to CSV")
    print("="*80)

    orchestrator = MetadataLineageOrchestrator(
        host="teradata.company.com",
        user="analyst_user",
        password="secure_password",
        database="ANALYTICS_DB",
        output_directory="./lineage_output"
    )

    results = orchestrator.run_full_analysis()

    # Export table lineage to CSV
    import csv

    output_file = Path(orchestrator.output_directory) / "table_lineage.csv"
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Source Type', 'Source Object', 'Target Object', 'Column', 'Source Column'])

        # Export view lineage
        for view in results['statement_report']['views']:
            for col in view.get('column_lineage', []):
                for src in col.get('source_columns', []):
                    writer.writerow([
                        'VIEW',
                        view['name'],
                        col['target_table'],
                        col['target_column'],
                        f"{src.get('table', '')}.{src.get('column', '')}"
                    ])

        # Export procedure lineage
        for proc_name, proc_data in results['procedure_report']['procedures'].items():
            if proc_data.get('analysis_success'):
                lineage = proc_data['lineage_analysis']
                target = lineage.get('target', {})

                for col_lineage in lineage.get('column_lineage', []):
                    target_col = col_lineage.get('target_column', '')
                    for src in col_lineage.get('source_columns', []):
                        writer.writerow([
                            'PROCEDURE',
                            proc_name,
                            target.get('name', ''),
                            target_col,
                            f"{src.get('table_list', '')}.{src.get('column', '')}"
                        ])

    print(f"Exported lineage to: {output_file}")


def example_incremental_analysis():
    """
    Example 9: Incremental analysis (only new/modified objects)
    """
    print("\n" + "="*80)
    print("EXAMPLE 9: Incremental Analysis")
    print("="*80)

    # Load previous metadata
    previous_metadata_file = "./lineage_output/enhanced_metadata_ANALYTICS_DB_20231124_*.json"

    # Extract new metadata
    orchestrator = MetadataLineageOrchestrator(
        host="teradata.company.com",
        user="analyst_user",
        password="secure_password",
        database="ANALYTICS_DB",
        output_directory="./lineage_output"
    )

    new_metadata = orchestrator.extract_metadata(force_refresh=True)

    # Compare with previous metadata (simplified example)
    try:
        import glob
        prev_files = glob.glob(previous_metadata_file)
        if prev_files:
            with open(prev_files[0], 'r') as f:
                prev_metadata = json.load(f)

            # Find new procedures
            prev_procs = {p['procedure_name'] for p in prev_metadata.get('procedures', [])}
            new_procs = {p['procedure_name'] for p in new_metadata.get('procedures', [])}
            added_procs = new_procs - prev_procs

            print(f"\nNew procedures since last run: {len(added_procs)}")
            for proc in list(added_procs)[:10]:
                print(f"  - {proc}")

    except Exception as e:
        print(f"Could not compare with previous metadata: {e}")

    # Run full analysis
    results = orchestrator.run_full_analysis()


def example_error_handling():
    """
    Example 10: Proper error handling
    """
    print("\n" + "="*80)
    print("EXAMPLE 10: Error Handling")
    print("="*80)

    try:
        orchestrator = MetadataLineageOrchestrator(
            host="teradata.company.com",
            user="analyst_user",
            password="secure_password",
            database="ANALYTICS_DB",
            output_directory="./lineage_output",
            debug=True
        )

        results = orchestrator.run_full_analysis()

        # Check for analysis errors
        statement_report = results['statement_report']
        failed_views = [
            v for v in statement_report['views']
            if not v.get('analysis_success', False)
        ]

        if failed_views:
            print(f"\nWarning: {len(failed_views)} views failed to parse:")
            for view in failed_views[:5]:
                print(f"  - {view['name']}")

        # Check procedure analysis errors
        procedure_report = results['procedure_report']
        failed_procs = [
            name for name, data in procedure_report['procedures'].items()
            if not data.get('analysis_success', False)
        ]

        if failed_procs:
            print(f"\nWarning: {len(failed_procs)} procedures failed LLM analysis:")
            for proc in failed_procs[:5]:
                print(f"  - {proc}")

    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install required packages: pip install teradatasql sqlglot aiohttp openai")

    except ConnectionError as e:
        print(f"Database connection failed: {e}")
        print("Check host, username, password, and network connectivity")

    except Exception as e:
        print(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    """
    Run examples

    Uncomment the example you want to run:
    """

    # example_basic_usage()
    # example_with_openai()
    # example_with_ollama()
    # example_with_preloaded_metadata()
    # example_with_custom_authentication()
    # example_analyzing_specific_objects()
    # example_batch_processing()
    # example_export_to_csv()
    # example_incremental_analysis()
    # example_error_handling()

    print("\n" + "="*80)
    print("TERADATA METADATA LINEAGE ORCHESTRATOR - EXAMPLES")
    print("="*80)
    print("\nAvailable examples:")
    print("  1. example_basic_usage() - Basic usage with minimal configuration")
    print("  2. example_with_openai() - Using OpenAI for LLM analysis")
    print("  3. example_with_ollama() - Using local Ollama for LLM analysis")
    print("  4. example_with_preloaded_metadata() - Using cached metadata")
    print("  5. example_with_custom_authentication() - LDAP and other auth methods")
    print("  6. example_analyzing_specific_objects() - Inspect specific views/procedures")
    print("  7. example_batch_processing() - Batch processing with progress tracking")
    print("  8. example_export_to_csv() - Export results to CSV")
    print("  9. example_incremental_analysis() - Only analyze new/modified objects")
    print(" 10. example_error_handling() - Proper error handling")
    print("\nUncomment the example you want to run in the __main__ section.")
    print("="*80)
