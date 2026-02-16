"""
Step 3b: Multi-species survey identification using Pl@ntNet API.

This script:
1. Reads images from the images/ folder
2. Estimates cost via /v2/cost/survey endpoint
3. Sends each image to the Pl@ntNet survey/tiles endpoint
4. Saves raw API responses and a summary JSON to output/predictions/

Each image is tiled and analyzed for multiple species.
Results include per-tile bounding box positions and confidence scores.

API docs: https://my.plantnet.org/doc/api/survey
"""

import os
import sys
import json
import time
import yaml
import requests
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Load .env
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")

if not PLANTNET_API_KEY or PLANTNET_API_KEY == "your_plantnet_api_key_here":
    print("ERROR: Please add your Pl@ntNet API key to the .env file")
    sys.exit(1)

# ─── Load config ─────────────────────────────────────────────────
config_path = os.path.join(PROJECT_ROOT, "config.yaml")
if not os.path.exists(config_path):
    print(f"ERROR: config.yaml not found at {config_path}")
    sys.exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

IMAGES_DIR = os.path.join(PROJECT_ROOT, config["folders"]["images"])
OUTPUT_DIR = os.path.join(PROJECT_ROOT, config["folders"]["output_predictions"])

API_BASE = config["plantnet"]["api_base"]
PROJECT = config["plantnet"]["project"]

# Survey parameters
survey_cfg = config["plantnet"]["survey"]
TILE_SIZE = survey_cfg.get("tile_size", 518)
TILE_STRIDE = survey_cfg.get("tile_stride", 259)
MULTI_SCALE = survey_cfg.get("multi_scale", False)
MIN_SCORE = survey_cfg.get("min_score", 0.10)
MAX_RANK = survey_cfg.get("max_rank", 1)
SHOW_SPECIES = survey_cfg.get("show_species", True)
SHOW_GENUS = survey_cfg.get("show_genus", False)
SHOW_FAMILY = survey_cfg.get("show_family", False)

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─── Find images ────────────────────────────────────────────────
VALID_EXTENSIONS = ('.jpg', '.jpeg', '.png')
image_files = sorted([
    f for f in os.listdir(IMAGES_DIR)
    if f.lower().endswith(VALID_EXTENSIONS)
])

if not image_files:
    print(f"ERROR: No images found in {IMAGES_DIR}")
    sys.exit(1)

print(f"Found {len(image_files)} image(s) in {IMAGES_DIR}")
print(f"API project: {PROJECT}")
print(f"Parameters: tile_size={TILE_SIZE}, tile_stride={TILE_STRIDE}, "
      f"multi_scale={MULTI_SCALE}, min_score={MIN_SCORE}, max_rank={MAX_RANK}")

# ─── Process each image ─────────────────────────────────────────
all_predictions = []
MAX_RETRIES = 3

