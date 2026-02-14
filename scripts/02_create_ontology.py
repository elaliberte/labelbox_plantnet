"""
Step 2: Create a Labelbox ontology for the Brazilian Amazon tree species.

This script:
1. Reads the species list CSV from Step 1
2. Creates a Labelbox ontology with:
   - A Bounding Box tool called "tree"
   - A nested Radio classification called "species" with 2,464 options
   - Each option: name = scientific name, value = GBIF taxon ID
"""

import os
import sys
import csv
import labelbox as lb
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

# Load .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

if not LABELBOX_API_KEY or LABELBOX_API_KEY == "your_labelbox_api_key_here":
    print("ERROR: Please add your Labelbox API key to the .env file")
    sys.exit(1)

# ─── Read species list from CSV ──────────────────────────────────
csv_path = os.path.join(OUTPUT_DIR, "species_list.csv")

if not os.path.exists(csv_path):
    print(f"ERROR: Species list not found at {csv_path}")
    print("Please run 01_fetch_species.py first.")
    sys.exit(1)

species = []
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        species.append(row)

print(f"Loaded {len(species)} species from {csv_path}")

# ─── Build the species options list ─────────────────────────────
# Each option: name = scientific name (what botanist sees)
#              value = GBIF taxon ID (stable identifier)
print("Building species options for ontology...")

species_options = []
for sp in species:
    name = sp["scientific_name"].strip()
    gbif_id = str(sp["gbif_id"]).strip()
    
    # Skip any entries with missing data
    if not name or not gbif_id:
        print(f"  WARNING: Skipping species with missing data: {sp}")
        continue
    
    species_options.append(
        lb.Option(value=gbif_id, label=name)
    )

print(f"Created {len(species_options)} species options")

# ─── Build the ontology ─────────────────────────────────────────
print("Building ontology structure...")

ontology_builder = lb.OntologyBuilder(
    tools=[
        lb.Tool(
            tool=lb.Tool.Type.BBOX,
            name="tree",
            classifications=[
                lb.Classification(
                    class_type=lb.Classification.Type.RADIO,
                    name="species",
                    options=species_options
                )
            ]
        )
    ]
)

# ─── Connect to Labelbox and create the ontology ────────────────
print("Connecting to Labelbox...")
client = lb.Client(api_key=LABELBOX_API_KEY)

ONTOLOGY_NAME = "Brazilian Amazon Trees (xprize-final-trees)"

print(f"Creating ontology: '{ONTOLOGY_NAME}'")
print(f"  - 1 Bounding Box tool ('tree')")
print(f"  - 1 nested Radio classification ('species')")
print(f"  - {len(species_options)} species options")
print()

ontology = client.create_ontology(
    name=ONTOLOGY_NAME,
    normalized=ontology_builder.asdict(),
    media_type=lb.MediaType.Image
)

print(f"Ontology created successfully!")
print(f"  Ontology ID:   {ontology.uid}")
print(f"  Ontology name: {ontology.name}")
print(f"  URL: https://app.labelbox.com/ontology/{ontology.uid}")

# ─── Save ontology ID for later use ─────────────────────────────
ontology_id_path = os.path.join(OUTPUT_DIR, "ontology_id.txt")
with open(ontology_id_path, "w") as f:
    f.write(ontology.uid)
print(f"\nOntology ID saved to: {ontology_id_path}")

print("\nDone! You can now view the ontology in the Labelbox web app.")