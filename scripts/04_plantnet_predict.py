"""
Step 4: Send images to the Pl@ntNet survey API for multi-species identification.

This script:
1. Reads images from the images/ folder
2. Estimates the API cost per image (credits)
3. Sends each image to the Pl@ntNet survey (tiles) API
4. Parses the multi-species predictions (species, scores, tile locations)
5. Converts tile locations to bounding boxes
6. Saves predictions as JSON for import into Labelbox

API docs: https://my.plantnet.org/doc/api/survey

Settings:
- tile_size=518 (minimum allowed by API)
- tile_stride=518 (no overlap — clean grid)
- min_score=0.10 (filter low-confidence noise)
- max_rank=1 (only top-1 species per tile)
"""

import os
import sys
import json
import requests
from PIL import Image
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")

if not PLANTNET_API_KEY or PLANTNET_API_KEY == "your_plantnet_api_key_here":
    print("ERROR: Please add your Pl@ntNet API key to the .env file")
    sys.exit(1)

# ─── Configuration ───────────────────────────────────────────────
PROJECT = "xprize-final-trees"
API_BASE = "https://my-api.plantnet.org"
SURVEY_URL = f"{API_BASE}/v2/survey/tiles/{PROJECT}"
COST_URL = f"{API_BASE}/v2/cost/survey/{PROJECT}"

# Survey parameters — tuned for 4000x3000 drone images
TILE_SIZE = 518       # minimum tile size (model input size)
TILE_STRIDE = 518     # no overlap — clean non-overlapping grid
MIN_SCORE = 0.10      # filter out low-confidence noise
MAX_RANK = 1          # only the best species guess per tile

# ─── Find images ────────────────────────────────────────────────
VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png')
image_files = sorted([
    f for f in os.listdir(IMAGES_DIR)
    if f.lower().endswith(VALID_EXTENSIONS)
])

if not image_files:
    print(f"ERROR: No images found in {IMAGES_DIR}")
    sys.exit(1)

print(f"Found {len(image_files)} image(s) to process")
print(f"Settings: tile_size={TILE_SIZE}, tile_stride={TILE_STRIDE}, "
      f"min_score={MIN_SCORE}, max_rank={MAX_RANK}")
print()

# ─── Process each image ─────────────────────────────────────────
all_predictions = {}

for i, img_filename in enumerate(image_files, 1):
    img_path = os.path.join(IMAGES_DIR, img_filename)
    file_size_mb = os.path.getsize(img_path) / (1024 * 1024)

    # Get image dimensions
    with Image.open(img_path) as img:
        width, height = img.size

    print(f"{'='*60}")
    print(f"[{i}/{len(image_files)}] {img_filename}")
    print(f"  Size: {width} x {height} pixels ({file_size_mb:.1f} MB)")
    print(f"{'='*60}")

    # ─── Step A: Estimate cost ───────────────────────────────────
    cost_params = {"api-key": PLANTNET_API_KEY}
    cost_data = {
        "size": f"{width}x{height}",
        "tile_size": TILE_SIZE,
        "tile_stride": TILE_STRIDE,
    }

    cost_response = requests.post(COST_URL, params=cost_params, data=cost_data)

    if cost_response.status_code == 200:
        cost_info = cost_response.json()
        estimated_cost = cost_info.get("estimated_cost", "unknown")
        print(f"  Estimated cost: {estimated_cost} credits")
    else:
        print(f"  WARNING: Could not estimate cost (status {cost_response.status_code})")
        print(f"  {cost_response.text[:200]}")
        estimated_cost = "unknown"

    # ─── Step B: Send image to survey API ────────────────────────
    print(f"  Sending to Pl@ntNet survey API...")

    survey_params = {"api-key": PLANTNET_API_KEY}

    with open(img_path, "rb") as img_file:
        files = {
            "image": (img_filename, img_file, "image/jpeg")
        }
        data = {
            "tile_size": TILE_SIZE,
            "tile_stride": TILE_STRIDE,
            "min_score": MIN_SCORE,
            "max_rank": MAX_RANK,
            "show_species": "true",
        }

        response = requests.post(
            SURVEY_URL,
            params=survey_params,
            files=files,
            data=data
        )

    if response.status_code != 200:
        print(f"  ERROR: API returned status {response.status_code}")
        print(f"  {response.text[:500]}")
        continue

    result = response.json()

    # Save raw response per image (for debugging)
    raw_per_image_path = os.path.join(OUTPUT_DIR, f"raw_{img_filename}.json")
    with open(raw_per_image_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # ─── Step C: Parse the results ───────────────────────────────
    results_section = result.get("results", {})
    nb_tiles = results_section.get("nb_sub_queries", 0)
    nb_matching = results_section.get("nb_matching_sub_queries", 0)
    species_results = results_section.get("species", [])

    print(f"  Tiles processed:  {nb_tiles}")
    print(f"  Tiles with match: {nb_matching}")
    print(f"  Species found:    {len(species_results)}")

    # ─── Step D: Convert tile locations to bounding boxes ────────
    image_predictions = []

    for sp in species_results:
        species_name = sp.get("binomial", sp.get("name", "unknown"))
        gbif_id = str(sp.get("gbif_id", ""))
        coverage = sp.get("coverage", 0)
        max_score = sp.get("max_score", 0)

        locations = sp.get("location", [])

        for loc in locations:
            center_x = loc["center"]["x"]
            center_y = loc["center"]["y"]
            tile_size = loc["size"]
            score = loc["score"]
            organ = loc.get("organ", "unknown")

            # Convert center + size to bounding box (top-left + dimensions)
            left = center_x - tile_size // 2
            top = center_y - tile_size // 2

            # Clamp to image boundaries
            left = max(0, left)
            top = max(0, top)
            box_width = min(tile_size, width - left)
            box_height = min(tile_size, height - top)

            prediction = {
                "species_name": species_name,
                "gbif_id": gbif_id,
                "confidence": round(score, 4),
                "organ": organ,
                "bbox": {
                    "left": left,
                    "top": top,
                    "width": box_width,
                    "height": box_height,
                },
            }
            image_predictions.append(prediction)

    all_predictions[img_filename] = {
        "image_width": width,
        "image_height": height,
        "nb_tiles": nb_tiles,
        "nb_matching_tiles": nb_matching,
        "nb_species": len(species_results),
        "predictions": image_predictions,
    }

    # ─── Print summary for this image ────────────────────────────
    print(f"\n  Results:")
    print(f"  {'Species':<35} {'Score':>7} {'Tiles':>6}")
    print(f"  {'-'*35} {'-'*7} {'-'*6}")
    for sp in species_results:
        name = sp.get("binomial", sp.get("name", "?"))
        print(f"  {name:<35} {sp.get('max_score', 0):>7.3f} {sp.get('count', 0):>6}")

    print(f"\n  Total bounding boxes: {len(image_predictions)}")
    print()

# ─── Save all predictions ───────────────────────────────────────
predictions_path = os.path.join(OUTPUT_DIR, "plantnet_predictions.json")
with open(predictions_path, "w", encoding="utf-8") as f:
    json.dump(all_predictions, f, indent=2, ensure_ascii=False)

# ─── Final summary ──────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"ALL PREDICTIONS COMPLETE")
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