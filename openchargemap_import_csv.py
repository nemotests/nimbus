#!/usr/bin/env python3
"""
Fetch charging station data from OpenChargeMap API and convert to CSV.

This script fetches POI data from OpenChargeMap API and formats it as flat CSV files.
"""

import csv
import json
import sys
import os
import requests
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv


def fetch_openchargemap_data(base_url: str, max_results: int = 10000) -> Tuple[List[Dict[str, Any]], int]:
    """
    Fetch all data from OpenChargeMap API.
    
    Args:
        base_url: The OpenChargeMap API URL (without maxresults parameter)
        max_results: Maximum results to fetch (default: 10000)
        
    Returns:
        Tuple of (list of all POI dictionaries, number of results returned)
    """
    # Remove maxresults from URL if present
    if 'maxresults=' in base_url:
        # Remove maxresults parameter
        parts = base_url.split('&')
        base_url = '&'.join([p for p in parts if not p.startswith('maxresults=')])
    
    # Build URL with maxresults to get all data
    if '?' in base_url:
        url = f"{base_url}&maxresults={max_results}"
    else:
        url = f"{base_url}?maxresults={max_results}"
    
    print(f"Fetching charging station data from OpenChargeMap API...")
    print(f"URL: {url}\n")
    
    try:
        response = requests.get(url, timeout=300)  # 5 minute timeout for large datasets
        response.raise_for_status()
        data = response.json()
        
        # Handle different response formats
        if isinstance(data, dict):
            # If response is a dict, check for common keys
            if 'data' in data:
                data = data['data']
            elif 'results' in data:
                data = data['results']
            elif 'items' in data:
                data = data['items']
            else:
                # If it's a dict but not a list, try to extract values
                print(f"Warning: Response is a dict, attempting to extract data...")
                print(f"Response keys: {list(data.keys())}")
        
        if not isinstance(data, list):
            print(f"Warning: Expected list but got {type(data)}")
            return [], 0
        
        num_results = len(data)
        print(f"Successfully fetched {num_results} charging stations")
        return data, num_results
    except requests.exceptions.Timeout:
        print(f"Error: Request timed out. The dataset might be too large.", file=sys.stderr)
        print(f"Try reducing the bounding box or contact OpenChargeMap for bulk data access.", file=sys.stderr)
        raise
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        raise


