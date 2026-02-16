"""
Step 3 (class): Create a Labelbox project, dataset, and upload images.

Creates:
  - A dataset with the 4 drone images
  - A project linked to the classification ontology
  - A batch sending all images to the project
"""

import os
import sys
import json
import traceback
import labelbox as lb
from dotenv import load_dotenv

# --- Paths ---------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # up 2 levels
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "class")
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

if not LABELBOX_API_KEY or LABELBOX_API_KEY == "your_labelbox_api_key_here":
    print("ERROR: Please add your Labelbox API key to the .env file")
    sys.exit(1)


def main():
    # --- Load ontology ID -------------------------------------------------
    ontology_id_path = os.path.join(OUTPUT_DIR, "ontology_id.txt")
    if not os.path.exists(ontology_id_path):
        print(f"ERROR: Ontology ID not found at {ontology_id_path}")
        print("Run 02_create_ontology.py first.")
        sys.exit(1)

    with open(ontology_id_path, "r") as f:
        ontology_id = f.read().strip()
    print(f"Ontology ID: {ontology_id}")

    # --- Find images ------------------------------------------------------
    image_files = sorted([
        f for f in os.listdir(IMAGES_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    if not image_files:
        print(f"ERROR: No images found in {IMAGES_DIR}")
        sys.exit(1)

    print(f"Found {len(image_files)} images in {IMAGES_DIR}:")
    for img in image_files:
        print(f"  - {img}")

    # --- Connect to Labelbox ----------------------------------------------
    print("\nConnecting to Labelbox...")
    client = lb.Client(api_key=LABELBOX_API_KEY)
    print("Connected.")

    # --- Create dataset ---------------------------------------------------
    DATASET_NAME = "Amazon Trees - Classification Photos"
    print(f"\nCreating dataset: '{DATASET_NAME}'")
    dataset = client.create_dataset(name=DATASET_NAME)
    print(f"  Dataset ID: {dataset.uid}")

    # Upload images (prefix global keys with "class_" to avoid conflicts with boxes workflow)
    data_rows = []
    for img_file in image_files:
        img_path = os.path.join(IMAGES_DIR, img_file)
        data_rows.append({
            "row_data": img_path,
            "global_key": "class_" + img_file,
        })

    print(f"  Uploading {len(data_rows)} images...")
    task = dataset.create_data_rows(data_rows)
    task.wait_till_done()
    print(f"  Done. Errors: {task.errors}")

    # --- Create project ---------------------------------------------------
    PROJECT_NAME = "Amazon Trees - Classification Demo"
    print(f"\nCreating project: '{PROJECT_NAME}'")
    project = client.create_project(
        name=PROJECT_NAME,
        media_type=lb.MediaType.Image,
    )
    print(f"  Project ID: {project.uid}")

    # Connect ontology
    ontology = client.get_ontology(ontology_id)
    project.connect_ontology(ontology)
    print(f"  Connected to ontology: {ontology.name}")

    # --- Create batch -----------------------------------------------------
    print("\nCreating batch...")
    global_keys = ["class_" + f for f in image_files]
    batch = project.create_batch(
        name="drone-photos-batch-1",
        global_keys=global_keys,
        priority=5,
    )
    print(f"  Batch: {batch.name}")

    # --- Save outputs -----------------------------------------------------
    project_id_path = os.path.join(OUTPUT_DIR, "project_id.txt")
    with open(project_id_path, "w") as f:
        f.write(project.uid)

    dataset_id_path = os.path.join(OUTPUT_DIR, "dataset_id.txt")
    with open(dataset_id_path, "w") as f:
        f.write(dataset.uid)

    gk_path = os.path.join(OUTPUT_DIR, "global_keys.json")
    with open(gk_path, "w") as f:
        json.dump(global_keys, f, indent=2)

    # --- Summary ----------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"PROJECT CREATED")
    print(f"{'='*60}")
    print(f"Dataset:     {DATASET_NAME} ({dataset.uid})")
    print(f"Project:     {PROJECT_NAME} ({project.uid})")
    print(f"Ontology:    {ontology.name} ({ontology.uid})")
    print(f"Images:      {len(image_files)}")
    print(f"Global keys: {global_keys}")
    print(f"{'='*60}")
    print(f"\nProject URL: https://app.labelbox.com/projects/{project.uid}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n!!! UNCAUGHT ERROR !!!")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {e}")
        traceback.print_exc()