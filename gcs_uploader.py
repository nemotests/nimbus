#!/usr/bin/env python3
"""
Upload CSV files from csv_files directory to Google Cloud Storage bucket
and import them into BigQuery.

This script:
1. Reads all CSV files from the csv_files directory
2. Uploads them to a specified GCS bucket under openchargemap/YYYYMMDD_HHMMSS/
3. Imports the data from GCS into BigQuery table
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv


from google.cloud import storage, bigquery
from google.auth.exceptions import DefaultCredentialsError
from google.cloud.exceptions import NotFound


def get_gcs_client(credentials_path: Optional[str] = None, project: Optional[str] = None):
    """
    Create and return a GCS client.
    
    Args:
        credentials_path: Optional path to service account JSON file
        project: Optional GCP project ID
        
    Returns:
        storage.Client instance
    """
    try:
        # If credentials_path is provided, use it
        if credentials_path:
            # Check if it's a service account JSON file (not application_default_credentials)
            if credentials_path.endswith('application_default_credentials.json'):
                print("Warning: application_default_credentials.json may have issues.", file=sys.stderr)
                print("Consider using a service account JSON file instead, or remove GCS_CREDENTIALS_PATH", file=sys.stderr)
                print("and run 'gcloud auth application-default login' to regenerate credentials.", file=sys.stderr)
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        
        # Create client with project if provided
        if project:
            client = storage.Client(project=project)
        else:
            # Try to use default credentials (from environment or gcloud auth)
            client = storage.Client()
        return client
    except DefaultCredentialsError:
        print("Error: No credentials found.", file=sys.stderr)
        print("Please either:", file=sys.stderr)
        print("  1. Set GOOGLE_APPLICATION_CREDENTIALS environment variable", file=sys.stderr)
        print("  2. Run 'gcloud auth application-default login'", file=sys.stderr)
        print("  3. Set GCS_CREDENTIALS_PATH in .env file to a service account JSON", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error creating GCS client: {e}", file=sys.stderr)
        if "Project was not passed" in str(e):
            print("Please set GCS_PROJECT_ID in your .env file", file=sys.stderr)
        sys.exit(1)


def get_csv_files(csv_dir: Path) -> List[Path]:
    """
    Get all CSV files from the specified directory.
    
    Args:
        csv_dir: Path to directory containing CSV files
        
    Returns:
        List of Path objects for CSV files
    """
    if not csv_dir.exists():
        print(f"Error: Directory {csv_dir} does not exist", file=sys.stderr)
        sys.exit(1)
    
    csv_files = list(csv_dir.glob("*.csv"))
    if not csv_files:
        print(f"Warning: No CSV files found in {csv_dir}", file=sys.stderr)
        return []
    
    return sorted(csv_files)


def upload_file_to_gcs(
    client: storage.Client,
    bucket_name: str,
    local_file: Path,
    gcs_path: Optional[str] = None,
    overwrite: bool = False
) -> bool:
    """
    Upload a single file to GCS bucket.
    
    Args:
        client: GCS client instance
        bucket_name: Name of the GCS bucket
        local_file: Path to local file to upload
        gcs_path: Optional GCS path (default: same as filename)
        overwrite: Whether to overwrite existing files
        
    Returns:
        True if successful, False otherwise
    """
    try:
        bucket = client.bucket(bucket_name)
        
        # Use provided gcs_path or default to filename
        if gcs_path:
            blob_name = gcs_path
        else:
            blob_name = local_file.name
        
        blob = bucket.blob(blob_name)
        
        # Check if file already exists
        if blob.exists() and not overwrite:
            print(f"  ⚠ Skipping {local_file.name} (already exists in bucket)")
            return False
        
        # Upload the file
        blob.upload_from_filename(str(local_file))
        
        # Get file size for display
        file_size = local_file.stat().st_size
        size_mb = file_size / (1024 * 1024)
        
        print(f"  ✓ Uploaded {local_file.name} ({size_mb:.2f} MB) -> gs://{bucket_name}/{blob_name}")
        return True
        
    except Exception as e:
        print(f"  ✗ Error uploading {local_file.name}: {e}", file=sys.stderr)
        return False


def run_post_import_sql(
    bq_client: bigquery.Client,
    project_id: str,
    dataset_id: str,
    table_id: str,
):
    """
    Run post-import SQL steps on the target BigQuery table:
      1) Add a GEOGRAPHY column `geom` and populate it with ST_GEOGPOINT(longitude, latitude)
      2) Add a STRING column `lat_lng` and populate it with "latitude,longitude"
    """
    full_table_id = f"`{project_id}.{dataset_id}.{table_id}`"

    statements = [
        # 1) Add geom column if it doesn't exist
        f"""
        ALTER TABLE {full_table_id}
        ADD COLUMN IF NOT EXISTS geom GEOGRAPHY
        """,
        # 2) Populate geom from longitude/latitude
        f"""
        UPDATE {full_table_id}
        SET geom = ST_GEOGPOINT(longitude),latitude)
        WHERE longitude IS NOT NULL
          AND latitude IS NOT NULL
        """,
        # 3) Add lat_lng column if it doesn't exist
        f"""
        ALTER TABLE {full_table_id}
        ADD COLUMN IF NOT EXISTS lat_lng STRING
        """,
        # 4) Populate lat_lng as "latitude,longitude"
        f"""
        UPDATE {full_table_id}
        SET lat_lng = CONCAT(CAST(latitude AS STRING), ',', CAST(longitude AS STRING))
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
        """,
    ]

    print("\nRunning post-import SQL transformations in BigQuery...")
    for idx, sql in enumerate(statements, start=1):
        try:
            print(f"  [{idx}/{len(statements)}] Executing statement...")
            job = bq_client.query(sql)
            job.result()  # Wait for completion
            print("    ✓ Done")
        except Exception as e:
            print(f"    ✗ Error executing statement {idx}: {e}", file=sys.stderr)
            # Continue with remaining statements so a failure in one doesn't block others


def import_to_bigquery(
    bucket_name: str,
    gcs_path: str,
    project_id: str,
    dataset_id: str,
    table_id: str,
    credentials_path: Optional[str] = None,
    write_disposition: str = "WRITE_APPEND"
):
    """
    Import CSV files from GCS into BigQuery table.
    
    Args:
        bucket_name: Name of the GCS bucket
        gcs_path: GCS path prefix (e.g., "openchargemap/20241215_143022/")
        project_id: GCP project ID
        dataset_id: BigQuery dataset ID
        table_id: BigQuery table ID
        credentials_path: Optional path to service account JSON file
        write_disposition: How to handle existing data (WRITE_APPEND, WRITE_TRUNCATE, WRITE_EMPTY)
    """
    print("\n" + "=" * 80)
    print("Importing data to BigQuery...")
    print(f"Project: {project_id}")
    print(f"Dataset: {dataset_id}")
    print(f"Table: {table_id}")
    print(f"GCS path: gs://{bucket_name}/{gcs_path}/*.csv")
    print("=" * 80)
    
    try:
        # Create BigQuery client
        if credentials_path:
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
        
        bq_client = bigquery.Client(project=project_id)
        
        # Get dataset reference
        dataset_ref = bq_client.dataset(dataset_id)
        
        # Create dataset if it doesn't exist
        try:
            bq_client.get_dataset(dataset_ref)
            print(f"✓ Dataset '{dataset_id}' exists")
        except NotFound:
            print(f"Creating dataset '{dataset_id}'...")
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"  # Set location, adjust if needed
            dataset = bq_client.create_dataset(dataset, exists_ok=True)
            print(f"✓ Dataset '{dataset_id}' created")
        
        # Get table reference
        table_ref = dataset_ref.table(table_id)
        
        # Construct GCS URI pattern
        gcs_uri = f"gs://{bucket_name}/{gcs_path.rstrip('/')}/*.csv"
        
        # Configure the load job
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,  # Skip header row
            autodetect=True,  # Automatically detect schema
            write_disposition=write_disposition,
            field_delimiter=",",
            quote_character='"',  # Use double quotes for quoted fields
            allow_quoted_newlines=True,  # Allow newlines in quoted fields (for JSON)
            allow_jagged_rows=True,  # Allow rows with missing trailing columns
            max_bad_records=1000,  # Allow up to 1000 bad records before failing
            ignore_unknown_values=True  # Ignore values that don't match the schema
        )
        
        # Start the load job
        print(f"\nLoading data from GCS to BigQuery...")
        load_job = bq_client.load_table_from_uri(
            gcs_uri,
            table_ref,
            job_config=job_config
        )
        
        # Wait for the job to complete
        print("Waiting for job to complete...", end="", flush=True)
        load_job.result()  # Waits for the job to complete
        
        # Get the loaded table
        table = bq_client.get_table(table_ref)
        
        print(f"\n✓ Successfully loaded {table.num_rows} rows into {project_id}.{dataset_id}.{table_id}")
        print(f"  Table size: {table.num_bytes / (1024*1024):.2f} MB")

        # Run post-import SQL to add and populate geom and lat_lng columns
        run_post_import_sql(
            bq_client=bq_client,
            project_id=project_id,
            dataset_id=dataset_id,
            table_id=table_id,
        )
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error importing to BigQuery: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


def upload_all_csv_files(
    bucket_name: str,
    csv_dir: Path = Path("csv_files"),
    gcs_prefix: Optional[str] = None,
    credentials_path: Optional[str] = None,
    project: Optional[str] = None,
    overwrite: bool = False
) -> str:
    """
    Upload all CSV files from csv_files directory to GCS bucket.
    
    Args:
        bucket_name: Name of the GCS bucket
        csv_dir: Path to directory containing CSV files
        gcs_prefix: Optional prefix to add to GCS paths (e.g., "data/csv/")
        credentials_path: Optional path to service account JSON file
        project: Optional GCP project ID
        overwrite: Whether to overwrite existing files
        
    Returns:
        Base GCS path where files were uploaded (e.g., "openchargemap/20241215_143022")
    """
    # Create timestamp for directory name (format: YYYYMMDD_HHMMSS)
    start_time = datetime.now()
    timestamp_dir = start_time.strftime("%Y%m%d_%H%M%S")
    
    # Build base GCS path: openchargemap/YYYYMMDD_HHMMSS/
    base_gcs_path = f"openchargemap/{timestamp_dir}"
    
    print(f"Uploading CSV files to GCS bucket: {bucket_name}")
    print(f"Source directory: {csv_dir.absolute()}")
    print(f"GCS base path: {base_gcs_path}/")
    if gcs_prefix:
        print(f"Additional prefix: {gcs_prefix}")
    print("=" * 80)
    
    # Get GCS client
    client = get_gcs_client(credentials_path=credentials_path, project=project)
    
    # Verify client is properly initialized
    if not isinstance(client, storage.Client):
        print(f"Error: Client is not a storage.Client instance. Got: {type(client)}", file=sys.stderr)
        sys.exit(1)
    
    # Verify bucket exists
    try:
        # Get bucket reference - make sure we're calling the method, not accessing a property
        if not hasattr(client, 'bucket') or not callable(getattr(client, 'bucket', None)):
            print(f"Error: client.bucket is not callable. Type: {type(getattr(client, 'bucket', None))}", file=sys.stderr)
            sys.exit(1)
        
        bucket_ref = client.bucket(bucket_name)
        # Check if bucket exists
        if not bucket_ref.exists():
            print(f"Error: Bucket '{bucket_name}' does not exist", file=sys.stderr)
            sys.exit(1)
        print(f"✓ Bucket '{bucket_name}' verified")
    except AttributeError as e:
        print(f"Error: Invalid client object. {e}", file=sys.stderr)
        print(f"Client type: {type(client)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"Error accessing bucket '{bucket_name}': {e}", file=sys.stderr)
        print(f"Error type: {type(e).__name__}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Get all CSV files
    csv_files = get_csv_files(csv_dir)
    
    if not csv_files:
        print("No CSV files to upload.")
        return
    
    print(f"\nFound {len(csv_files)} CSV file(s) to upload\n")
    
    # Upload each file
    successful = 0
    failed = 0
    skipped = 0
    
    for idx, csv_file in enumerate(csv_files, start=1):
        print(f"[{idx}/{len(csv_files)}] Processing {csv_file.name}...")
        
        # Construct GCS path: openchargemap/YYYYMMDD_HHMMSS/[prefix/]filename.csv
        if gcs_prefix:
            gcs_path = f"{base_gcs_path}/{gcs_prefix.rstrip('/')}/{csv_file.name}"
        else:
            gcs_path = f"{base_gcs_path}/{csv_file.name}"
        
        result = upload_file_to_gcs(
            client=client,
            bucket_name=bucket_name,
            local_file=csv_file,
            gcs_path=gcs_path,
            overwrite=overwrite
        )
        
        if result:
            successful += 1
        elif result is False:
            # Check if it was skipped (already exists) by trying to access it
            try:
                bucket_ref = client.bucket(bucket_name)
                blob = bucket_ref.blob(gcs_path)
                if blob.exists():
                    skipped += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
    
    # Summary
    print("\n" + "=" * 80)
    print("Upload Summary:")
    print(f"  Successful: {successful}")
    print(f"  Skipped: {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Total: {len(csv_files)}")
    
    if failed > 0:
        print(f"\nWarning: {failed} file(s) failed to upload", file=sys.stderr)
        sys.exit(1)
    
    # Return the base GCS path for BigQuery import
    return base_gcs_path


if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()
    
    # Get configuration from environment
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        print("Error: GCS_BUCKET_NAME not found in .env file", file=sys.stderr)
        print("Please add: GCS_BUCKET_NAME=your-bucket-name", file=sys.stderr)
        sys.exit(1)
    
    # Optional configuration
    csv_dir = Path(os.getenv("CSV_DIR", "csv_files"))
    gcs_prefix = os.getenv("GCS_PREFIX")  # Optional prefix for GCS paths
    credentials_path = os.getenv("GCS_CREDENTIALS_PATH")  # Optional path to service account JSON
    project_id = os.getenv("GCS_PROJECT_ID")  # Optional GCP project ID
    overwrite = os.getenv("GCS_OVERWRITE", "false").lower() == "true"
    
    # Upload all CSV files
    gcs_path = upload_all_csv_files(
        bucket_name=bucket_name,
        csv_dir=csv_dir,
        gcs_prefix=gcs_prefix,
        credentials_path=credentials_path,
        project=project_id,
        overwrite=overwrite
    )
    
    # Import to BigQuery
    bq_project = os.getenv("BQ_PROJECT_ID", project_id or "nimbus-479222")
    bq_dataset = os.getenv("BQ_DATASET_ID", "nimbus_ev_test")
    bq_table = os.getenv("BQ_TABLE_ID", "openchargemap_stations")
    bq_write_mode = os.getenv("BQ_WRITE_MODE", "WRITE_APPEND")
    
    if not bq_project:
        print("\nWarning: BigQuery project ID not specified. Skipping BigQuery import.", file=sys.stderr)
    else:
        success = import_to_bigquery(
            bucket_name=bucket_name,
            gcs_path=gcs_path,
            project_id=bq_project,
            dataset_id=bq_dataset,
            table_id=bq_table,
            credentials_path=credentials_path,
            write_disposition=bq_write_mode
        )
        
        if not success:
            print("\nWarning: BigQuery import failed, but files were uploaded to GCS.", file=sys.stderr)
            sys.exit(1)

