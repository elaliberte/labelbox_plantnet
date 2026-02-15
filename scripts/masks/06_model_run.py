"""
06_model_run.py – Upload segmentation mask predictions to Labelbox Model Run
Uses Python annotation types (confidence on masks is not actually supported by Labelbox, despite what docs say).
"""

import json
import os
import uuid
import labelbox as lb
import labelbox.types as lb_types
from dotenv import load_dotenv

# ── paths ──────────────────────────────────────────────────────────────
ROOT = r"c:\Users\etien\OneDrive\Documents\projets\labelbox_plantnet"
load_dotenv(os.path.join(ROOT, ".env"))

OUT = os.path.join(ROOT, "output", "masks")
SUMMARY = os.path.join(OUT, "mask_summary.json")
ONTOLOGY_ID_FILE = os.path.join(OUT, "ontology_id.txt")
PROJECT_ID_FILE = os.path.join(OUT, "project_id.txt")


def main():
    # ── connect ────────────────────────────────────────────────────────
    api_key = os.getenv("LABELBOX_API_KEY")
    if not api_key:
        raise SystemExit("Missing LABELBOX_API_KEY in .env")
    client = lb.Client(api_key=api_key)

    # ── load IDs ───────────────────────────────────────────────────────
    with open(ONTOLOGY_ID_FILE) as f:
        ontology_id = f.read().strip()

    # ── load mask summary ──────────────────────────────────────────────
    with open(SUMMARY) as f:
        mask_summary = json.load(f)

    # ── create model + model run ───────────────────────────────────────
    ontology = client.get_ontology(ontology_id)
    model = client.create_model(
        name="PlantNet-Segmentation-" + uuid.uuid4().hex[:6],
        ontology_id=ontology.uid,
    )
    print(f"Model created: {model.name} ({model.uid})")

    model_run = model.create_model_run("mask-predictions-v1")
    print(f"Model Run created: {model_run.name} ({model_run.uid})")

    # ── send data rows ─────────────────────────────────────────────────
    global_keys = [f"mask_{img}" for img in mask_summary.keys()]
    model_run.upsert_data_rows(global_keys=global_keys)
    print(f"Sent {len(global_keys)} data rows to model run")

    # ── build predictions using Python annotation types ────────────────
    labels = []

    for img_file, img_data in mask_summary.items():
        global_key = f"mask_{img_file}"
        composite_abs_path = os.path.join(ROOT, img_data["composite_mask_path"])

        # Load mask from local file (SDK handles upload internally)
        mask_data = lb_types.MaskData(file_path=composite_abs_path)
        print(f"  Loaded mask for {img_file}")

        annotations = []
        for sp in img_data["species"]:
            confidence = sp["max_confidence"]
            color = tuple(sp["color_rgb"])

            # NOTE: Labelbox does not support confidence on segmentation masks.
            # confidence is placed on ObjectAnnotation for completeness,
            # but it will be ignored/defaulted to 1 by the API.
            annotation = lb_types.ObjectAnnotation(
                name="Plant",
                confidence=confidence,
                value=lb_types.Mask(
                    mask=mask_data,
                    color=color,
                ),
                classifications=[
                    lb_types.ClassificationAnnotation(
                        name="species",
                        value=lb_types.Radio(
                            answer=lb_types.ClassificationAnswer(
                                name=sp["species_name"],
                                confidence=confidence,
                                value=sp["gbif_id"]
                            )
                        ),
                    )
                ],
            )
            annotations.append(annotation)

        label = lb_types.Label(
            data=lb_types.GenericDataRowData(global_key=global_key),
            annotations=annotations,
        )
        labels.append(label)

    print(f"\nTotal labels: {len(labels)}")
    total_annots = sum(len(l.annotations) for l in labels)
    print(f"Total mask annotations: {total_annots}")

    # ── upload predictions ─────────────────────────────────────────────
    upload_job = model_run.add_predictions(
        name="mask-pred-upload-" + uuid.uuid4().hex[:6],
        predictions=labels,
    )
    upload_job.wait_till_done()

    print(f"\nErrors: {upload_job.errors}")
    print(f"Status: {upload_job.statuses}")
    print(f"\nModel Run ID: {model_run.uid}")


if __name__ == "__main__":
    main()