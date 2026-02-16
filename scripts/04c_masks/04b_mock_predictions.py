"""
Step 4 (masks): Load predictions from the bounding box workflow.

Since we don't have Pl@ntNet multi-species API access yet,
we re-use the mock predictions generated in the boxes workflow.
Copies output/boxes/plantnet_predictions.json → output/masks/plantnet_predictions.json
"""

import os
import sys
import json
import shutil

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BOXES_DIR = os.path.join(PROJECT_ROOT, "output", "boxes")
MASKS_DIR = os.path.join(PROJECT_ROOT, "output", "masks")
os.makedirs(MASKS_DIR, exist_ok=True)

SOURCE_PATH = os.path.join(BOXES_DIR, "plantnet_predictions.json")
DEST_PATH = os.path.join(MASKS_DIR, "plantnet_predictions.json")


def main():
    # ─── Check source file exists ────────────────────────────────
    if not os.path.exists(SOURCE_PATH):
        print(f"ERROR: Source file not found: {SOURCE_PATH}")
        print(f"Run scripts/boxes/04b_mock_predictions.py first.")
        sys.exit(1)

    # ─── Load and inspect ────────────────────────────────────────
    with open(SOURCE_PATH, "r", encoding="utf-8") as f:
        predictions = json.load(f)

    print(f"Loaded predictions from: {SOURCE_PATH}")
    print(f"  Images: {len(predictions)}")

    total_tiles = 0
    total_species = set()
    for img_file, data in predictions.items():
        preds = data.get("predictions", [])
        total_tiles += data.get("nb_tiles", 0)
        for p in preds:
            species = p.get("species_name", "")
            if species:
                total_species.add(species)
        print(f"  {img_file}: {data.get('nb_tiles', 0)} tiles, "
              f"{len(preds)} predictions, "
              f"{data.get('nb_species', 0)} species")

    print(f"\n  Total tiles (across all images): {total_tiles}")
    print(f"  Unique species (across all images): {len(total_species)}")
    for sp in sorted(total_species):
        print(f"    - {sp}")

    # ─── Copy to masks output folder ─────────────────────────────
    shutil.copy2(SOURCE_PATH, DEST_PATH)
    print(f"\nCopied to: {DEST_PATH}")

    print(f"\n{'='*60}")
    print(f"PREDICTIONS READY FOR MASK BUILDING")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()