"""
07_import_predictions.py – Import segmentation mask predictions as MAL pre-labels
into a Labelbox Project so annotators see them directly in the editor.
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
PROJECT_ID_FILE = os.path.join(OUT, "project_id.txt")


def main():
    # ── connect ────────────────────────────────────────────────────────
    api_key = os.getenv("LABELBOX_API_KEY")
    if not api_key:
        raise SystemExit("Missing LABELBOX_API_KEY in .env")
    client = lb.Client(api_key=api_key)

    # ── load project ID ────────────────────────────────────────────────
    with open(PROJECT_ID_FILE) as f:
        project_id = f.read().strip()
    print(f"Project ID: {project_id}")

    # ── load mask summary ──────────────────────────────────────────────
    with open(SUMMARY) as f:
        mask_summary = json.load(f)

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

            annotation = lb_types.ObjectAnnotation(
                name="Plant",
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
                                value=sp["gbif_id"],
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

    # ── import as MAL pre-labels ───────────────────────────────────────
    mal_job = lb.MALPredictionImport.create_from_objects(
        client=client,
        project_id=project_id,
        name="mal-mask-import-" + uuid.uuid4().hex[:6],
        predictions=labels,
    )
    mal_job.wait_till_done()

    print(f"\nErrors: {mal_job.errors}")
    print(f"Status: {mal_job.statuses}")


if __name__ == "__main__":
    main()