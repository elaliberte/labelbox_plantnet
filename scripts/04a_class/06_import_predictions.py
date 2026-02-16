"""
Step 6: Import Pl@ntNet single-species predictions (top-1) as global Radio
classification predictions into a Labelbox Model Run.

For each image:
  - Take the top-1 result (results[0])
  - Create a ClassificationAnnotation with the species name + confidence

Inputs:
  - config.yaml
  - output/class/ontology_id.txt
  - output/predictions/single_predictions.json
  - output/images/dataset_id.txt

Outputs:
  - output/class/model_run_id.txt
  - output/class/model_run_summary.json
"""

import os
import sys
import json
import yaml
import uuid
import labelbox as lb
import labelbox.types as lb_types
from dotenv import load_dotenv
from datetime import datetime

# ─── Paths ───────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

with open(os.path.join(PROJECT_ROOT, "config.yaml"), "r") as f:
    cfg = yaml.safe_load(f)

lb_cfg = cfg["labelbox"]
CLASS_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_class"])
PREDICTIONS_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_predictions"])
DATASET_ID_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_images"])

# Config values
CLASSIFICATION_INSTRUCTIONS = lb_cfg["classification_instructions"]
GLOBAL_KEY_PREFIX = lb_cfg["global_key_prefix"]
MODEL_NAME = lb_cfg["model_name_class"]
MODEL_DESCRIPTION = lb_cfg["model_description_class"]
MODEL_RUN_NAME = lb_cfg["model_run_name_class"]

# ─── Load IDs ────────────────────────────────────────────────────
with open(os.path.join(CLASS_DIR, "ontology_id.txt")) as f:
    ontology_id = f.read().strip()
print(f"Ontology ID: {ontology_id}")

with open(os.path.join(DATASET_ID_DIR, "dataset_id.txt")) as f:
    dataset_id = f.read().strip()
print(f"Dataset ID: {dataset_id}")

# ─── Load predictions ───────────────────────────────────────────
predictions_path = os.path.join(PREDICTIONS_DIR, "single_predictions.json")
with open(predictions_path) as f:
    all_predictions = json.load(f)
print(f"Loaded predictions for {len(all_predictions)} image(s)")

# ─── Connect to Labelbox ────────────────────────────────────────
API_KEY = os.getenv("LABELBOX_API_KEY")
if not API_KEY:
    sys.exit("ERROR: LABELBOX_API_KEY not found in .env")

client = lb.Client(api_key=API_KEY)
print("\nConnected to Labelbox")

ontology = client.get_ontology(ontology_id)
print(f"Ontology: {ontology.name}")

# ─── Get dataset and collect global keys ────────────────────────
dataset = client.get_dataset(dataset_id)
global_keys = []
for dr in dataset.data_rows():
    global_keys.append(dr.global_key)
print(f"Dataset: {dataset.name} ({len(global_keys)} data rows)")

# ─── Create or find Model ───────────────────────────────────────
print(f"\nLooking for Model: {MODEL_NAME}")
model = None
for m in client.get_models():
    if m.name == MODEL_NAME:
        model = m
        print(f"  Found existing Model: {model.uid}")
        break

if model is None:
    print(f"  Creating new Model: {MODEL_NAME}")
    model = client.create_model(
        name=MODEL_NAME,
        ontology_id=ontology.uid,
    )
    print(f"  Model ID: {model.uid}")

# ─── Create or find Model Run ───────────────────────────────────
print(f"Looking for Model Run: {MODEL_RUN_NAME}")
model_run = None
for mr in model.model_runs():
    if mr.name == MODEL_RUN_NAME:
        model_run = mr
        print(f"  Found existing Model Run: {model_run.uid}")
        break

if model_run is None:
    print(f"  Creating new Model Run: {MODEL_RUN_NAME}")
    model_run = model.create_model_run(MODEL_RUN_NAME)
    print(f"  Model Run ID: {model_run.uid}")

# ─── Send data rows to Model Run ────────────────────────────────
print(f"\nSending {len(global_keys)} data row(s) to Model Run...")
model_run.upsert_data_rows(global_keys=global_keys)
print(f"  Done.")

# ─── Build classification predictions ────────────────────────────
print(f"\nBuilding classification predictions...")

labels = []
skipped = 0

for img_entry in all_predictions:
    img_filename = img_entry["image"]
    global_key = f"{GLOBAL_KEY_PREFIX}{img_filename}"

    results = img_entry.get("results", [])
    if not results:
        print(f"  {img_filename}: no results, skipping")
        skipped += 1
        continue

    # Top-1 prediction
    top1 = results[0]
    sp_name = top1["scientific_name"]
    score = top1["score"]

    # Global Radio classification — one per image
    radio_prediction = lb_types.ClassificationAnnotation(
        name=CLASSIFICATION_INSTRUCTIONS,
        value=lb_types.Radio(
            answer=lb_types.ClassificationAnswer(
                name=sp_name,
                confidence=score,
            )
        ),
    )

    labels.append(
        lb_types.Label(
            data={"global_key": global_key},
            annotations=[radio_prediction],
        )
    )
    print(f"  {img_filename}: {sp_name} (score={score:.5f})")

print(f"\n  Total: {len(labels)} predictions, {skipped} skipped")

# ─── Upload predictions to Model Run ────────────────────────────
print(f"\nUploading predictions to Model Run...")

upload_job = model_run.add_predictions(
    name="class_predictions_" + str(uuid.uuid4()),
    predictions=labels,
)

upload_job.wait_till_done()

print(f"  Errors: {upload_job.errors}")

n_success = sum(1 for s in upload_job.statuses if s.get("status") == "SUCCESS")
n_failure = sum(1 for s in upload_job.statuses if s.get("status") == "FAILURE")
print(f"  Success: {n_success}, Failure: {n_failure}")

if upload_job.errors:
    for err in upload_job.errors[:5]:
        print(f"    {err}")

# ─── Save Model Run ID ──────────────────────────────────────────
mr_id_path = os.path.join(CLASS_DIR, "model_run_id.txt")
with open(mr_id_path, "w") as f:
    f.write(model_run.uid)

# ─── Summary ─────────────────────────────────────────────────────
summary = {
    "model_name": MODEL_NAME,
    "model_id": model.uid,
    "model_run_name": MODEL_RUN_NAME,
    "model_run_id": model_run.uid,
    "images_processed": len(labels),
    "images_skipped": skipped,
    "upload_success": n_success,
    "upload_failure": n_failure,
    "timestamp": datetime.now().isoformat(),
}

summary_path = os.path.join(CLASS_DIR, "model_run_summary.json")
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)

print(f"""
==================================================
CLASSIFICATION PREDICTIONS UPLOADED
==================================================
Model: {MODEL_NAME} ({model.uid})
Model Run: {MODEL_RUN_NAME} ({model_run.uid})
Images: {len(labels)} predicted, {skipped} skipped
Upload: {n_success} success, {n_failure} failure
Model Run ID saved to: {mr_id_path}
Summary saved to: {summary_path}
==================================================
""")