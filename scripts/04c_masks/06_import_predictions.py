"""
Step 6: Convert Pl@ntNet survey tile predictions into segmentation masks and
upload them to a Labelbox Model Run.

For each image:
  1. Filter species with at least one tile above confidence threshold
  2. For each species, keep only the tile with the highest confidence
  3. Assign a unique RGB color to each species
  4. Paint tiles onto a blank canvas (same size as original image),
     ordered from lowest to highest confidence so that higher-confidence
     species overwrite overlapping pixels
  5. Save the composite mask PNG
  6. Upload as Mask predictions to a Labelbox Model Run

Inputs:
  - config.yaml
  - output/masks/ontology_id.txt
  - output/predictions/multi_predictions.json
  - output/images/dataset_id.txt
  - images/*.JPG  (to read dimensions)

Outputs:
  - output/masks/composite_masks/<filename>.png  (one per image)
  - output/masks/model_run_id.txt
  - output/masks/model_run_summary.json
"""

import os
import sys
import json
import yaml
import uuid
import hashlib
import numpy as np
from PIL import Image
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
MASKS_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_masks"])
PREDICTIONS_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_predictions"])
IMAGES_DIR_PATH = os.path.join(PROJECT_ROOT, cfg["folders"]["images"])
DATASET_ID_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_images"])

COMPOSITE_DIR = os.path.join(MASKS_DIR, "composite_masks")
os.makedirs(COMPOSITE_DIR, exist_ok=True)

# Config values
TOOL_NAME = lb_cfg["tool_name"]
CLASSIFICATION_INSTRUCTIONS = lb_cfg["classification_instructions"]
GLOBAL_KEY_PREFIX = lb_cfg["global_key_prefix"]
CONFIDENCE_THRESHOLD = lb_cfg["confidence_threshold_boxes"]  # reuse same threshold
MODEL_NAME = lb_cfg["model_name_masks"]
MODEL_DESCRIPTION = lb_cfg["model_description_masks"]
MODEL_RUN_NAME = lb_cfg["model_run_name_masks"]

# ─── Load IDs ────────────────────────────────────────────────────
with open(os.path.join(MASKS_DIR, "ontology_id.txt")) as f:
    ontology_id = f.read().strip()
print(f"Ontology ID: {ontology_id}")

with open(os.path.join(DATASET_ID_DIR, "dataset_id.txt")) as f:
    dataset_id = f.read().strip()
print(f"Dataset ID: {dataset_id}")

# ─── Load predictions ───────────────────────────────────────────
predictions_path = os.path.join(PREDICTIONS_DIR, "multi_predictions.json")
with open(predictions_path) as f:
    all_predictions = json.load(f)
print(f"Loaded predictions for {len(all_predictions)} image(s)")
print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")


# ─── Helper: deterministic color from species name ───────────────
def species_color(scientific_name):
    """Generate a unique, deterministic RGB color from a species name.
    Avoids black (0,0,0) which is the background."""
    h = hashlib.md5(scientific_name.encode()).digest()
    r, g, b = h[0], h[1], h[2]
    # Avoid pure black (background)
    if r == 0 and g == 0 and b == 0:
        r = 1
    return (r, g, b)


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

# ─── Build mask predictions ──────────────────────────────────────
print(f"\nBuilding mask predictions...")

labels = []
total_masks = 0

