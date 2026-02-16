"""
Step 6: Import bounding box predictions into a Labelbox Model Run.

This script:
1. Loads multi_predictions.json from output/predictions/
2. Filters predictions per photo:
   a. Only keep tiles with score >= confidence_threshold (from config)
   b. Skip species with empty scientific_name or missing gbif_id
   c. Keep only the single best tile (highest score) per species per photo
3. Creates a Model and Model Run in Labelbox
4. Sends data rows (images) to the Model Run
5. Builds bounding box + nested radio prediction payloads
6. Uploads predictions to the Model Run

Requires:
  - output/boxes/ontology_id.txt  (from 01_create_ontology.py)
  - output/boxes/dataset_id.txt   (from 04_upload_images.py)
  - output/predictions/multi_predictions.json (from 03b_multi_predict.py)
  - config.yaml with model_name_boxes, model_run_name_boxes, confidence_threshold_boxes
"""

import os
import sys
import json
import uuid
import yaml
import labelbox as lb
import labelbox.types as lb_types
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

if not LABELBOX_API_KEY or LABELBOX_API_KEY == "your_labelbox_api_key_here":
    print("ERROR: Please add your Labelbox API key to the .env file")
    sys.exit(1)

# ─── Load config ─────────────────────────────────────────────────
config_path = os.path.join(PROJECT_ROOT, "config.yaml")
with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

lb_cfg = config["labelbox"]
TOOL_NAME = lb_cfg["tool_name"]
CLASSIFICATION_NAME = lb_cfg["classification_name"]
CLASSIFICATION_INSTRUCTIONS = lb_cfg["classification_instructions"]
GLOBAL_KEY_PREFIX = lb_cfg["global_key_prefix"]
MODEL_NAME = lb_cfg["model_name_boxes"]
MODEL_RUN_NAME = lb_cfg["model_run_name_boxes"]
CONFIDENCE_THRESHOLD = lb_cfg["confidence_threshold_boxes"]

PREDICTIONS_DIR = os.path.join(PROJECT_ROOT, config["folders"]["output_predictions"])
BOXES_DIR = os.path.join(PROJECT_ROOT, config["folders"]["output_boxes"])

os.makedirs(BOXES_DIR, exist_ok=True)

# ─── Load ontology ID ───────────────────────────────────────────
ontology_id_path = os.path.join(BOXES_DIR, "ontology_id.txt")
if not os.path.exists(ontology_id_path):
    print(f"ERROR: ontology_id.txt not found at {ontology_id_path}")
    print("  Run 01_create_ontology.py first.")
    sys.exit(1)

with open(ontology_id_path, "r") as f:
    ontology_id = f.read().strip()

print(f"Ontology ID: {ontology_id}")

# ─── Load predictions ───────────────────────────────────────────
predictions_path = os.path.join(PREDICTIONS_DIR, "multi_predictions.json")
if not os.path.exists(predictions_path):
    print(f"ERROR: multi_predictions.json not found at {predictions_path}")
    print("  Run 03b_multi_predict.py first.")
    sys.exit(1)

with open(predictions_path, "r", encoding="utf-8") as f:
    all_predictions = json.load(f)

print(f"Loaded predictions for {len(all_predictions)} image(s)")
print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")

# ─── Filter predictions ─────────────────────────────────────────
# For each photo:
#   1. Only consider tiles with score >= CONFIDENCE_THRESHOLD
#   2. Skip species with empty scientific_name or missing gbif_id
#   3. Keep only the single best tile (highest score) per species

filtered_data = []  # list of {global_key, annotations: [...]}

for img_pred in all_predictions:
    img_filename = img_pred["image"]
    global_key = f"{GLOBAL_KEY_PREFIX}{img_filename}"

    # Collect best tile per species for this image
    best_per_species = {}  # key: scientific_name -> best tile dict

    for species in img_pred.get("species", []):
        sci_name = species.get("scientific_name", "").strip()
        gbif_id = species.get("gbif_id", "")

        # Skip species with no name or no GBIF ID
        if not sci_name:
            continue
        if not gbif_id:
            continue

        # Find the best tile above threshold for this species
        for tile in species.get("tiles", []):
            score = tile.get("score", 0)
            if score < CONFIDENCE_THRESHOLD:
                continue

            # Is this the best tile so far for this species?
            if sci_name not in best_per_species or score > best_per_species[sci_name]["score"]:
                best_per_species[sci_name] = {
                    "scientific_name": sci_name,
                    "gbif_id": str(gbif_id),
                    "score": score,
                    "box_left": tile["box_left"],
                    "box_top": tile["box_top"],
                    "box_width": tile["box_width"],
                    "box_height": tile["box_height"],
                }

    filtered_data.append({
        "global_key": global_key,
        "image": img_filename,
        "boxes": list(best_per_species.values()),
    })

    n_boxes = len(best_per_species)
    print(f"  {img_filename}: {n_boxes} species above threshold")

