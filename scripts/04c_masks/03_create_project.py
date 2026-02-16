"""
Step 3 (masks): Create Labelbox project, upload images, create batch.

Creates a project 'Amazon Trees - Segmentation Demo', uploads images
from the images/ folder, and creates a batch.
Saves project_id.txt and dataset_id.txt to output/masks/.
"""

import os
import sys
import labelbox as lb
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "masks")
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

if not LABELBOX_API_KEY or LABELBOX_API_KEY == "your_labelbox_api_key_here":
    print("ERROR: Please add your Labelbox API key to the .env file")
    sys.exit(1)


def main():
    # ─── Load ontology ID ────────────────────────────────────────
    ontology_id_path = os.path.join(OUTPUT_DIR, "ontology_id.txt")
    if not os.path.exists(ontology_id_path):
        print("ERROR: ontology_id.txt not found. Run 02_create_ontology.py first.")
        sys.exit(1)

    with open(ontology_id_path) as f:
        ontology_id = f.read().strip()
    print(f"Ontology ID: {ontology_id}")

    # ─── Find images ─────────────────────────────────────────────
    image_files = sorted([
        f for f in os.listdir(IMAGES_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    if not image_files:
        print(f"ERROR: No images found in {IMAGES_DIR}")
        sys.exit(1)

    print(f"Found {len(image_files)} images in {IMAGES_DIR}")
    for img in image_files:
        print(f"  {img}")

    # ─── Connect to Labelbox ─────────────────────────────────────
    print("\nConnecting to Labelbox...")
    client = lb.Client(api_key=LABELBOX_API_KEY)

    # ─── Create dataset and upload images ────────────────────────
    dataset = client.create_dataset(name="Amazon Trees - Segmentation Dataset")
    print(f"\nDataset created: {dataset.name} (ID: {dataset.uid})")

    data_rows = []
    for img_file in image_files:
        img_path = os.path.join(IMAGES_DIR, img_file)
        global_key = "mask_" + img_file
        data_rows.append({
            "row_data": img_path,
            "global_key": global_key,
            "media_type": "IMAGE",
        })

    print(f"Uploading {len(data_rows)} images...")
    task = dataset.create_data_rows(data_rows)
    task.wait_till_done()
    print(f"  Upload complete!")
    if task.errors:
        print(f"  Errors: {task.errors}")

    # ─── Create project ──────────────────────────────────────────
    project = client.create_project(
        name="Amazon Trees - Segmentation Demo",
        media_type=lb.MediaType.Image,
    )
    print(f"\nProject created: {project.name} (ID: {project.uid})")

    # Connect ontology
    ontology = client.get_ontology(ontology_id)
    project.connect_ontology(ontology)
    print(f"  Connected ontology: {ontology.name}")

    # Create batch
    global_keys = ["mask_" + f for f in image_files]
    project.create_batch(
        "drone-photos-batch-1",
        global_keys=global_keys,
        priority=1,
    )
    print(f"  Created batch with {len(global_keys)} images")

    # ─── Save IDs ────────────────────────────────────────────────
    with open(os.path.join(OUTPUT_DIR, "project_id.txt"), "w") as f:
        f.write(project.uid)
    with open(os.path.join(OUTPUT_DIR, "dataset_id.txt"), "w") as f:
        f.write(dataset.uid)

    # ─── Summary ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"PROJECT READY")
    print(f"{'='*60}")
    print(f"  Project ID:  {project.uid}")
    print(f"  Dataset ID:  {dataset.uid}")
    print(f"  Ontology:    {ontology.name}")
    print(f"  Images:      {len(image_files)}")
    print(f"  Global keys: mask_<filename>")
    print(f"\n  View: https://app.labelbox.com/projects/{project.uid}")


if __name__ == "__main__":
    main()