for i, img_filename in enumerate(image_files, 1):
    img_path = os.path.join(IMAGES_DIR, img_filename)
    print(f"\n[{i}/{len(image_files)}] {img_filename}")

    # Get image dimensions
    with Image.open(img_path) as img:
        width, height = img.size
    print(f"  Image size: {width}x{height}")

    # ─── Cost estimation ─────────────────────────────────────────
    # Cost endpoint only needs tiling params (not result-filtering params)
    cost_form = {
        "size": f"{width}x{height}",
        "tile_size": TILE_SIZE,
        "tile_stride": TILE_STRIDE,
        "multi_scale": str(MULTI_SCALE).lower(),
    }

    try:
        cost_resp = requests.post(
            f"{API_BASE}/v2/cost/survey/{PROJECT}",
            params={"api-key": PLANTNET_API_KEY},
            data=cost_form,
            timeout=30
        )
        if cost_resp.status_code == 200:
            cost_data = cost_resp.json()
            estimated_cost = cost_data.get("estimated_cost", "?")
            print(f"  Estimated cost: {estimated_cost} credits")
        else:
            print(f"  Cost estimation failed (HTTP {cost_resp.status_code})")
            try:
                print(f"    Response: {cost_resp.text[:300]}")
            except:
                pass
            estimated_cost = "?"
    except Exception as e:
        print(f"  Cost estimation error: {e}")
        estimated_cost = "?"

    # ─── Survey identification ───────────────────────────────────
    # All tiling and result params sent as form data alongside the image
    survey_form = {
        "tile_size": TILE_SIZE,
        "tile_stride": TILE_STRIDE,
        "multi_scale": str(MULTI_SCALE).lower(),
        "min_score": MIN_SCORE,
        "max_rank": MAX_RANK,
        "show_species": str(SHOW_SPECIES).lower(),
        "show_genus": str(SHOW_GENUS).lower(),
        "show_family": str(SHOW_FAMILY).lower(),
    }

    response = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(img_path, "rb") as f:
                files = [("image", (img_filename, f, "image/jpeg"))]
                response = requests.post(
                    f"{API_BASE}/v2/survey/tiles/{PROJECT}",
                    files=files,
                    data=survey_form,
                    params={"api-key": PLANTNET_API_KEY},
                    timeout=300
                )

            if response.status_code == 200:
                break
            elif response.status_code == 429:
                print(f"  Quota exceeded (429). Stopping.")
                sys.exit(1)
            else:
                print(f"  Attempt {attempt}: HTTP {response.status_code}")
                try:
                    print(f"    Response: {response.text[:300]}")
                except:
                    pass
                if attempt < MAX_RETRIES:
                    time.sleep(5 * attempt)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"  Attempt {attempt}: {type(e).__name__}")
            if attempt < MAX_RETRIES:
                time.sleep(5 * attempt)

    if response is None or response.status_code != 200:
        print(f"  FAILED after {MAX_RETRIES} attempts. Skipping.")
        continue

    data = response.json()

    # Save raw response
    raw_path = os.path.join(OUTPUT_DIR, f"multi_raw_{Path(img_filename).stem}.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Parse results
    results = data.get("results", {})
    species_list = results.get("species", [])
    nb_sub = results.get("nb_sub_queries", 0)
    nb_match = results.get("nb_matching_sub_queries", 0)
    uncovered = results.get("uncovered", 0)

    print(f"  Sub-queries (tiles): {nb_sub}, matching: {nb_match}")
    print(f"  Uncovered: {uncovered:.1%}")
    print(f"  Species found: {len(species_list)}")

    # Build prediction record
    prediction = {
        "image": img_filename,
        "width": width,
        "height": height,
        "estimated_cost": estimated_cost,
        "nb_sub_queries": nb_sub,
        "nb_matching_sub_queries": nb_match,
        "uncovered": uncovered,
        "species": []
    }

    for sp in species_list:
        species_record = {
            "scientific_name": sp.get("binomial", ""),
            "scientific_name_author": sp.get("name", ""),
            "family": sp.get("family", ""),
            "genus": sp.get("genus", ""),
            "gbif_id": sp.get("gbif_id", ""),
            "coverage": sp.get("coverage", 0),
            "max_score": sp.get("max_score", 0),
            "count": sp.get("count", 0),
            "tiles": []
        }

        for loc in sp.get("location", []):
            center = loc.get("center", {})
            tile_sz = loc.get("size", TILE_SIZE)
            cx, cy = center.get("x", 0), center.get("y", 0)

            # Convert center + size to bounding box (top, left, width, height)
            box_left = cx - tile_sz // 2
            box_top = cy - tile_sz // 2

            species_record["tiles"].append({
                "center_x": cx,
                "center_y": cy,
                "tile_size": tile_sz,
                "box_left": max(0, box_left),
                "box_top": max(0, box_top),
                "box_width": min(tile_sz, width - max(0, box_left)),
                "box_height": min(tile_sz, height - max(0, box_top)),
                "score": loc.get("score", 0),
                "organ": loc.get("organ", ""),
            })

        prediction["species"].append(species_record)

        if species_record["count"] > 0:
            print(f"    {species_record['scientific_name']}: "
                  f"coverage={species_record['coverage']:.3f}, "
                  f"max_score={species_record['max_score']:.3f}, "
                  f"tiles={species_record['count']}")

    all_predictions.append(prediction)

    # Be polite to the API (survey is heavier)
    if i < len(image_files):
        time.sleep(2)

# ─── Save summary ───────────────────────────────────────────────
summary_path = os.path.join(OUTPUT_DIR, "multi_predictions.json")
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(all_predictions, f, indent=2, ensure_ascii=False)

print(f"\n{'='*50}")
print(f"MULTI-SPECIES PREDICTIONS COMPLETE")
print(f"{'='*50}")
print(f"Images processed: {len(all_predictions)}/{len(image_files)}")
print(f"Results saved to: {summary_path}")
print(f"Raw responses in: {OUTPUT_DIR}/multi_raw_*.json")
print(f"{'='*50}")