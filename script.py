

import os
import re
import csv
import requests
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# Configuration - assuming you're running from the repo root
DOCS_PATH = "website/docs/r"  # Relative path from repo root
OUTPUT_FILE = "terraform_resources_with_tags.csv"
CSV_URL = "https://raw.githubusercontent.com/tfitzmac/resource-capabilities/main/tag-support.csv"

def verify_docs_path():
    """Verify the docs directory exists"""
    if not os.path.exists(DOCS_PATH):
        raise FileNotFoundError(
            f"Docs directory not found at: {os.path.abspath(DOCS_PATH)}\n"
            "Please run this script from the root of the terraform-provider-azurerm repository"
        )

def fetch_supported_resources():
    """Fetch resources that support tags from CSV"""
    try:
        response = requests.get(CSV_URL, timeout=10)
        response.raise_for_status()
        reader = csv.DictReader(response.text.splitlines())
        
        supported_resources = []
        for row in reader:
            if row.get('supportsTags', '').strip().upper() == 'TRUE':
                provider = row['providerName'].replace(" ", ".").lower()
                resource_type = row['resourceType']
                supported_resources.append(f"{provider}/{resource_type}")
        
        print(f"Found {len(supported_resources)} resources supporting tags")
        return supported_resources
    
    except Exception as e:
        print(f"Error fetching CSV: {e}")
        raise

def get_markdown_files():
    """Get all markdown files from docs directory"""
    markdown_files = []
    for root, _, files in os.walk(DOCS_PATH):
        for file in files:
            if file.endswith(".markdown"):
                markdown_files.append(os.path.join(root, file))
    
    if not markdown_files:
        raise FileNotFoundError(f"No markdown files found in {DOCS_PATH}")
    return markdown_files

def find_resource_matches(resource, markdown_files):
    """Find matching Terraform resources for a given Azure resource"""
    segments = resource.split('/')
    if len(segments) < 2:
        return None
    
    # Create search pattern that enforces one-word-per-segment
    search_pattern = re.escape(segments[0].lower())
    for segment in segments[1:]:
        if not segment or ' ' in segment:
            return None
        search_pattern += r'/[^/]+'
    
    matches = []
    for md_file in markdown_files:
        try:
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Match import lines with full provider paths
            for match in re.finditer(
                r'terraform\s+import\s+(azurerm_\w+)[^\n]*/providers/([^\s/]+(?:/[^/\s]+)*)',
                content,
                re.IGNORECASE
            ):
                tf_resource = match.group(1)
                provider_path = match.group(2).lower()
                
                if re.fullmatch(search_pattern, provider_path):
                    azure_type = '/'.join(provider_path.split('/')[1:])
                    matches.append((tf_resource, segments[0], azure_type))
        
        except Exception as e:
            print(f"Error processing {md_file}: {e}")
    
    return matches if matches else None

def main():
    try:
        verify_docs_path()
        resources = fetch_supported_resources()
        markdown_files = get_markdown_files()
        
        print(f"Searching {len(markdown_files)} markdown files...")
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=8) as executor:
            find_matches = partial(find_resource_matches, markdown_files=markdown_files)
            results = list(filter(None, executor.map(find_matches, resources)))
        
        # Flatten and deduplicate results
        flat_results = [item for sublist in results for item in sublist]
        unique_results = sorted(set(flat_results), key=lambda x: x[0])
        
        # Save to CSV
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["terraform_resource", "provider_name", "azure_resource_type"])
            writer.writerows(unique_results)
        
        print(f"\n✅ Found {len(unique_results)} matches. Sample results:")
        for res in unique_results[:10]:
            print(f"{res[0]} -> {res[1]}/{res[2]}")
        if len(unique_results) > 10:
            print(f"... plus {len(unique_results)-10} more")
        print(f"\nFull results saved to {OUTPUT_FILE}")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if isinstance(e, FileNotFoundError):
            print(f"Current directory: {os.getcwd()}")
            print(f"Expected docs path: {os.path.abspath(DOCS_PATH)}")
        raise

if __name__ == "__main__":
    main()

