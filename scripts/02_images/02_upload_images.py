"""
Step 2: Upload images to Labelbox as a shared dataset.

This script:
1. Reads images from the images/ folder
2. Creates a Labelbox dataset (or reuses an existing one)
3. Uploads each image as a data row with a global key = filename
4. Saves the dataset ID to output/images/dataset_id.txt

The same dataset is shared across all Labelbox projects
(boxes, classification, masks). Run this only once.

Docs: https://docs.labelbox.com/reference/dataset
"""

import os
import sys
import json
import yaml
import labelbox as lb
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

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

IMAGES_DIR = os.path.join(PROJECT_ROOT, config["folders"]["images"])
DATASET_NAME = config["labelbox"]["dataset_name"]
DATASET_DESC = config["labelbox"]["dataset_description"]
GLOBAL_KEY_PREFIX = config["labelbox"].get("global_key_prefix", "")

# ─── Find images ────────────────────────────────────────────────
VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png')
image_files = sorted([
    f for f in os.listdir(IMAGES_DIR)
    if f.lower().endswith(VALID_EXTENSIONS)
])

if not image_files:
    print(f"ERROR: No images found in {IMAGES_DIR}")
    sys.exit(1)

print(f"Found {len(image_files)} image(s) to upload")
print(f"Dataset name: {DATASET_NAME}")
print()

# ─── Connect to Labelbox ────────────────────────────────────────
client = lb.Client(api_key=LABELBOX_API_KEY)
print("Connected to Labelbox")

# ─── Create dataset ─────────────────────────────────────────────
dataset = client.create_dataset(
    name=DATASET_NAME,
    description=DATASET_DESC,
    iam_integration=None  # use Labelbox-hosted storage
)
print(f"Created dataset: {dataset.name} (ID: {dataset.uid})")

# ─── Upload images as data rows ─────────────────────────────────
data_rows = []

for img_filename in image_files:
    img_path = os.path.join(IMAGES_DIR, img_filename)
    global_key = f"{GLOBAL_KEY_PREFIX}{img_filename}"

    data_rows.append({
        "row_data": img_path,           # local file — Labelbox uploads it
        "global_key": global_key,
        "external_id": img_filename,    # original filename for reference
    })

print(f"\nUploading {len(data_rows)} image(s)...")

task = dataset.create_data_rows(data_rows)
task.wait_till_done()

if task.errors:
    print(f"\nERRORS during upload:")
    for err in task.errors:
        print(f"  {err}")
else:
    print(f"All {len(data_rows)} image(s) uploaded successfully!")

# ─── Save dataset ID ────────────────────────────────────────────
dataset_id_path = os.path.join(OUTPUT_DIR, "dataset_id.txt")
with open(dataset_id_path, "w") as f:
    f.write(dataset.uid)
print(f"\nDataset ID saved to: {dataset_id_path}")

# ─── Save upload summary ────────────────────────────────────────
summary = {
    "dataset_id": dataset.uid,
    "dataset_name": DATASET_NAME,
    "num_images": len(data_rows),
    "global_keys": [dr["global_key"] for dr in data_rows],
    "filenames": [dr["external_id"] for dr in data_rows],
}

summary_path = os.path.join(OUTPUT_DIR, "upload_summary.json")
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)
print(f"Upload summary saved to: {summary_path}")

# ─── Final summary ──────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"UPLOAD COMPLETE")
print(f"{'='*50}")
print(f"Dataset:    {DATASET_NAME}")
print(f"Dataset ID: {dataset.uid}")
print(f"Images:     {len(data_rows)}")
print()
print("Global keys:")
for dr in data_rows:
    print(f"  {dr['global_key']}")
print(f"{'='*50}")