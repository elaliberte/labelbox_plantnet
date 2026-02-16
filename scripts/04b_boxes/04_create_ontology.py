"""
Step 4: Create a Labelbox ontology for bounding box predictions.

This script:
1. Reads the shared species list CSV from output/species/
2. Creates a Labelbox ontology with:
   - A Bounding Box tool (name, color from config.yaml)
   - A nested Radio classification (name, instructions from config.yaml)
     with ~2,464 options
   - Each option: name = scientific name, value = GBIF taxon ID
3. Saves the ontology ID to output/boxes/ontology_id.txt

Run once per workflow. The species list is shared (from step 01).
"""

import os
import sys
import csv
import yaml
import labelbox as lb
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Load .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

if not LABELBOX_API_KEY or LABELBOX_API_KEY == "your_labelbox_api_key_here":
    print("ERROR: Please add your Labelbox API key to the .env file")
    sys.exit(1)

# ─── Load config ─────────────────────────────────────────────────
config_path = os.path.join(PROJECT_ROOT, "config.yaml")
if not os.path.exists(config_path):
    print(f"ERROR: config.yaml not found at {config_path}")
    sys.exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

SPECIES_DIR = os.path.join(PROJECT_ROOT, config["folders"]["output_species"])
OUTPUT_DIR = os.path.join(PROJECT_ROOT, config["folders"]["output_boxes"])
ONTOLOGY_NAME = config["labelbox"]["ontology_name_boxes"]
TOOL_NAME = config["labelbox"]["tool_name"]
TOOL_COLOR = config["labelbox"].get("tool_color", "#00ff00")
CLASSIFICATION_NAME = config["labelbox"]["classification_name"]
CLASSIFICATION_INSTRUCTIONS = config["labelbox"].get("classification_instructions", "Select the plant species.")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Read species list from shared CSV ───────────────────────────
csv_path = os.path.join(SPECIES_DIR, "species_list.csv")

if not os.path.exists(csv_path):
    print(f"ERROR: Species list not found at {csv_path}")
    print("Please run scripts/01_species/01_fetch_species.py first.")
    sys.exit(1)

species = []
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        species.append(row)

print(f"Loaded {len(species)} species from {csv_path}")

# ─── Build the species options list ─────────────────────────────
print("Building species options for ontology...")

species_options = []
skipped = 0
for sp in species:
    name = sp["scientific_name"].strip()
    gbif_id = str(sp["gbif_id"]).strip()

    if not name or not gbif_id:
        print(f"  WARNING: Skipping species with missing data: {sp}")
        skipped += 1
        continue

    species_options.append(
        lb.Option(value=gbif_id, label=name)
    )

print(f"Created {len(species_options)} species options (skipped {skipped})")

# ─── Build the ontology ─────────────────────────────────────────
print("Building ontology structure...")

ontology_builder = lb.OntologyBuilder(
    tools=[
        lb.Tool(
            tool=lb.Tool.Type.BBOX,
            name=TOOL_NAME,
            color=TOOL_COLOR,
            classifications=[
                lb.Classification(
                    class_type=lb.Classification.Type.RADIO,
                    name=CLASSIFICATION_NAME,
                    instructions=CLASSIFICATION_INSTRUCTIONS,
                    options=species_options
                )
            ]
        )
    ]
)

# ─── Connect to Labelbox and create the ontology ────────────────
print("Connecting to Labelbox...")
client = lb.Client(api_key=LABELBOX_API_KEY)

print(f"Creating ontology: '{ONTOLOGY_NAME}'")
print(f"  - 1 Bounding Box tool ('{TOOL_NAME}', color: {TOOL_COLOR})")
print(f"  - 1 nested Radio classification ('{CLASSIFICATION_NAME}')")
print(f"    Instructions: '{CLASSIFICATION_INSTRUCTIONS}'")
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

# ─── Save ontology ID ───────────────────────────────────────────
ontology_id_path = os.path.join(OUTPUT_DIR, "ontology_id.txt")
with open(ontology_id_path, "w") as f:
    f.write(ontology.uid)
print(f"\nOntology ID saved to: {ontology_id_path}")

print("\nDone! You can now view the ontology in the Labelbox web app.")