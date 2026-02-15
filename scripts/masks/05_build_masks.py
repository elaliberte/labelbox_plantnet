"""
Step 5 (masks): Build COMPOSITE segmentation masks from tile predictions.

For each image, creates ONE composite RGB mask where each species
gets a unique color. Also saves a mask_summary.json with the
color-to-species mapping.

Saves composite masks to output/masks/mask_images/<image_name>/composite.png
Saves summary JSON to output/masks/mask_summary.json
"""

import os
import sys
import json
from collections import defaultdict
from PIL import Image, ImageDraw

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "masks")
MASKS_IMG_DIR = os.path.join(OUTPUT_DIR, "mask_images")
PREDICTIONS_PATH = os.path.join(OUTPUT_DIR, "plantnet_predictions.json")


def generate_distinct_colors(n):
    """Generate n visually distinct RGB colors (avoiding black = background)."""
    colors = []
    for i in range(n):
        # Use HSV-like distribution to get distinct colors
        hue = i / n
        # Convert hue to RGB (simplified, fully saturated, full brightness)
        r, g, b = 0, 0, 0
        sector = int(hue * 6) % 6
        frac = (hue * 6) - sector
        if sector == 0:
            r, g, b = 255, int(255 * frac), 0
        elif sector == 1:
            r, g, b = int(255 * (1 - frac)), 255, 0
        elif sector == 2:
            r, g, b = 0, 255, int(255 * frac)
        elif sector == 3:
            r, g, b = 0, int(255 * (1 - frac)), 255
        elif sector == 4:
            r, g, b = int(255 * frac), 0, 255
        elif sector == 5:
            r, g, b = 255, 0, int(255 * (1 - frac))
        # Ensure no color is (0,0,0) — that's background
        if r == 0 and g == 0 and b == 0:
            r = 1
        colors.append((r, g, b))
    return colors


def main():
    # ─── Load predictions ────────────────────────────────────────
    if not os.path.exists(PREDICTIONS_PATH):
        print(f"ERROR: {PREDICTIONS_PATH} not found. Run step 04 first.")
        sys.exit(1)

    with open(PREDICTIONS_PATH, "r", encoding="utf-8") as f:
        all_predictions = json.load(f)

    print(f"Loaded predictions for {len(all_predictions)} images")

    summary = {}
    total_masks = 0

    for img_file, img_data in all_predictions.items():
        img_w = img_data["image_width"]
        img_h = img_data["image_height"]
        predictions = img_data["predictions"]

        print(f"\n{'─'*60}")
        print(f"Image: {img_file} ({img_w}x{img_h})")
        print(f"  Predictions: {len(predictions)}")

        # ─── Group predictions by species ────────────────────────
        species_tiles = defaultdict(list)
        for p in predictions:
            key = (p["species_name"], p["gbif_id"])
            species_tiles[key].append(p)

        num_species = len(species_tiles)
        print(f"  Species: {num_species}")

        # ─── Assign a unique color to each species ───────────────
        sorted_species = sorted(species_tiles.keys())
        colors = generate_distinct_colors(num_species)
        species_color_map = dict(zip(sorted_species, colors))

        # ─── Create blank black RGB composite mask ───────────────
        composite = Image.new("RGB", (img_w, img_h), (0, 0, 0))
        draw = ImageDraw.Draw(composite)

        # ─── Create output folder for this image ────────────────
        img_mask_dir = os.path.join(MASKS_IMG_DIR, img_file)
        os.makedirs(img_mask_dir, exist_ok=True)

        image_summary = {
            "image_width": img_w,
            "image_height": img_h,
            "species": []
        }

        for (species_name, gbif_id) in sorted_species:
            preds = species_tiles[(species_name, gbif_id)]
            color = species_color_map[(species_name, gbif_id)]

            # ─── Draw tiles for this species in its unique color ─
            max_confidence = 0.0
            for p in preds:
                bbox = p["bbox"]
                left = max(0, bbox["left"])
                top = max(0, bbox["top"])
                right = min(img_w, bbox["left"] + bbox["width"])
                bottom = min(img_h, bbox["top"] + bbox["height"])

                draw.rectangle([left, top, right, bottom], fill=color)

                if p["confidence"] > max_confidence:
                    max_confidence = p["confidence"]

            image_summary["species"].append({
                "species_name": species_name,
                "gbif_id": gbif_id,
                "color_rgb": list(color),
                "max_confidence": round(max_confidence, 4),
                "num_tiles": len(preds),
            })

            total_masks += 1
            print(f"    {species_name} (GBIF {gbif_id}): "
                  f"{len(preds)} tiles, max conf {max_confidence:.4f}, "
                  f"color {color}")

        # ─── Save composite mask PNG ─────────────────────────────
        composite_path = os.path.join(img_mask_dir, "composite.png")
        composite.save(composite_path)
        image_summary["composite_mask_path"] = os.path.relpath(
            composite_path, PROJECT_ROOT
        )
        print(f"  Composite mask saved: {composite_path}")

        summary[img_file] = image_summary

    # ─── Save summary JSON ───────────────────────────────────────
    summary_path = os.path.join(OUTPUT_DIR, "mask_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"COMPOSITE MASK BUILDING COMPLETE")
    print(f"{'='*60}")
    print(f"  Total species masks: {total_masks}")
    print(f"  Composite masks saved to: {MASKS_IMG_DIR}")
    print(f"  Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()