for img_entry in all_predictions:
    img_filename = img_entry["image"]
    img_w = img_entry["width"]
    img_h = img_entry["height"]
    global_key = f"{GLOBAL_KEY_PREFIX}{img_filename}"

    # ── Filter species: keep only those with best tile >= threshold ─
    species_list = []
    for sp in img_entry.get("species", []):
        # Find the tile with the highest score for this species
        tiles = sp.get("tiles", [])
        if not tiles:
            continue
        best_tile = max(tiles, key=lambda t: t["score"])
        if best_tile["score"] >= CONFIDENCE_THRESHOLD:
            species_list.append({
                "scientific_name": sp["scientific_name"],
                "score": best_tile["score"],
                "tile": best_tile,
            })

    if not species_list:
        continue

    # ── Sort from lowest to highest confidence ───────────────────
    # Paint lowest first so highest overwrites overlapping pixels
    species_list.sort(key=lambda s: s["score"])

    # ── Paint composite mask ─────────────────────────────────────
    composite = np.zeros((img_h, img_w, 3), dtype=np.uint8)
    color_map = {}

    for sp_info in species_list:
        sp_name = sp_info["scientific_name"]
        tile = sp_info["tile"]
        color = species_color(sp_name)
        color_map[sp_name] = color

        # Paint this species' best tile onto the composite
        x1 = max(0, tile["box_left"])
        y1 = max(0, tile["box_top"])
        x2 = min(img_w, tile["box_left"] + tile["box_width"])
        y2 = min(img_h, tile["box_top"] + tile["box_height"])
        composite[y1:y2, x1:x2] = color

    # Save composite mask PNG
    mask_filename = os.path.splitext(img_filename)[0] + "_mask.png"
    mask_path = os.path.join(COMPOSITE_DIR, mask_filename)
    Image.fromarray(composite).save(mask_path)

    # Read mask bytes for upload
    with open(mask_path, "rb") as f:
        mask_bytes = f.read()

    mask_data = lb_types.MaskData(im_bytes=mask_bytes)

    # ── Create one ObjectAnnotation per species ──────────────────
    annotations = []
    for sp_info in species_list:
        sp_name = sp_info["scientific_name"]
        color = color_map[sp_name]

        species_classification = lb_types.ClassificationAnnotation(
            name=CLASSIFICATION_INSTRUCTIONS,
            value=lb_types.Radio(
                answer=lb_types.ClassificationAnswer(
                    name=sp_name,
                    confidence=sp_info["score"],
                )
            ),
        )

        mask_annotation = lb_types.ObjectAnnotation(
            name=TOOL_NAME,
            confidence=sp_info["score"],
            value=lb_types.Mask(
                mask=mask_data,
                color=color,
            ),
            classifications=[species_classification],
        )
        annotations.append(mask_annotation)

    labels.append(
        lb_types.Label(
            data={"global_key": global_key},
            annotations=annotations,
        )
    )
    n_species = len(species_list)
    total_masks += n_species
    print(f"  {img_filename}: {n_species} species masks, "
          f"image {img_w}x{img_h}, "
          f"saved {mask_filename}")

print(f"\n  Total: {total_masks} mask annotations across {len(labels)} image(s)")

# ─── Upload predictions to Model Run ────────────────────────────
print(f"\nUploading predictions to Model Run...")

upload_job = model_run.add_predictions(
    name="mask_predictions_" + str(uuid.uuid4()),
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
mr_id_path = os.path.join(MASKS_DIR, "model_run_id.txt")
with open(mr_id_path, "w") as f:
    f.write(model_run.uid)

# ─── Summary ─────────────────────────────────────────────────────
summary = {
    "model_name": MODEL_NAME,
    "model_id": model.uid,
    "model_run_name": MODEL_RUN_NAME,
    "model_run_id": model_run.uid,
    "confidence_threshold": CONFIDENCE_THRESHOLD,
    "images_processed": len(labels),
    "total_mask_annotations": total_masks,
    "composite_masks_dir": COMPOSITE_DIR,
    "upload_success": n_success,
    "upload_failure": n_failure,
    "timestamp": datetime.now().isoformat(),
}

summary_path = os.path.join(MASKS_DIR, "model_run_summary.json")
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)

print(f"""
==================================================
MASK PREDICTIONS UPLOADED
==================================================
Model: {MODEL_NAME} ({model.uid})
Model Run: {MODEL_RUN_NAME} ({model_run.uid})
Confidence threshold: {CONFIDENCE_THRESHOLD}
Images: {len(labels)}
Mask annotations: {total_masks}
Composite masks saved to: {COMPOSITE_DIR}
Upload: {n_success} success, {n_failure} failure
Model Run ID saved to: {mr_id_path}
Summary saved to: {summary_path}
==================================================
""")