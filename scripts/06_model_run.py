"""
Step 6: Upload predictions to a Labelbox Model Run (with confidence scores).

Unlike MAL (step 05), Model Runs support confidence scores.
This enables active learning: sort images by model uncertainty,
then send the least-confident ones to labellers first.

Workflow:
1. Create a Model (linked to our ontology)
2. Create a Model Run ("iteration 1")
3. Send our data rows to the model run
4. Build prediction payloads WITH confidence scores
5. Upload predictions to the model run

Docs:
  - https://docs.labelbox.com/reference/upload-image-predictions
  - https://docs.labelbox.com/docs/active-learning
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
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
except NameError:
    PROJECT_ROOT = r"c:\Users\etien\OneDrive\Documents\projets\labelbox_plantnet"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

if not LABELBOX_API_KEY or LABELBOX_API_KEY == "your_labelbox_api_key_here":
    print("ERROR: Please add your Labelbox API key to the .env file")
    sys.exit(1)


def main():
    # --- Load predictions -------------------------------------------------
    predictions_path = os.path.join(OUTPUT_DIR, "plantnet_predictions.json")
    if not os.path.exists(predictions_path):
        print(f"ERROR: Predictions not found at {predictions_path}")
        print("Please run 04b_mock_predictions.py first.")
        sys.exit(1)

    with open(predictions_path, "r", encoding="utf-8") as f:
        all_predictions = json.load(f)
    print(f"Loaded predictions for {len(all_predictions)} image(s)")

    # --- Load project ID --------------------------------------------------
    project_id_path = os.path.join(OUTPUT_DIR, "project_id.txt")
    if not os.path.exists(project_id_path):
        print(f"ERROR: Project ID not found at {project_id_path}")
        sys.exit(1)

    with open(project_id_path, "r") as f:
        project_id = f.read().strip()
    print(f"Using project ID: {project_id}")

    # --- Connect to Labelbox ----------------------------------------------
    print("Connecting to Labelbox...")
    client = lb.Client(api_key=LABELBOX_API_KEY)
    project = client.get_project(project_id)
    print(f"Project: {project.name}")

    ontology = project.ontology()
    print(f"Ontology: {ontology.name} (ID: {ontology.uid})")

    # --- Get ontology tool/classification info ----------------------------
    normalized = ontology.normalized

    tree_tool = None
    for tool in normalized["tools"]:
        if tool["name"] == "tree":
            tree_tool = tool
            break
    if not tree_tool:
        print("ERROR: Could not find 'tree' tool in ontology")
        sys.exit(1)

    species_cls = None
    for cls in tree_tool.get("classifications", []):
        if cls["name"] == "species":
            species_cls = cls
            break
    if not species_cls:
        print("ERROR: Could not find 'species' classification")
        sys.exit(1)

    # Build lookup: GBIF ID -> option name, and name -> name
    # For Python annotation types, we use 'name' (= the option's value/label)
    gbif_to_name = {}
    name_set = set()
    for opt in species_cls.get("options", []):
        gbif_to_name[opt["value"]] = opt["label"]  # GBIF ID -> scientific name
        name_set.add(opt["label"])
    print(f"  Species options loaded: {len(gbif_to_name)}")

    # --- Create Model and Model Run ---------------------------------------
    print("\nCreating Model...")
    model_name = "PlantNet-xprize-trees-" + uuid.uuid4().hex[:8]
    model = client.create_model(
        name=model_name,
        ontology_id=ontology.uid,
    )
    print(f"  Model created: {model.name} (ID: {model.uid})")

    print("Creating Model Run...")
    model_run = model.create_model_run("iteration-1")
    print(f"  Model Run created: {model_run.name} (ID: {model_run.uid})")

    # Save model run ID for future reference
    model_run_path = os.path.join(OUTPUT_DIR, "model_run_id.txt")
    with open(model_run_path, "w") as f:
        f.write(model_run.uid)
    print(f"  Saved model run ID to: {model_run_path}")

    # --- Send data rows to model run --------------------------------------
    print("\nSending data rows to model run...")
    global_keys = list(all_predictions.keys())
    print(f"  Global keys: {global_keys}")
    model_run.upsert_data_rows(global_keys=global_keys)
    print("  Data rows sent.")

    # --- Build prediction payloads ----------------------------------------
    print("\nBuilding prediction payloads with confidence scores...")

    label_predictions = []
    skipped_species = set()

    for img_filename, img_data in all_predictions.items():
        annotations = []
        for pred in img_data["predictions"]:
            gbif_id = pred["gbif_id"]
            species_name = pred["species_name"]
            confidence = pred.get("confidence", 1.0)
            bbox = pred["bbox"]

            # Find the option name for this species
            option_name = gbif_to_name.get(gbif_id)
            if option_name is None:
                if species_name in name_set:
                    option_name = species_name
                else:
                    skipped_species.add(f"{species_name} (GBIF: {gbif_id})")
                    continue

            # Build bounding box with nested radio classification
            # Using Python annotation types (recommended by Labelbox)
            bbox_annotation = lb_types.ObjectAnnotation(
                name="tree",
                confidence=confidence,
                value=lb_types.Rectangle(
                    start=lb_types.Point(x=bbox["left"], y=bbox["top"]),
                    end=lb_types.Point(
                        x=bbox["left"] + bbox["width"],
                        y=bbox["top"] + bbox["height"],
                    ),
                ),
                classifications=[
                    lb_types.ClassificationAnnotation(
                        name="species",
                        value=lb_types.Radio(
                            answer=lb_types.ClassificationAnswer(
                                name=option_name,
                                confidence=confidence,
                            )
                        ),
                    )
                ],
            )
            annotations.append(bbox_annotation)

        if annotations:
            label = lb_types.Label(
                data={"global_key": img_filename},
                annotations=annotations,
            )
            label_predictions.append(label)
            print(f"  {img_filename}: {len(annotations)} boxes")

    print(f"\nTotal labels: {len(label_predictions)}")
    total_boxes = sum(len(lbl.annotations) for lbl in label_predictions)
    print(f"Total bounding boxes: {total_boxes}")

    if skipped_species:
        print(f"\nWARNING: {len(skipped_species)} species not found in ontology:")
        for sp in sorted(skipped_species):
            print(f"  - {sp}")

    if len(label_predictions) == 0:
        print("ERROR: No predictions to upload!")
        sys.exit(1)

    # --- Upload predictions to model run ----------------------------------
    print(f"\nUploading predictions to model run...")
    upload_job = model_run.add_predictions(
        name="plantnet-preds-" + uuid.uuid4().hex[:8],
        predictions=label_predictions,
    )

    print("Waiting for upload to complete...")
    upload_job.wait_till_done()

    print(f"\nUpload errors: {upload_job.errors}")
    print(f"Upload statuses: {upload_job.statuses}")

    # --- Summary ----------------------------------------------------------
    print("")
    print("=" * 60)
    print("MODEL RUN UPLOAD COMPLETE")
    print("=" * 60)
    print(f"Model:       {model.name}")
    print(f"Model Run:   {model_run.name}")
    print(f"Predictions: {total_boxes} bounding boxes with confidence scores")
    print(f"Images:      {len(label_predictions)}")
    print("=" * 60)
    print(f"\nNext steps (active learning):")
    print(f"  1. Go to Labelbox > Models > {model.name} > {model_run.name}")
    print(f"  2. Sort data rows by confidence (ascending)")
    print(f"  3. Select low-confidence images")
    print(f"  4. Send them to your labeling project as a batch")
    print(f"  5. Expert botanists label the most uncertain images first!")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n!!! UNCAUGHT ERROR !!!")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {e}")
        traceback.print_exc()