"""
Step 5 (class): Import Pl@ntNet top-1 predictions into a Labelbox Model Run.

Creates a Model + Model Run, sends data rows, and uploads
predictions with confidence scores for active learning.
"""

import os
import sys
import json
import uuid
import traceback
import labelbox as lb
import labelbox.types as lb_types
from dotenv import load_dotenv

# --- Paths ---------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "class")

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

if not LABELBOX_API_KEY or LABELBOX_API_KEY == "your_labelbox_api_key_here":
    print("ERROR: Please add your Labelbox API key to the .env file")
    sys.exit(1)


def main():
    # --- Load IDs ---------------------------------------------------------
    with open(os.path.join(OUTPUT_DIR, "project_id.txt")) as f:
        project_id = f.read().strip()
    with open(os.path.join(OUTPUT_DIR, "ontology_id.txt")) as f:
        ontology_id = f.read().strip()

    print(f"Project ID:  {project_id}")
    print(f"Ontology ID: {ontology_id}")

    # --- Load predictions -------------------------------------------------
    pred_path = os.path.join(OUTPUT_DIR, "plantnet_predictions.json")
    with open(pred_path, "r", encoding="utf-8") as f:
        predictions = json.load(f)
    print(f"Loaded predictions for {len(predictions)} images")

    # --- Connect to Labelbox ----------------------------------------------
    print("\nConnecting to Labelbox...")
    client = lb.Client(api_key=LABELBOX_API_KEY)

    project = client.get_project(project_id)
    ontology = client.get_ontology(ontology_id)
    print(f"Project:  {project.name}")
    print(f"Ontology: {ontology.name}")

    # --- Find the 'species' classification and build lookup ---------------
    species_feature = None
    for c in ontology.normalized["classifications"]:
        if c["name"] == "species":
            species_feature = c
            break

    if not species_feature:
        print("ERROR: Could not find 'species' classification in ontology")
        sys.exit(1)

    print(f"\nSpecies classification schema ID: {species_feature['featureSchemaId']}")

    # Build lookup: gbif_id -> option info
    option_lookup = {}
    for opt in species_feature["options"]:
        option_lookup[opt["value"]] = {
            "schema_id": opt["featureSchemaId"],
            "label": opt["label"],
        }
    print(f"  {len(option_lookup)} species options in ontology")

    # --- Step 1: Create Model + Model Run ---------------------------------
    print("\n--- Creating Model and Model Run ---")
    model = client.create_model(
        name="PlantNet-Classification-" + uuid.uuid4().hex[:8],
        ontology_id=ontology.uid,
    )
    print(f"  Model created: {model.name} (ID: {model.uid})")

    model_run = model.create_model_run("plantnet-run-1")
    print(f"  Model Run created: plantnet-run-1 (ID: {model_run.uid})")

    # Save IDs for future reference
    with open(os.path.join(OUTPUT_DIR, "model_id.txt"), "w") as f:
        f.write(model.uid)
    with open(os.path.join(OUTPUT_DIR, "model_run_id.txt"), "w") as f:
        f.write(model_run.uid)

    # --- Step 2: Send data rows to model run ------------------------------
    print("\n--- Sending data rows to Model Run ---")
    global_keys = ["class_" + img_file for img_file in predictions.keys()]
    model_run.upsert_data_rows(global_keys=global_keys)
    print(f"  Sent {len(global_keys)} data rows")

    # --- Step 3: Build prediction labels ----------------------------------
    print("\n--- Building predictions ---")
    label_predictions = []
    skipped = 0

    for img_file, data in predictions.items():
        preds = data.get("predictions", [])
        if not preds:
            print(f"  SKIP {img_file}: no predictions")
            skipped += 1
            continue

        top1 = preds[0]
        gbif_id = top1["gbif_id"]
        score = top1["score"]

        if gbif_id not in option_lookup:
            print(f"  SKIP {img_file}: GBIF ID {gbif_id} ({top1['scientific_name']}) not in ontology")
            skipped += 1
            continue

        option_info = option_lookup[gbif_id]
        global_key = "class_" + img_file

        label = lb_types.Label(
            data={"global_key": global_key},
            annotations=[
                lb_types.ClassificationAnnotation(
                    name="species",
                    value=lb_types.Radio(
                        answer=lb_types.ClassificationAnswer(
                            name=option_info["label"],
                            confidence=score,
                        )
                    ),
                )
            ],
        )
        label_predictions.append(label)
        print(f"  {img_file}: {top1['scientific_name']} (score={score:.4f}, GBIF={gbif_id})")

    print(f"\n  Predictions built: {len(label_predictions)}")
    if skipped:
        print(f"  Skipped: {skipped}")

    if not label_predictions:
        print("ERROR: No predictions to upload!")
        sys.exit(1)

    # --- Step 4: Upload predictions to model run --------------------------
    print("\n--- Uploading predictions to Model Run ---")
    upload_job = model_run.add_predictions(
        name="plantnet-pred-upload-" + uuid.uuid4().hex[:8],
        predictions=label_predictions,
    )
    upload_job.wait_till_done()

    print(f"\nUpload complete!")
    print(f"  Errors: {upload_job.errors}")
    print(f"  Statuses: {upload_job.statuses}")

    # --- Summary ----------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"MODEL RUN IMPORT COMPLETE")
    print(f"{'='*60}")
    print(f"  Model:     {model.name}")
    print(f"  Model Run: plantnet-run-1")
    print(f"  Predictions uploaded: {len(label_predictions)}")
    print(f"  Skipped: {skipped}")
    print(f"\nView project: https://app.labelbox.com/projects/{project_id}")
    print(f"View model:   https://app.labelbox.com/models/{model.uid}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n!!! UNCAUGHT ERROR !!!")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {e}")
        traceback.print_exc()