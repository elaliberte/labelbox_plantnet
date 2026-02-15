"""
Step 3: Create a Labelbox project and upload test images.

This script:
1. Reads images from the images/ folder
2. Uploads them to a Labelbox dataset
3. Creates a labeling project connected to our ontology
4. Sends the images to the project as a batch
"""

import os
import sys
import uuid
import labelbox as lb
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")

# Load .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

if not LABELBOX_API_KEY or LABELBOX_API_KEY == "your_labelbox_api_key_here":
    print("ERROR: Please add your Labelbox API key to the .env file")
    sys.exit(1)

# ─── Read ontology ID from Step 2 ───────────────────────────────
ontology_id_path = os.path.join(OUTPUT_DIR, "ontology_id.txt")
if not os.path.exists(ontology_id_path):
    print(f"ERROR: Ontology ID not found at {ontology_id_path}")
    print("Please run 02_create_ontology.py first.")
    sys.exit(1)

with open(ontology_id_path, "r") as f:
    ontology_id = f.read().strip()
print(f"Using ontology ID: {ontology_id}")

# ─── Find images ────────────────────────────────────────────────
VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png')
image_files = sorted([
    f for f in os.listdir(IMAGES_DIR)
    if f.lower().endswith(VALID_EXTENSIONS)
])

if not image_files:
    print(f"ERROR: No images found in {IMAGES_DIR}")
    print(f"Please add .jpg or .png images to the images/ folder.")
    sys.exit(1)

print(f"Found {len(image_files)} image(s) in {IMAGES_DIR}:")
for img in image_files:
    print(f"  - {img}")

# ─── Connect to Labelbox ────────────────────────────────────────
print("\nConnecting to Labelbox...")
client = lb.Client(api_key=LABELBOX_API_KEY)

# ─── Create a dataset ───────────────────────────────────────────
DATASET_NAME = "Brazilian Amazon Drone Photos"
print(f"Creating dataset: '{DATASET_NAME}'")
dataset = client.create_dataset(name=DATASET_NAME)
print(f"  Dataset ID: {dataset.uid}")

# ─── Upload images to the dataset ───────────────────────────────
print(f"\nUploading {len(image_files)} image(s) to dataset...")

data_rows = []
for img_filename in image_files:
    img_path = os.path.join(IMAGES_DIR, img_filename)
    
    # Use the filename (without extension) as the global key
    # Global keys must be unique across your entire Labelbox workspace
    global_key = img_filename
    
    data_rows.append({
        "row_data": img_path,       # local file path — Labelbox will upload it
        "global_key": global_key,
        "media_type": "IMAGE",
    })

task = dataset.create_data_rows(data_rows)
task.wait_till_done()

print(f"  Upload complete!")
print(f"  Errors: {task.errors}")
print(f"  Failed rows: {task.failed_data_rows}")

if task.errors:
    print("WARNING: Some uploads had errors. Check above.")

# ─── Create a labeling project ──────────────────────────────────
PROJECT_NAME = "Amazon Trees - PlantNet MAL Demo"
print(f"\nCreating project: '{PROJECT_NAME}'")

project = client.create_project(
    name=PROJECT_NAME,
    media_type=lb.MediaType.Image
)
print(f"  Project ID: {project.uid}")

# Connect the ontology
ontology = client.get_ontology(ontology_id)
project.connect_ontology(ontology)
print(f"  Connected to ontology: {ontology.name}")

# ─── Send images to the project as a batch ──────────────────────
print(f"\nSending images to project as a batch...")

global_keys = [img for img in image_files]

batch = project.create_batch(
    name="drone-photos-batch-1",
    global_keys=global_keys,
    priority=1  # highest priority
)
print(f"  Batch created: {batch.name}")

# ─── Save project ID for later use ──────────────────────────────
project_id_path = os.path.join(OUTPUT_DIR, "project_id.txt")
with open(project_id_path, "w") as f:
    f.write(project.uid)
print(f"\nProject ID saved to: {project_id_path}")

# ─── Summary ────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"PROJECT SETUP COMPLETE")
print(f"{'='*50}")
print(f"Dataset:  {DATASET_NAME} ({dataset.uid})")
print(f"Project:  {PROJECT_NAME} ({project.uid})")
print(f"Ontology: {ontology.name} ({ontology_id})")
print(f"Images:   {len(image_files)}")
print(f"{'='*50}")
print(f"\nView your project at:")
print(f"  https://app.labelbox.com/projects/{project.uid}")