"""
Step 1: Fetch the species list from a Pl@ntNet microproject.

This script:
1. Reads the project slug and settings from config.yaml
2. Calls the Pl@ntNet API to get all species (paginated)
3. Extracts: scientific name (without author), GBIF taxon ID, family, genus
4. Saves species_raw.json and species_list.csv to output/species/

Run once — the species list is shared by all workflows (boxes, class, masks).

Pl@ntNet pagination uses "page" and "pageSize" parameters.
See: https://my.plantnet.org/doc/api/taxonomy
"""

import os
import sys
import json
import csv
import requests
import yaml
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Load .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")

if not PLANTNET_API_KEY or PLANTNET_API_KEY == "your_plantnet_api_key_here":
    print("ERROR: Please add your Pl@ntNet API key to the .env file")
    sys.exit(1)

# ─── Load config ─────────────────────────────────────────────────
config_path = os.path.join(PROJECT_ROOT, "config.yaml")
if not os.path.exists(config_path):
    print(f"ERROR: config.yaml not found at {config_path}")
    sys.exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

PROJECT = config["plantnet"]["project"]
PROJECT_NAME = config["plantnet"]["project_name"]
API_BASE = config["plantnet"]["api_base"]
PAGE_SIZE = config["plantnet"]["species_page_size"]
OUTPUT_DIR = os.path.join(PROJECT_ROOT, config["folders"]["output_species"])

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── API URL ─────────────────────────────────────────────────────
SPECIES_URL = f"{API_BASE}/v2/projects/{PROJECT}/species"

# ─── Fetch ALL species using pagination ──────────────────────────
print(f"Project: {PROJECT_NAME} ({PROJECT})")
print(f"URL: {SPECIES_URL}")
print(f"Page size: {PAGE_SIZE}")
print()

all_raw_species = []
page = 1

while True:
    params = {
        "api-key": PLANTNET_API_KEY,
        "lang": "en",
        "pageSize": PAGE_SIZE,
        "page": page,
    }

    response = requests.get(SPECIES_URL, params=params)

    if response.status_code != 200:
        print(f"ERROR: API returned status code {response.status_code}")
        print(f"Response: {response.text}")
        sys.exit(1)

    page_data = response.json()

    # The response is a list of species objects
    if isinstance(page_data, list):
        page_species = page_data
    elif isinstance(page_data, dict):
        for key in ["species", "data", "results"]:
            if key in page_data:
                page_species = page_data[key]
                break
        else:
            print(f"Unexpected response structure. Keys: {list(page_data.keys())}")
            print(json.dumps(page_data, indent=2)[:500])
            sys.exit(1)
    else:
        print(f"Unexpected response type: {type(page_data)}")
        sys.exit(1)

    count = len(page_species)
    all_raw_species.extend(page_species)
    print(f"  Page {page}: fetched {count} species (total so far: {len(all_raw_species)})")

    # If we got fewer than PAGE_SIZE, we've reached the last page
    if count < PAGE_SIZE:
        break

    page += 1

print(f"\nTotal species fetched: {len(all_raw_species)}")

# ─── Save raw JSON response (for reference) ─────────────────────
raw_output_path = os.path.join(OUTPUT_DIR, "species_raw.json")
with open(raw_output_path, "w", encoding="utf-8") as f:
    json.dump(all_raw_species, f, indent=2, ensure_ascii=False)
print(f"Raw JSON saved to: {raw_output_path}")

# ─── Extract relevant fields ────────────────────────────────────
species_list = []

for sp in all_raw_species:
    entry = {
        "scientific_name": sp.get("scientificNameWithoutAuthor", ""),
        "author": sp.get("scientificNameAuthorship", ""),
        "gbif_id": sp.get("gbifId", ""),
        "plantnet_id": sp.get("id", ""),
        "iucn_category": sp.get("iucnCategory", ""),
        "common_names": "; ".join(sp.get("commonNames", [])),
    }
    species_list.append(entry)

# Sort alphabetically by scientific name
species_list.sort(key=lambda x: x["scientific_name"])

# ─── Save as CSV ────────────────────────────────────────────────
csv_output_path = os.path.join(OUTPUT_DIR, "species_list.csv")
fieldnames = [
    "scientific_name", "author", "gbif_id", "plantnet_id",
    "iucn_category", "common_names"
]

with open(csv_output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(species_list)

print(f"Species list saved to: {csv_output_path}")

# ─── Summary stats ──────────────────────────────────────────────
total = len(species_list)
with_gbif = sum(1 for sp in species_list if sp["gbif_id"])
without_gbif = total - with_gbif

print(f"\n{'='*50}")
print(f"SPECIES LIST SUMMARY")
print(f"{'='*50}")
print(f"Total species:          {total}")
print(f"With GBIF taxon ID:     {with_gbif}")
print(f"Without GBIF taxon ID:  {without_gbif}")
print(f"{'='*50}")

# Show first 10 species as a preview
print(f"\nFirst 10 species (preview):")
print(f"{'Scientific Name':<40} {'GBIF ID':<12}")
print(f"{'-'*40} {'-'*12}")
for sp in species_list[:10]:
    print(f"{sp['scientific_name']:<40} {str(sp['gbif_id']):<12}")