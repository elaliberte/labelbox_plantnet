"""
Step 4 (class): Call Pl@ntNet single-species identification API for each image.

For each image in images/, calls:
  POST https://my-api.plantnet.org/v2/identify/xprize-final-trees

Saves top-5 predictions to output/class/plantnet_predictions.json
"""

import os
import sys
import json
import time
import traceback
import requests
from dotenv import load_dotenv

# --- Paths ---------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # up 2 levels
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "class")
IMAGES_DIR = os.path.join(PROJECT_ROOT, "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")

if not PLANTNET_API_KEY or PLANTNET_API_KEY == "your_plantnet_api_key_here":
    print("ERROR: Please add your Pl@ntNet API key to the .env file")
    sys.exit(1)

API_URL = "https://my-api.plantnet.org/v2/identify/xprize-final-trees"


def identify_image(image_path):
    """Call Pl@ntNet single-species identification for one image."""
    with open(image_path, "rb") as img_file:
        files = [
            ("images", (os.path.basename(image_path), img_file, "image/jpeg")),
        ]
        data = {
            "organs": ["auto"],
        }
        params = {
            "api-key": PLANTNET_API_KEY,
            "include-related-images": "false",
            "no-reject": "true",
            "nb-results": 5,
            "lang": "en",
        }

        response = requests.post(API_URL, files=files, data=data, params=params)

    if response.status_code == 200:
        return response.json()
    elif response.status_code == 429:
        print("  Rate limited! Waiting 60 seconds...")
        time.sleep(60)
        return identify_image(image_path)
    else:
        print(f"  ERROR {response.status_code}: {response.text}")
        return None


def parse_result(r):
    """Parse a single result entry from the API response."""
    species = r.get("species", {})
    return {
        "scientific_name": species.get("scientificNameWithoutAuthor", "unknown"),
        "gbif_id": r.get("gbif", {}).get("id", ""),
        "score": r.get("score", 0),
        "family": species.get("family", {}).get("scientificNameWithoutAuthor", ""),
        "genus": species.get("genus", {}).get("scientificNameWithoutAuthor", ""),
    }


def main():
    # --- Find images ------------------------------------------------------
    image_files = sorted([
        f for f in os.listdir(IMAGES_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])
    if not image_files:
        print(f"ERROR: No images found in {IMAGES_DIR}")
        sys.exit(1)

    print(f"Found {len(image_files)} images to identify\n")

    # --- Call API for each image ------------------------------------------
    all_predictions = {}

    for i, img_file in enumerate(image_files, 1):
        img_path = os.path.join(IMAGES_DIR, img_file)
        print(f"[{i}/{len(image_files)}] Identifying: {img_file}")

        result = identify_image(img_path)

        if result is None:
            print(f"  FAILED — skipping\n")
            continue

        # Parse all results
        raw_results = result.get("results", [])
        predictions = [parse_result(r) for r in raw_results]

        # Print summary
        print(f"  Top {len(predictions)} predictions:")
        for p in predictions:
            print(f"    {p['score']:.4f}  {p['scientific_name']} ({p['family']})  [GBIF: {p['gbif_id']}]")

        all_predictions[img_file] = {
            "predictions": predictions,
            "remaining_requests": result.get("remainingIdentificationRequests", "?"),
        }
        print()

        # Small delay to be polite to the API
        if i < len(image_files):
            time.sleep(1)

    # --- Save predictions -------------------------------------------------
    output_path = os.path.join(OUTPUT_DIR, "plantnet_predictions.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_predictions, f, indent=2, ensure_ascii=False)

    print(f"{'='*60}")
    print(f"PREDICTIONS SAVED")
    print(f"{'='*60}")
    print(f"  File: {output_path}")
    print(f"  Images processed: {len(all_predictions)}")
    remaining = list(all_predictions.values())[-1].get("remaining_requests", "?") if all_predictions else "?"
    print(f"  Remaining API requests: {remaining}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n!!! UNCAUGHT ERROR !!!")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {e}")
        traceback.print_exc()