def flatten_poi(poi: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten a POI dictionary into a flat structure for CSV.
    
    Args:
        poi: POI dictionary from OpenChargeMap API
        
    Returns:
        Flattened dictionary with all fields at top level
    """
    flat = {}
    
    # Basic fields
    flat['id'] = poi.get('ID') or poi.get('id') or ''
    flat['uuid'] = poi.get('UUID') or poi.get('uuid') or ''
    flat['operator_id'] = poi.get('OperatorID') or poi.get('operatorID') or poi.get('operator_id') or ''
    flat['usage_type_id'] = poi.get('UsageTypeID') or poi.get('usageTypeID') or poi.get('usage_type_id') or ''
    flat['status_type_id'] = poi.get('StatusTypeID') or poi.get('statusTypeID') or poi.get('status_type_id') or ''
    flat['number_of_points'] = poi.get('NumberOfPoints') or poi.get('numberOfPoints') or poi.get('number_of_points') or ''
    flat['general_comments'] = poi.get('GeneralComments') or poi.get('generalComments') or poi.get('general_comments') or ''
    flat['date_created'] = poi.get('DateCreated') or poi.get('dateCreated') or poi.get('date_created') or ''
    flat['date_last_updated'] = poi.get('DateLastUpdated') or poi.get('dateLastUpdated') or poi.get('date_last_updated') or ''
    flat['date_last_status_update'] = poi.get('DateLastStatusUpdate') or poi.get('dateLastStatusUpdate') or poi.get('date_last_status_update') or ''
    
    # Operator info
    operator_info = poi.get('OperatorInfo') or poi.get('operatorInfo') or poi.get('operator_info') or {}
    if isinstance(operator_info, dict):
        flat['operator_name'] = operator_info.get('Title') or operator_info.get('title') or ''
        flat['operator_website'] = operator_info.get('WebsiteURL') or operator_info.get('websiteURL') or operator_info.get('website_url') or ''
    else:
        flat['operator_name'] = ''
        flat['operator_website'] = ''
    
    # Usage type
    usage_type = poi.get('UsageType') or poi.get('usageType') or poi.get('usage_type') or {}
    if isinstance(usage_type, dict):
        flat['usage_type'] = usage_type.get('Title') or usage_type.get('title') or ''
    else:
        flat['usage_type'] = ''
    
    # Status type
    status_type = poi.get('StatusType') or poi.get('statusType') or poi.get('status_type') or {}
    if isinstance(status_type, dict):
        flat['status_type'] = status_type.get('Title') or status_type.get('title') or ''
    else:
        flat['status_type'] = ''
    
    # Address info
    address_info = poi.get('AddressInfo') or poi.get('addressInfo') or poi.get('address_info') or {}
    if isinstance(address_info, dict):
        flat['latitude'] = address_info.get('Latitude') or address_info.get('latitude') or address_info.get('lat') or ''
        flat['longitude'] = address_info.get('Longitude') or address_info.get('longitude') or address_info.get('lon') or address_info.get('lng') or ''
        flat['address_line1'] = address_info.get('AddressLine1') or address_info.get('addressLine1') or address_info.get('address_line1') or ''
        flat['address_line2'] = address_info.get('AddressLine2') or address_info.get('addressLine2') or address_info.get('address_line2') or ''
        flat['town'] = address_info.get('Town') or address_info.get('town') or ''
        flat['state_or_province'] = address_info.get('StateOrProvince') or address_info.get('stateOrProvince') or address_info.get('state_or_province') or ''
        flat['postcode'] = address_info.get('Postcode') or address_info.get('postcode') or ''
        flat['country_id'] = address_info.get('CountryID') or address_info.get('countryID') or address_info.get('country_id') or ''
        
        country = address_info.get('Country') or address_info.get('country') or {}
        if isinstance(country, dict):
            flat['country'] = country.get('Title') or country.get('title') or ''
        else:
            flat['country'] = ''
    else:
        flat['latitude'] = ''
        flat['longitude'] = ''
        flat['address_line1'] = ''
        flat['address_line2'] = ''
        flat['town'] = ''
        flat['state_or_province'] = ''
        flat['postcode'] = ''
        flat['country_id'] = ''
        flat['country'] = ''
    
    # Connections - flatten as JSON string or count
    connections = poi.get('Connections') or poi.get('connections') or []
    if isinstance(connections, list):
        flat['connection_count'] = len(connections)
        # Store connection details as JSON string
        flat['connections'] = json.dumps(connections) if connections else ''
    else:
        flat['connection_count'] = 0
        flat['connections'] = ''
    
    return flat


def convert_to_csv_rows(pois: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Convert OpenChargeMap POI data to CSV rows.
    
    Args:
        pois: List of POI dictionaries from OpenChargeMap API
        
    Returns:
        Tuple of (list of flattened dictionaries, list of field names)
    """
    rows = []
    skipped = 0
    
    print(f"\nConverting {len(pois)} POIs to CSV format...")
    
    # Get all field names from first POI to ensure consistent columns
    if pois:
        sample_flat = flatten_poi(pois[0])
        fieldnames = list(sample_flat.keys())
    else:
        fieldnames = []
    
    for poi in pois:
        # Flatten the POI
        flat_poi = flatten_poi(poi)
        
        # Only include if we have coordinates
        if flat_poi.get('latitude') and flat_poi.get('longitude'):
            rows.append(flat_poi)
        else:
            skipped += 1
            if skipped <= 3:  # Only print first few skipped items
                print(f"Warning: Skipping POI {poi.get('ID', 'unknown')} - missing coordinates")
    
    if skipped > 0:
        print(f"Skipped {skipped} POIs due to missing coordinate data")
    
    print(f"Created {len(rows)} CSV rows")
    
    return rows, fieldnames


def save_csv(rows: List[Dict[str, Any]], fieldnames: List[str], output_file: str = "openchargemap_stations.csv"):
    """
    Save CSV data to a file in the csv_files directory.
    
    Args:
        rows: List of flattened dictionaries (one per row)
        fieldnames: List of column names
        output_file: Output file path (will be saved in csv_files/ directory)
    """
    # Create csv_files directory if it doesn't exist
    csv_dir = Path("csv_files")
    csv_dir.mkdir(exist_ok=True)
    
    # Ensure output_file is just the filename, not a full path
    filename = Path(output_file).name
    if not filename.endswith('.csv'):
        filename += '.csv'
    
    # Create full path in csv_files directory
    output_path = csv_dir / filename
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        # Use QUOTE_MINIMAL which will automatically quote fields containing commas, newlines, or quotes
        writer = csv.DictWriter(
            f, 
            fieldnames=fieldnames, 
            extrasaction='ignore',
            quoting=csv.QUOTE_MINIMAL  # Quote fields containing delimiter, newline, or quote character
        )
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"\nCSV saved to: {output_path.absolute()}")
    print(f"Total rows: {len(rows)}")


def generate_filename_from_bbox(bbox: str, index: int) -> str:
    """
    Generate a filename from a bounding box string.
    
    Args:
        bbox: Bounding box string in format "(lat1,lon1),(lat2,lon2)"
        index: Index number for the bounding box
        
    Returns:
        Filename string
    """
    # Clean the bbox string for filename
    clean_bbox = bbox.replace('(', '').replace(')', '').replace(',', '_').replace(' ', '')
    return f"openchargemap_bbox_{index:03d}_{clean_bbox}.csv"