total_boxes = sum(len(d["boxes"]) for d in filtered_data)
images_with_boxes = sum(1 for d in filtered_data if d["boxes"])
print(f"\nTotal filtered boxes: {total_boxes} across {images_with_boxes} image(s)")

if total_boxes == 0:
    print("WARNING: No predictions above threshold. Nothing to upload.")
    print("  Consider lowering confidence_threshold_boxes in config.yaml.")
    sys.exit(0)

# ─── Connect to Labelbox ────────────────────────────────────────
client = lb.Client(api_key=LABELBOX_API_KEY)
print(f"\nConnected to Labelbox")

# ─── Create or get Model ─────────────────────────────────────────
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
        ontology_id=ontology_id,
    )
    print(f"  Model ID: {model.uid}")

# ─── Create or get Model Run ────────────────────────────────────
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
# We send ALL images (even those with no predictions above threshold)
all_global_keys = [d["global_key"] for d in filtered_data]
print(f"\nSending {len(all_global_keys)} data row(s) to Model Run...")
model_run.upsert_data_rows(global_keys=all_global_keys)
print("  Done.")

# ─── Build prediction payloads ──────────────────────────────────
print(f"\nBuilding prediction payloads...")

labels = []

for img_data in filtered_data:
    global_key = img_data["global_key"]
    boxes = img_data["boxes"]

    if not boxes:
        # No predictions for this image — skip (data row is still in Model Run)
        continue

    annotations = []
    for box in boxes:
        # The nested radio classification: species name
        # 'name' must match the classification_name in the ontology ("Species")
        # 'answer name' must match an Option name in the ontology (scientific_name)
        species_classification = lb_types.ClassificationAnnotation(
            name=CLASSIFICATION_INSTRUCTIONS,
            value=lb_types.Radio(
                answer=lb_types.ClassificationAnswer(
                    name=box["scientific_name"],
                    confidence=box["score"],
                )
            ),
        )

        # The bounding box with nested classification
        # 'name' must match the tool name in the ontology ("Plant")
        bbox_annotation = lb_types.ObjectAnnotation(
            name=TOOL_NAME,
            confidence=box["score"],
            value=lb_types.Rectangle(
                start=lb_types.Point(
                    x=box["box_left"],
                    y=box["box_top"],
                ),
                end=lb_types.Point(
                    x=box["box_left"] + box["box_width"],
                    y=box["box_top"] + box["box_height"],
                ),
            ),
            classifications=[species_classification],
        )

        annotations.append(bbox_annotation)

    label = lb_types.Label(
        data={"global_key": global_key},
        annotations=annotations,
    )
    labels.append(label)

print(f"  Built {len(labels)} label(s) with {total_boxes} total box prediction(s)")

# ─── Upload predictions to Model Run ────────────────────────────
print(f"\nUploading predictions to Model Run...")
upload_job = model_run.add_predictions(
    name="prediction_upload_" + str(uuid.uuid4()),
    predictions=labels,
)

print(f"  Errors: {upload_job.errors}")
print(f"  Statuses: {upload_job.statuses}")

# ─── Save summary ───────────────────────────────────────────────
summary = {
    "model_name": MODEL_NAME,
    "model_id": model.uid,
    "model_run_name": MODEL_RUN_NAME,
    "model_run_id": model_run.uid,
    "ontology_id": ontology_id,
    "confidence_threshold": CONFIDENCE_THRESHOLD,
    "total_images": len(filtered_data),
    "images_with_predictions": images_with_boxes,
    "total_boxes": total_boxes,
    "filtered_predictions": filtered_data,
}

summary_path = os.path.join(BOXES_DIR, "model_run_summary.json")
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

# Save model run ID for later scripts
model_run_id_path = os.path.join(BOXES_DIR, "model_run_id.txt")
with open(model_run_id_path, "w") as f:
    f.write(model_run.uid)

model_id_path = os.path.join(BOXES_DIR, "model_id.txt")
with open(model_id_path, "w") as f:
    f.write(model.uid)

print(f"\n{'='*50}")
print(f"MODEL RUN PREDICTIONS UPLOADED")
print(f"{'='*50}")
print(f"Model: {MODEL_NAME} ({model.uid})")
print(f"Model Run: {MODEL_RUN_NAME} ({model_run.uid})")
print(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
print(f"Images in Model Run: {len(filtered_data)}")
print(f"Images with predictions: {images_with_boxes}")
print(f"Total bounding boxes: {total_boxes}")
print(f"Summary saved to: {summary_path}")
print(f"Model Run ID saved to: {model_run_id_path}")
print(f"{'='*50}")