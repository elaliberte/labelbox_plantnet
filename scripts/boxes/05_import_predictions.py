"""
Step 5: Import Pl@ntNet predictions into Labelbox as MAL pre-labels.
"""

import os
import sys
import json
import uuid
import traceback
import labelbox as lb
from dotenv import load_dotenv

# --- Paths ---------------------------------------------------------------
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
except NameError:
    PROJECT_ROOT = r"c:\Users\etien\OneDrive\Documents\projets\labelbox_plantnet"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "boxes")

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
    print("Client connected.")

    project = client.get_project(project_id)
    print(f"Project: {project.name}")

    # --- Load ontology ----------------------------------------------------
    ontology = project.ontology()
    print(f"Ontology: {ontology.name}")

    normalized = ontology.normalized

    # Find the "tree" bounding box tool
    tree_tool = None
    for tool in normalized["tools"]:
        if tool["name"] == "tree":
            tree_tool = tool
            break

    if not tree_tool:
        print("ERROR: Could not find 'tree' tool in ontology")
        sys.exit(1)

    tree_schema_id = tree_tool["featureSchemaId"]
    print(f"  Tool 'tree' schema ID: {tree_schema_id}")

    # Find the "species" radio classification nested inside "tree"
    species_cls = None
    for cls in tree_tool.get("classifications", []):
        if cls["name"] == "species":
            species_cls = cls
            break

    if not species_cls:
        print("ERROR: Could not find 'species' classification in 'tree' tool")
        sys.exit(1)

    species_schema_id = species_cls["featureSchemaId"]
    print(f"  Classification 'species' schema ID: {species_schema_id}")

    # Build lookup: GBIF ID -> option schema ID
    gbif_to_option = {}
    name_to_option = {}
    for opt in species_cls.get("options", []):
        gbif_to_option[opt["value"]] = opt["featureSchemaId"]
        name_to_option[opt["label"]] = opt["featureSchemaId"]
    print(f"  Species options loaded: {len(gbif_to_option)}")

    # --- Build NDJSON annotations -----------------------------------------
    print("\nBuilding annotations...")

    labels = []
    skipped_species = set()

    for img_filename, img_data in all_predictions.items():
        img_count = 0
        for pred in img_data["predictions"]:
            gbif_id = pred["gbif_id"]
            species_name = pred["species_name"]
            bbox = pred["bbox"]

            # Find the option schema ID for this species
            option_id = gbif_to_option.get(gbif_id)
            if option_id is None:
                option_id = name_to_option.get(species_name)
            if option_id is None:
                skipped_species.add(f"{species_name} (GBIF: {gbif_id})")
                continue

            annotation = {
                "uuid": str(uuid.uuid4()),
                "dataRow": {"globalKey": img_filename},
                "schemaId": tree_schema_id,
                "bbox": {
                    "top": bbox["top"],
                    "left": bbox["left"],
                    "height": bbox["height"],
                    "width": bbox["width"],
                },
                "classifications": [
                    {
                        "schemaId": species_schema_id,
                        "answer": {"schemaId": option_id},
                    }
                ],
            }
            labels.append(annotation)
            img_count += 1
        print(f"  {img_filename}: {img_count} boxes")

    print(f"\nTotal annotations: {len(labels)}")

    if skipped_species:
        print(f"\nWARNING: {len(skipped_species)} species not found in ontology:")
        for sp in sorted(skipped_species):
            print(f"  - {sp}")

    if len(labels) == 0:
        print("ERROR: No annotations to import!")
        sys.exit(1)

    # --- Save NDJSON for reference ----------------------------------------
    ndjson_path = os.path.join(OUTPUT_DIR, "mal_annotations.ndjson")
    with open(ndjson_path, "w", encoding="utf-8") as f:
        for label in labels:
            f.write(json.dumps(label) + "\n")
    print(f"Saved NDJSON to: {ndjson_path}")

    # --- Import as MAL pre-labels -----------------------------------------
    print(f"\nUploading {len(labels)} annotations as MAL pre-labels...")

    job = lb.MALPredictionImport.create_from_objects(
        client=client,
        project_id=project_id,
        name=f"plantnet-predictions-{uuid.uuid4().hex[:8]}",
        predictions=labels,
    )

    print("Waiting for import to complete...")
    job.wait_till_done()

    print(f"\nImport status: {job.state}")
    if job.errors:
        print(f"Errors ({len(job.errors)}):")
        for e in job.errors[:10]:
            print(f"  {e}")
    else:
        print("No errors!")

    # --- Summary ----------------------------------------------------------
    print("")
    print("=" * 60)
    print("MAL IMPORT COMPLETE")
    print("=" * 60)
    print(f"Project:     {project.name}")
    print(f"Annotations: {len(labels)} bounding boxes imported")
    print(f"Images:      {len(all_predictions)}")
    print("=" * 60)
    print(f"\nView your project at:")
    print(f"  https://app.labelbox.com/projects/{project_id}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n!!! UNCAUGHT ERROR !!!")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {e}")
        traceback.print_exc()