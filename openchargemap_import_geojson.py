#!/usr/bin/env python3
"""
Fetch charging station data from OpenChargeMap API and convert to GeoJSON.

This script fetches POI data from OpenChargeMap API and formats it as GeoJSON.
"""

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


def convert_to_geojson(pois: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Convert OpenChargeMap POI data to GeoJSON format.
    
    Args:
        pois: List of POI dictionaries from OpenChargeMap API
        
    Returns:
        GeoJSON FeatureCollection dictionary
    """
    features = []
    skipped = 0
    
    print(f"\nConverting {len(pois)} POIs to GeoJSON format...")
    
    for poi in pois:
        # Handle case-insensitive key access and different key formats
        address_info = None
        if 'AddressInfo' in poi:
            address_info = poi['AddressInfo']
        elif 'addressInfo' in poi:
            address_info = poi['addressInfo']
        elif 'address_info' in poi:
            address_info = poi['address_info']
        
        if address_info:
            # Try different case variations for latitude/longitude
            lat = None
            lon = None
            
            if 'Latitude' in address_info:
                lat = address_info['Latitude']
            elif 'latitude' in address_info:
                lat = address_info['latitude']
            elif 'lat' in address_info:
                lat = address_info['lat']
            
            if 'Longitude' in address_info:
                lon = address_info['Longitude']
            elif 'longitude' in address_info:
                lon = address_info['longitude']
            elif 'lon' in address_info:
                lon = address_info['lon']
            elif 'lng' in address_info:
                lon = address_info['lng']
            
            if lat is not None and lon is not None:
                # Create GeoJSON feature
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(lon), float(lat)]
                    },
                    "properties": {
                        "id": poi.get('ID') or poi.get('id'),
                        "uuid": poi.get('UUID') or poi.get('uuid'),
                        "operator_id": poi.get('OperatorID') or poi.get('operatorID') or poi.get('operator_id'),
                        "operator_name": (poi.get('OperatorInfo', {}) or poi.get('operatorInfo', {}) or poi.get('operator_info', {}) or {}).get('Title') or (poi.get('OperatorInfo', {}) or poi.get('operatorInfo', {}) or poi.get('operator_info', {}) or {}).get('title'),
                        "usage_type_id": poi.get('UsageTypeID') or poi.get('usageTypeID') or poi.get('usage_type_id'),
                        "usage_type": (poi.get('UsageType', {}) or poi.get('usageType', {}) or poi.get('usage_type', {}) or {}).get('Title') or (poi.get('UsageType', {}) or poi.get('usageType', {}) or poi.get('usage_type', {}) or {}).get('title'),
                        "status_type_id": poi.get('StatusTypeID') or poi.get('statusTypeID') or poi.get('status_type_id'),
                        "status_type": (poi.get('StatusType', {}) or poi.get('statusType', {}) or poi.get('status_type', {}) or {}).get('Title') or (poi.get('StatusType', {}) or poi.get('statusType', {}) or poi.get('status_type', {}) or {}).get('title'),
                        "address": address_info.get('AddressLine1') or address_info.get('addressLine1') or address_info.get('address_line1'),
                        "town": address_info.get('Town') or address_info.get('town'),
                        "state_or_province": address_info.get('StateOrProvince') or address_info.get('stateOrProvince') or address_info.get('state_or_province'),
                        "postcode": address_info.get('Postcode') or address_info.get('postcode'),
                        "country_id": address_info.get('CountryID') or address_info.get('countryID') or address_info.get('country_id'),
                        "country": (address_info.get('Country', {}) or address_info.get('country', {}) or {}).get('Title') or (address_info.get('Country', {}) or address_info.get('country', {}) or {}).get('title'),
                        "number_of_points": poi.get('NumberOfPoints') or poi.get('numberOfPoints') or poi.get('number_of_points'),
                        "general_comments": poi.get('GeneralComments') or poi.get('generalComments') or poi.get('general_comments'),
                        "date_created": poi.get('DateCreated') or poi.get('dateCreated') or poi.get('date_created'),
                        "date_last_updated": poi.get('DateLastUpdated') or poi.get('dateLastUpdated') or poi.get('date_last_updated'),
                        "date_last_status_update": poi.get('DateLastStatusUpdate') or poi.get('dateLastStatusUpdate') or poi.get('date_last_status_update'),
                        "connections": poi.get('Connections') or poi.get('connections') or []
                    }
                }
                features.append(feature)
            else:
                skipped += 1
                if skipped <= 3:  # Only print first few skipped items
                    print(f"Warning: Skipping POI {poi.get('ID', 'unknown')} - missing coordinates")
        else:
            skipped += 1
            if skipped <= 3:  # Only print first few skipped items
                print(f"Warning: Skipping POI {poi.get('ID', 'unknown')} - missing AddressInfo")
    
    if skipped > 0:
        print(f"Skipped {skipped} POIs due to missing coordinate data")
    
    print(f"Created {len(features)} GeoJSON features")
    
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    return geojson


def save_geojson(geojson: Dict[str, Any], output_file: str = "openchargemap_stations.geojson"):
    """
    Save GeoJSON data to a file in the data directory.
    
    Args:
        geojson: GeoJSON FeatureCollection dictionary
        output_file: Output file path (will be saved in data/ directory)
    """
    # Create data directory if it doesn't exist
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    # Ensure output_file is just the filename, not a full path
    filename = Path(output_file).name
    
    # Create full path in data directory
    output_path = data_dir / filename
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(geojson, f, indent=2, ensure_ascii=False)
    
    print(f"\nGeoJSON saved to: {output_path.absolute()}")
    print(f"Total features: {len(geojson['features'])}")


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
    return f"openchargemap_bbox_{index:03d}_{clean_bbox}.geojson"


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
            
            # Convert to GeoJSON
            geojson = convert_to_geojson(pois)
            
            # Generate filename
            filename = generate_filename_from_bbox(bbox, idx)
            
            # Save to file
            save_geojson(geojson, filename)
            
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

