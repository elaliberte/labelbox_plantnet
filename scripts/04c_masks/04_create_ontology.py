"""
Step 4: Create a Labelbox ontology for segmentation mask labeling.

The ontology has one RASTER_SEGMENTATION tool ("Plant") with a nested
Radio classification ("Species") containing all ~2,464 taxa from the
Pl@ntNet 'Trees of the Brazilian Amazon' project.

Inputs:
  - config.yaml
  - output/species/species_list.csv

Outputs:
  - output/masks/ontology_id.txt
"""

import os
import sys
import csv
import yaml
import labelbox as lb
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

with open(os.path.join(PROJECT_ROOT, "config.yaml"), "r") as f:
    cfg = yaml.safe_load(f)

lb_cfg = cfg["labelbox"]
SPECIES_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_species"])
MASKS_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_masks"])
os.makedirs(MASKS_DIR, exist_ok=True)

# Config values
ONTOLOGY_NAME = lb_cfg["ontology_name_masks"]
TOOL_NAME = lb_cfg["tool_name"]
TOOL_COLOR = lb_cfg["tool_color"]
CLASSIFICATION_NAME = lb_cfg["classification_name"]
CLASSIFICATION_INSTRUCTIONS = lb_cfg["classification_instructions"]

# ─── Load species list ───────────────────────────────────────────
species_path = os.path.join(SPECIES_DIR, "species_list.csv")
species = []
with open(species_path, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        species.append(row)

print(f"Loaded {len(species)} species from {species_path}")

# ─── Build ontology options ──────────────────────────────────────
options = []
for sp in species:
    options.append(
        lb.Option(
            value=sp["gbif_id"],
            label=sp["scientific_name"],
        )
    )

print(f"Built {len(options)} radio options")

# ─── Build ontology ──────────────────────────────────────────────
ontology_builder = lb.OntologyBuilder(
    tools=[
        lb.Tool(
            tool=lb.Tool.Type.RASTER_SEGMENTATION,
            name=TOOL_NAME,
            color=TOOL_COLOR,
            classifications=[
                lb.Classification(
                    class_type=lb.Classification.Type.RADIO,
                    name=CLASSIFICATION_NAME,
                    instructions=CLASSIFICATION_INSTRUCTIONS,
                    options=options,
                )
            ],
        )
    ]
)

# ─── Connect to Labelbox ────────────────────────────────────────
API_KEY = os.getenv("LABELBOX_API_KEY")
if not API_KEY:
    sys.exit("ERROR: LABELBOX_API_KEY not found in .env")

client = lb.Client(api_key=API_KEY)
print("\nConnected to Labelbox")

# ─── Create or find ontology ────────────────────────────────────
print(f"\nLooking for ontology: {ONTOLOGY_NAME}")
ontology = None
for o in client.get_ontologies(ONTOLOGY_NAME):
    if o.name == ONTOLOGY_NAME:
        ontology = o
        print(f"  Found existing ontology: {ontology.uid}")
        break

if ontology is None:
    print(f"  Creating new ontology: {ONTOLOGY_NAME}")
    ontology = client.create_ontology(
        ONTOLOGY_NAME,
        ontology_builder.asdict(),
        media_type=lb.MediaType.Image,
    )
    print(f"  Ontology ID: {ontology.uid}")

# ─── Save ontology ID ───────────────────────────────────────────
ontology_id_path = os.path.join(MASKS_DIR, "ontology_id.txt")
with open(ontology_id_path, "w") as f:
    f.write(ontology.uid)

print(f"""
==================================================
ONTOLOGY READY (Segmentation Masks)
==================================================
Name: {ONTOLOGY_NAME}
ID:   {ontology.uid}
Tool: {TOOL_NAME} (RASTER_SEGMENTATION)
Species options: {len(options)}
Saved to: {ontology_id_path}
==================================================
""")