"""
Step 3a: Single-species identification using Pl@ntNet API.

This script:
1. Reads images from the images/ folder
2. Sends each image to the Pl@ntNet single-species identification endpoint
3. Saves raw API responses and a summary JSON to output/predictions/

Each image is treated as a separate plant individual.
The top-N results (with confidence scores) are returned per image.

API docs: https://my.plantnet.org/doc/api/identify
"""

import os
import sys
import json
import time
import yaml
import requests
from pathlib import Path
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

# Single-species parameters
single_cfg = config["plantnet"]["single"]
ORGANS = single_cfg.get("organs", "auto")
NB_RESULTS = single_cfg.get("nb_results", 5)
NO_REJECT = single_cfg.get("no_reject", True)
INCLUDE_RELATED = single_cfg.get("include_related_images", False)
LANG = single_cfg.get("lang", "en")

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
print(f"Parameters: organs={ORGANS}, nb-results={NB_RESULTS}, "
      f"no-reject={NO_REJECT}, lang={LANG}")

# ─── Process each image ─────────────────────────────────────────
all_predictions = []
MAX_RETRIES = 3

for i, img_filename in enumerate(image_files, 1):
    img_path = os.path.join(IMAGES_DIR, img_filename)
    print(f"\n[{i}/{len(image_files)}] {img_filename}")

    # Retry logic
    response = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(img_path, "rb") as f:
                # images and organs are multipart form data
                files = [("images", (img_filename, f, "image/jpeg"))]
                form_data = {"organs": ORGANS}

                # everything else is query parameters
                params = {
                    "api-key": PLANTNET_API_KEY,
                    "nb-results": NB_RESULTS,
                    "no-reject": str(NO_REJECT).lower(),
                    "include-related-images": str(INCLUDE_RELATED).lower(),
                    "lang": LANG,
                }

                response = requests.post(
                    f"{API_BASE}/v2/identify/{PROJECT}",
                    files=files,
                    data=form_data,
                    params=params,
                    timeout=120
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
    raw_path = os.path.join(OUTPUT_DIR, f"single_raw_{Path(img_filename).stem}.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Parse results
    best_match = data.get("bestMatch", "Unknown")
    results = data.get("results", [])
    remaining = data.get("remainingIdentificationRequests", "?")

    print(f"  Best match: {best_match}")
    print(f"  Results: {len(results)} species returned")
    print(f"  Remaining quota: {remaining}")

    # Print top results
    for j, r in enumerate(results[:3], 1):
        sp = r.get("species", {})
        name = sp.get("scientificNameWithoutAuthor", "?")
        score = r.get("score", 0)
        print(f"    #{j} {name} (score: {score:.4f})")

    # Build prediction record
    prediction = {
        "image": img_filename,
        "best_match": best_match,
        "results": []
    }

    for r in results:
        sp = r.get("species", {})
        prediction["results"].append({
            "score": r.get("score", 0),
            "scientific_name": sp.get("scientificNameWithoutAuthor", ""),
            "scientific_name_author": sp.get("scientificName", ""),
            "family": sp.get("family", {}).get("scientificNameWithoutAuthor", ""),
            "genus": sp.get("genus", {}).get("scientificNameWithoutAuthor", ""),
            "gbif_id": r.get("gbif", {}).get("id", ""),
            "powo_id": r.get("powo", {}).get("id", ""),
        })

    all_predictions.append(prediction)

    # Be polite to the API
    if i < len(image_files):
        time.sleep(1)

# ─── Save summary ───────────────────────────────────────────────
summary_path = os.path.join(OUTPUT_DIR, "single_predictions.json")
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(all_predictions, f, indent=2, ensure_ascii=False)

print(f"\n{'='*50}")
print(f"SINGLE-SPECIES PREDICTIONS COMPLETE")
print(f"{'='*50}")
print(f"Images processed: {len(all_predictions)}/{len(image_files)}")
print(f"Results saved to: {summary_path}")
print(f"Raw responses in: {OUTPUT_DIR}/single_raw_*.json")
print(f"{'='*50}")