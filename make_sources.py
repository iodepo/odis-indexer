# make the source.yaml file starting from ODISCat
#
# run 'python make_sources.py'

import json
import httpx
import yaml
import os
from datetime import datetime
import re
from indexer.config import load_config
from indexer.elasticsearch_client import build_client, bulk_index

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def index_to_es(sources, config_path):
    print("Indexing sources to Elasticsearch...")
    try:
        cfg = load_config(config_path)
        client = build_client(cfg.search.endpoint)
        index_name = "odiscat"
        
        # Prepare documents
        documents = []
        for s in sources:
            doc = s.copy()
            doc["_id"] = s["sourceid"]
            documents.append(doc)
        
        success, bulk_errors = bulk_index(client, index_name, documents)
        print(f"ES Indexing complete: {success} successes, {len(bulk_errors)} errors")
    except Exception as e:
        print(f"Error indexing to ES: {e}")

def main():
    url = "https://catalogue.odis.org/odis-arch-records"
    # Determine script directory to use absolute paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sources_path = os.path.join(script_dir, "sources.yaml")
    config_path = os.path.join(script_dir, "config.yaml")
    
    print(f"Fetching records from {url}...")
    try:
        response = httpx.get(url)
        response.raise_for_status()
        records = response.json()
    except Exception as e:
        print(f"Error fetching records: {e}")
        return

    new_sources = []
    used_sourceids = set()
    for rec in records:
        # Mapping fields
        # ds_name_english -> name
        # ds_url -> domain
        # odis_arch_url -> url
        # odis_arch_type -> sourcetype
        # id -> odiscatid
        
        sourceid = slugify(rec.get("ds_name_english", ""))
        counter = 1
        while sourceid in used_sourceids:
            sourceid = f"{sourceid}-{counter}"
            counter += 1
        
        used_sourceids.add(sourceid)
        
        source_entry = {
            "sourceid": sourceid,
            "name": rec.get("ds_name_english", ""),
            "domain": rec.get("ds_url", ""),
            "odiscatid": rec.get('id'),
            "sourcetype": rec.get("odis_arch_type", "").lower(),
            "url": rec.get("odis_arch_url", ""),
            "changefreq": "daily", # Defaulting as seen in original
            "backend": "Custom",    # Defaulting
            "headless": False,      # Defaulting
            "active": True          # Defaulting
        }
        # Special case for headless if needed, but per instructions we just match fields
        if source_entry["sourcetype"] == "sitegraph":
             source_entry["headless"] = False # Matches original logic usually
        
        new_sources.append(source_entry)

    output_data = {"sources": new_sources}

    # Backup existing sources.yaml
    if os.path.exists(sources_path):
        today = datetime.now().strftime("%Y%m%d")
        backup_path = f"{sources_path}_{today}"
        print(f"Backing up {sources_path} to {backup_path}...")
        os.rename(sources_path, backup_path)

    # Write new sources.yaml
    print(f"Writing new {sources_path}...")
    with open(sources_path, 'w') as f:
        yaml.dump(output_data, f, sort_keys=False, default_flow_style=False)
    
    # Index to ES
    index_to_es(new_sources, config_path)
    
    print("Done!")

if __name__ == "__main__":
    main()