if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()
    
    # Get API key from environment
    api_key = os.getenv("opencharge_map_key")
    if not api_key:
        print("Error: opencharge_map_key not found in .env file", file=sys.stderr)
        sys.exit(1)
    
    # Get bounding boxes from environment
    # Format: tiles_array= ["item1","item2",...]
    tiles_str = os.getenv("tiles_array")
    if not tiles_str:
        print("Error: tiles_array not found in .env file", file=sys.stderr)
        sys.exit(1)
    
    # Parse bounding boxes - expect JSON array format
    bounding_boxes = []
    
    # Remove surrounding quotes if present (common in .env files)
    # Handle both single and double quotes
    tiles_str = tiles_str.strip()
    if (tiles_str.startswith('"') and tiles_str.endswith('"')) or \
       (tiles_str.startswith("'") and tiles_str.endswith("'")):
        tiles_str = tiles_str[1:-1]
    
    # If the string includes "tiles_array=", extract just the array part
    if '=' in tiles_str:
        # Extract everything after the = sign
        tiles_str = tiles_str.split('=', 1)[1].strip()
    
    # Remove trailing comma before closing bracket (invalid JSON but common)
    # Pattern: ...",] should become ..."]
    tiles_str = tiles_str.rstrip(',').strip()
    if tiles_str.endswith(',]'):
        tiles_str = tiles_str[:-2] + ']'
    
    try:
        # Parse as JSON array
        bounding_boxes = json.loads(tiles_str)
        if not isinstance(bounding_boxes, list):
            raise ValueError("tiles_array must be a JSON array")
    except json.JSONDecodeError as e:
        # If JSON parsing fails, try to fix common issues
        print(f"Warning: JSON parse error: {e}", file=sys.stderr)
        print(f"Attempting to fix JSON format...", file=sys.stderr)
        
        # Try removing trailing comma before ]
        fixed_str = tiles_str.rstrip()
        if fixed_str.endswith(',]'):
            fixed_str = fixed_str[:-2] + ']'
        elif fixed_str.endswith(','):
            fixed_str = fixed_str.rstrip(',')
        
        try:
            bounding_boxes = json.loads(fixed_str)
            if not isinstance(bounding_boxes, list):
                raise ValueError("tiles_array must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e2:
            print(f"Error: Could not parse tiles_array as JSON: {e2}", file=sys.stderr)
            print(f"Debug: tiles_str (first 200 chars): {tiles_str[:200]}", file=sys.stderr)
            sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Debug: Show how many were parsed
    print(f"Parsed {len(bounding_boxes)} bounding boxes from tiles_array")
    
    if not bounding_boxes:
        print("Error: No bounding boxes found in tiles_array environment variable", file=sys.stderr)
        print(f"Debug info: tiles_str length={len(tiles_str)}, first 200 chars: {tiles_str[:200]}", file=sys.stderr)
        sys.exit(1)
    
    # Warn if only 1 bounding box (might indicate parsing issue)
    if len(bounding_boxes) == 1:
        print(f"Warning: Only 1 bounding box parsed. This might indicate a parsing issue.", file=sys.stderr)
        print(f"First bounding box: {bounding_boxes[0][:100]}...", file=sys.stderr)
    
    max_results = 10000
    
    print(f"Processing {len(bounding_boxes)} bounding boxes...")
    print(f"Max results per request: {max_results}\n")
    print("=" * 80)
    
    files_with_warnings = []
    
    for idx, bbox in enumerate(bounding_boxes, start=1):
        print(f"\n[{idx}/{len(bounding_boxes)}] Processing bounding box: {bbox}")
        print("-" * 80)
        
        # Build URL for this bounding box
        url = f"https://api.openchargemap.io/v3/poi?output=json&camelcase=false&boundingbox={bbox}&key={api_key}"
        
        try:
            # Fetch data
            pois, num_results = fetch_openchargemap_data(url, max_results=max_results)
            
            # Check if we hit the max results limit
            if num_results >= max_results:
                warning_msg = f"WARNING: Bounding box {idx} returned {num_results} results, which equals or exceeds the max_results limit of {max_results}. Some data may be missing!"
                print(f"\n{'!' * 80}", file=sys.stderr)
                print(warning_msg, file=sys.stderr)
                print(f"{'!' * 80}\n", file=sys.stderr)
                files_with_warnings.append((idx, bbox, num_results))
            
            if not pois:
                print(f"Warning: No POI data received for bounding box {idx}, skipping...")
                continue
            
            # Convert to CSV rows
            rows, fieldnames = convert_to_csv_rows(pois)
            
            if not rows:
                print(f"Warning: No valid POI data to save for bounding box {idx}, skipping...")
                continue
            
            # Generate filename
            filename = generate_filename_from_bbox(bbox, idx)
            
            # Save to CSV file
            save_csv(rows, fieldnames, filename)
            
        except Exception as e:
            print(f"Error processing bounding box {idx}: {e}", file=sys.stderr)
            continue
    
    # Summary
    print("\n" + "=" * 80)
    print(f"Processing complete! Processed {len(bounding_boxes)} bounding boxes.")
    
    if files_with_warnings:
        print(f"\nWARNING: {len(files_with_warnings)} bounding box(es) hit the max_results limit:")
        for idx, bbox, num_results in files_with_warnings:
            print(f"  - Bounding box {idx}: {num_results} results (limit: {max_results})")
            print(f"    BBox: {bbox}")
    else:
        print("\nAll bounding boxes processed successfully without hitting the max_results limit.")
