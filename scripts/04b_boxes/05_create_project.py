"""
Step 5: Create an empty Labelbox project for bounding box labeling.

This script:
1. Reads the ontology ID from output/boxes/ontology_id.txt
2. Creates an empty Labelbox project (with description)
3. Connects it to the bounding box ontology
4. Saves the project ID to output/boxes/project_id.txt

Images are NOT sent here — that's done in step 05.
The ontology ID is passed between steps via file, not config.yaml,
because it changes every time you create a new ontology.
"""

import os
import sys
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

OUTPUT_DIR = os.path.join(PROJECT_ROOT, config["folders"]["output_boxes"])
PROJECT_NAME = config["labelbox"]["project_name_boxes"]
PROJECT_DESC = config["labelbox"].get("project_description_boxes", "")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Read ontology ID from step 03 ──────────────────────────────
ontology_id_path = os.path.join(OUTPUT_DIR, "ontology_id.txt")
if not os.path.exists(ontology_id_path):
    print(f"ERROR: Ontology ID not found at {ontology_id_path}")
    print("Please run 03_create_ontology.py first.")
    sys.exit(1)

with open(ontology_id_path, "r") as f:
    ontology_id = f.read().strip()
print(f"Using ontology ID: {ontology_id}")

# ─── Connect to Labelbox ────────────────────────────────────────
print("Connecting to Labelbox...")
client = lb.Client(api_key=LABELBOX_API_KEY)

# ─── Create the project ─────────────────────────────────────────
print(f"Creating project: '{PROJECT_NAME}'")
if PROJECT_DESC:
    print(f"  Description: {PROJECT_DESC}")

project = client.create_project(
    name=PROJECT_NAME,
    description=PROJECT_DESC,
    media_type=lb.MediaType.Image
)
print(f"  Project ID: {project.uid}")

# ─── Connect the ontology ───────────────────────────────────────
ontology = client.get_ontology(ontology_id)
project.connect_ontology(ontology)
print(f"  Connected to ontology: {ontology.name} ({ontology_id})")

# ─── Save project ID ────────────────────────────────────────────
project_id_path = os.path.join(OUTPUT_DIR, "project_id.txt")
with open(project_id_path, "w") as f:
    f.write(project.uid)
print(f"\nProject ID saved to: {project_id_path}")

# ─── Summary ────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"PROJECT CREATED (empty — no images yet)")
print(f"{'='*50}")
print(f"Project:     {PROJECT_NAME}")
print(f"Description: {PROJECT_DESC}")
print(f"Project ID:  {project.uid}")
print(f"Ontology:    {ontology.name} ({ontology_id})")
print(f"{'='*50}")
print(f"\nView your project at:")
print(f"  https://app.labelbox.com/projects/{project.uid}")
print(f"\nNext step: run 05_send_batch.py to send images to this project.")