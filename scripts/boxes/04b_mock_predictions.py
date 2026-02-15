"""
Step 4b: Generate mock Pl@ntNet predictions for testing.

This script creates realistic fake predictions so we can test the full
Labelbox import pipeline while waiting for survey API access.

For each image in images/, it:
1. Creates a non-overlapping 518x518 tile grid (same as real API would)
2. Randomly assigns species from our species list to some tiles
3. Generates realistic confidence scores
4. Saves predictions in the same format as 04_plantnet_predict.py
"""

import os
import sys
import json
import csv
import random
from PIL import Image
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "boxes")
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Configuration ───────────────────────────────────────────────
TILE_SIZE = 518
TILE_STRIDE = 518     # no overlap
MIN_SCORE = 0.10
MATCH_PROBABILITY = 0.70  # 70% of tiles will have a species prediction

# Seed for reproducibility (remove this line for random results each run)
random.seed(42)

# ─── Load species list from Step 1 ──────────────────────────────
csv_path = os.path.join(OUTPUT_DIR, "species_list.csv")
if not os.path.exists(csv_path):
    print(f"ERROR: Species list not found at {csv_path}")
    print("Please run 01_fetch_species.py first.")
    sys.exit(1)

species_pool = []
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        species_pool.append(row)

print(f"Loaded {len(species_pool)} species from species list")

# Pick a smaller subset to simulate realistic results
# (a single drone photo won't have 2,464 species — maybe 5-15)
NUM_SPECIES_PER_IMAGE = 8  # each image will have predictions from ~8 species

# ─── Find images ────────────────────────────────────────────────
VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png')
image_files = sorted([
    f for f in os.listdir(IMAGES_DIR)
    if f.lower().endswith(VALID_EXTENSIONS)
])

if not image_files:
    print(f"ERROR: No images found in {IMAGES_DIR}")
    sys.exit(1)

print(f"Found {len(image_files)} image(s)")
print(f"Settings: tile_size={TILE_SIZE}, tile_stride={TILE_STRIDE}, "
      f"min_score={MIN_SCORE}")
print(f"Mock: {int(MATCH_PROBABILITY*100)}% of tiles will have predictions, "
      f"~{NUM_SPECIES_PER_IMAGE} species per image")
print()

# ─── Generate mock predictions for each image ───────────────────
all_predictions = {}

for i, img_filename in enumerate(image_files, 1):
    img_path = os.path.join(IMAGES_DIR, img_filename)

    with Image.open(img_path) as img:
        width, height = img.size

    print(f"{'='*60}")
    print(f"[{i}/{len(image_files)}] {img_filename}")
    print(f"  Size: {width} x {height} pixels")

    # ─── Calculate tile grid ─────────────────────────────────────
    # Same logic the real API would use
    tiles = []
    y = TILE_SIZE // 2  # center of first tile
    while y - TILE_SIZE // 2 < height:
        x = TILE_SIZE // 2
        while x - TILE_SIZE // 2 < width:
            tiles.append((x, y))
            x += TILE_STRIDE
        y += TILE_STRIDE

    print(f"  Tile grid: {len(tiles)} tiles")

    # ─── Pick random species for this image ──────────────────────
    image_species = random.sample(species_pool, min(NUM_SPECIES_PER_IMAGE, len(species_pool)))

    # ─── Assign predictions to tiles ─────────────────────────────
    image_predictions = []
    nb_matching = 0

    for center_x, center_y in tiles:
        # Does this tile have a match?
        if random.random() > MATCH_PROBABILITY:
            continue  # no match for this tile

        nb_matching += 1

        # Pick a random species and generate a confidence score
        sp = random.choice(image_species)

        # Generate a realistic score (beta distribution skewed toward lower values)
        score = round(random.betavariate(2, 5), 4)

        # Apply min_score filter
        if score < MIN_SCORE:
            continue

        # Pick a random organ detection
        organ = random.choice(["leaf", "bark", "flower", "fruit", "habit"])

        # Convert center to bounding box
        left = max(0, center_x - TILE_SIZE // 2)
        top = max(0, center_y - TILE_SIZE // 2)
        box_width = min(TILE_SIZE, width - left)
        box_height = min(TILE_SIZE, height - top)

        prediction = {
            "species_name": sp["scientific_name"],
            "gbif_id": str(sp["gbif_id"]),
            "confidence": score,
            "organ": organ,
            "bbox": {
                "left": left,
                "top": top,
                "width": box_width,
                "height": box_height,
            },
        }
        image_predictions.append(prediction)

    # Count unique species in predictions
    unique_species = set(p["species_name"] for p in image_predictions)

    all_predictions[img_filename] = {
        "image_width": width,
        "image_height": height,
        "nb_tiles": len(tiles),
        "nb_matching_tiles": nb_matching,
        "nb_species": len(unique_species),
        "predictions": image_predictions,
    }

    # ─── Print summary ───────────────────────────────────────────
    print(f"  Tiles with match: {nb_matching}")
    print(f"  Predictions (after min_score filter): {len(image_predictions)}")
    print(f"  Unique species: {len(unique_species)}")

    # Show per-species breakdown
    species_counts = {}
    species_max_scores = {}
    for p in image_predictions:
        name = p["species_name"]
        species_counts[name] = species_counts.get(name, 0) + 1
        species_max_scores[name] = max(species_max_scores.get(name, 0), p["confidence"])

    print(f"\n  {'Species':<35} {'Max Score':>9} {'Tiles':>6}")
    print(f"  {'-'*35} {'-'*9} {'-'*6}")
    for name in sorted(species_counts.keys()):
        print(f"  {name:<35} {species_max_scores[name]:>9.4f} {species_counts[name]:>6}")
    print()

# ─── Save predictions (same format as real API script) ───────────
predictions_path = os.path.join(OUTPUT_DIR, "plantnet_predictions.json")
with open(predictions_path, "w", encoding="utf-8") as f:
    json.dump(all_predictions, f, indent=2, ensure_ascii=False)

# ─── Final summary ──────────────────────────────────────────────
print(f"{'='*60}")
print(f"MOCK PREDICTIONS COMPLETE")
print(f"{'='*60}")
print(f"Output: {predictions_path}")
print(f"Images processed: {len(all_predictions)}")
print()
for img_name, data in all_predictions.items():
    n_boxes = len(data["predictions"])
    n_species = data["nb_species"]
    print(f"  {img_name}:")
    print(f"    Species: {n_species}, Bounding boxes: {n_boxes}, "
          f"Tiles: {data['nb_tiles']}")
print(f"{'='*60}")
print()
print("NOTE: These are MOCK predictions for testing the Labelbox pipeline.")
print("Once you have Pl@ntNet survey API access, run 04_plantnet_predict.py instead.")