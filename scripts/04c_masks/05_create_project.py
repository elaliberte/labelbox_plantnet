"""
Step 5: Create a Labelbox project for segmentation mask labeling and connect
the ontology. Does NOT create a batch — that is done via the UI.

Inputs:
  - config.yaml
  - output/masks/ontology_id.txt

Outputs:
  - output/masks/project_id.txt
"""

import os
import sys
import yaml
import labelbox as lb
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

with open(os.path.join(PROJECT_ROOT, "config.yaml"), "r") as f:
    cfg = yaml.safe_load(f)

lb_cfg = cfg["labelbox"]
MASKS_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_masks"])

# Config values
PROJECT_NAME = lb_cfg["project_name_masks"]
PROJECT_DESCRIPTION = lb_cfg["project_description_masks"]

# ─── Load ontology ID ───────────────────────────────────────────
with open(os.path.join(MASKS_DIR, "ontology_id.txt")) as f:
    ontology_id = f.read().strip()
print(f"Ontology ID: {ontology_id}")

# ─── Connect to Labelbox ────────────────────────────────────────
API_KEY = os.getenv("LABELBOX_API_KEY")
if not API_KEY:
    sys.exit("ERROR: LABELBOX_API_KEY not found in .env")

client = lb.Client(api_key=API_KEY)
print("Connected to Labelbox")

ontology = client.get_ontology(ontology_id)
print(f"Ontology: {ontology.name}")

# ─── Create or find Project ─────────────────────────────────────
print(f"\nLooking for Project: {PROJECT_NAME}")
project = None
for p in client.get_projects():
    if p.name == PROJECT_NAME:
        project = p
        print(f"  Found existing Project: {project.uid}")
        break

if project is None:
    print(f"  Creating new Project: {PROJECT_NAME}")
    project = client.create_project(
        name=PROJECT_NAME,
        description=PROJECT_DESCRIPTION,
        media_type=lb.MediaType.Image,
    )
    print(f"  Project ID: {project.uid}")

    # Connect ontology
    print(f"  Connecting ontology: {ontology.name}")
    project.connect_ontology(ontology)
    print(f"  Ontology connected.")
else:
    print(f"  Project already exists, skipping ontology setup.")

# ─── Save project ID ────────────────────────────────────────────
project_id_path = os.path.join(MASKS_DIR, "project_id.txt")
with open(project_id_path, "w") as f:
    f.write(project.uid)

print(f"""
==================================================
PROJECT READY (Segmentation Masks)
==================================================
Name: {PROJECT_NAME}
ID:   {project.uid}
Ontology: {ontology.name} ({ontology.uid})
Saved to: {project_id_path}
==================================================
""")