"""
07_upload_embeddings.py
Generate Pl@ntNet image embeddings and upload them to Labelbox.

Uses the Pl@ntNet survey/tiles endpoint with show_embeddings=true.
Each image is tiled; the API returns a 768-dim embedding per tile.
Tile embeddings are mean-pooled and L2-normalized into one vector per image.

The Labelbox embedding type is named dynamically from the Pl@ntNet model
version string found in the API response (e.g. "PlantNet-v7.3-2026-03"),
enabling tracking across Pl@ntNet retraining cycles.

Inputs:
  - config.yaml
  - images/*.JPG
  - output/images/dataset_id.txt

Outputs:
  - output/embeddings/embeddings.json
  - output/embeddings/embeddings_summary.json
  - Embeddings uploaded to Labelbox
"""

import os
import sys
import json
import re
import time
import yaml
import glob
import math
import requests
import labelbox as lb
from dotenv import load_dotenv
from datetime import datetime

# ─── Paths ───────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

with open(os.path.join(PROJECT_ROOT, "config.yaml"), "r") as f:
    cfg = yaml.safe_load(f)

lb_cfg = cfg["labelbox"]
pn_cfg = cfg["plantnet"]
survey_cfg = pn_cfg["survey"]

IMAGES_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["images"])
DATASET_ID_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_images"])
EMBEDDINGS_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_embeddings"])
os.makedirs(EMBEDDINGS_DIR, exist_ok=True)

API_BASE = pn_cfg["api_base"]
PROJECT = pn_cfg["project"]
GLOBAL_KEY_PREFIX = lb_cfg["global_key_prefix"]
EMBEDDING_DIMS = lb_cfg["embedding_dims"]

PLANTNET_API_KEY = os.getenv("PLANTNET_API_KEY")
if not PLANTNET_API_KEY:
    sys.exit("ERROR: PLANTNET_API_KEY not found in .env")

# Survey tiling parameters (reuse from config)
TILE_SIZE = survey_cfg.get("tile_size", 518)
TILE_STRIDE = survey_cfg.get("tile_stride", 259)
MULTI_SCALE = survey_cfg.get("multi_scale", False)
MIN_SCORE = survey_cfg.get("min_score", 0.005)

MAX_RETRIES = 3

# ─── Find images ─────────────────────────────────────────────────
image_files = sorted(glob.glob(os.path.join(IMAGES_DIR, "*.JPG")))
if not image_files:
    image_files = sorted(glob.glob(os.path.join(IMAGES_DIR, "*.jpg")))
if not image_files:
    image_files = sorted(glob.glob(os.path.join(IMAGES_DIR, "*.jpeg")))
if not image_files:
    image_files = sorted(glob.glob(os.path.join(IMAGES_DIR, "*.png")))

if not image_files:
    sys.exit(f"ERROR: No images found in {IMAGES_DIR}")

print("=" * 60)
print("STEP 1: Fetching Pl@ntNet embeddings via survey/tiles API")
print("=" * 60)
print(f"  Images:      {len(image_files)}")
print(f"  Project:     {PROJECT}")
print(f"  tile_size:   {TILE_SIZE}, tile_stride: {TILE_STRIDE}, multi_scale: {MULTI_SCALE}")
print(f"  min_score:   {MIN_SCORE}")

# ─── Call API per image ──────────────────────────────────────────
embeddings_data = []
plantnet_version = None  # extracted from first successful response

for i, img_path in enumerate(image_files):
    filename = os.path.basename(img_path)
    print(f"\n  [{i+1}/{len(image_files)}] {filename}")

    form = {
        "tile_size": TILE_SIZE,
        "tile_stride": TILE_STRIDE,
        "multi_scale": str(MULTI_SCALE).lower(),
        "min_score": MIN_SCORE,
        "show_embeddings": "true",
        # Suppress species results — we only need embeddings here
        "show_species": "false",
        "show_genus": "false",
        "show_family": "false",
    }

    response = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(img_path, "rb") as f:
                files = [("image", (filename, f, "image/jpeg"))]
                response = requests.post(
                    f"{API_BASE}/v2/survey/tiles/{PROJECT}",
                    files=files,
                    data=form,
                    params={"api-key": PLANTNET_API_KEY},
                    timeout=300,
                )
            if response.status_code == 200:
                break
            elif response.status_code == 429:
                print("  Quota exceeded (429). Stopping.")
                sys.exit(1)
            else:
                print(f"  Attempt {attempt}: HTTP {response.status_code} - {response.text[:200]}")
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

    # Extract model version from first successful response
    if plantnet_version is None:
        plantnet_version = data.get("version", "unknown")
        print(f"  Pl@ntNet model version: {plantnet_version}")

    # Extract tile embeddings (inside data["results"]["embeddings"])
    tile_embeddings = data.get("results", {}).get("embeddings")
    if not tile_embeddings:
        print(f"  WARNING: no 'embeddings' field in results for {filename}. Skipping.")
        continue

    n_tiles = len(tile_embeddings)
    print(f"  Tiles with embeddings: {n_tiles}", end="", flush=True)

    # Mean pool across all tiles (each tile has key "embeddings" for the vector)
    dims = len(tile_embeddings[0]["embeddings"])
    mean_vec = [0.0] * dims
    for tile in tile_embeddings:
        for j, v in enumerate(tile["embeddings"]):
            mean_vec[j] += v
    mean_vec = [v / n_tiles for v in mean_vec]

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in mean_vec))
    if norm > 0:
        mean_vec = [v / norm for v in mean_vec]

    assert len(mean_vec) == EMBEDDING_DIMS, (
        f"Expected {EMBEDDING_DIMS} dims, got {len(mean_vec)}"
    )

    print(f"  -> {dims} dims, pooled & normalized OK")

    embeddings_data.append({
        "filename": filename,
        "global_key": f"{GLOBAL_KEY_PREFIX}{filename}",
        "embedding": mean_vec,
        "n_tiles": n_tiles,
        "plantnet_version": plantnet_version,
    })

    if i < len(image_files) - 1:
        time.sleep(2)  # be polite to the API

if not embeddings_data:
    sys.exit("ERROR: No embeddings generated. Check API key and image files.")

# ─── Build dynamic embedding name ────────────────────────────────
# version string example: "2025-01-17 (7.3)" -> extract "7.3"
version_short = "unknown"
if plantnet_version:
    match = re.search(r"\(([^)]+)\)", plantnet_version)
    version_short = match.group(1) if match else plantnet_version.split()[0]

run_month = datetime.now().strftime("%Y-%m")
EMBEDDING_NAME = f"PlantNet-v{version_short}-{run_month}"

# ─── Save embeddings locally ─────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2: Saving embeddings to disk")
print("=" * 60)

embeddings_path = os.path.join(EMBEDDINGS_DIR, "embeddings.json")
with open(embeddings_path, "w") as f:
    json.dump(embeddings_data, f)
print(f"  Saved {len(embeddings_data)} embeddings -> {embeddings_path}")

# ─── Connect to Labelbox ─────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3: Uploading embeddings to Labelbox")
print("=" * 60)

LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")
if not LABELBOX_API_KEY:
    sys.exit("ERROR: LABELBOX_API_KEY not found in .env")

client = lb.Client(api_key=LABELBOX_API_KEY)
print("  Connected to Labelbox")

# ─── Create or get embedding type ────────────────────────────────
print(f"\n  Embedding name: '{EMBEDDING_NAME}'")
embedding = None
try:
    embedding = client.get_embedding_by_name(EMBEDDING_NAME)
    print(f"  Found existing embedding type: {embedding.id} ({embedding.dims} dims)")
except Exception:
    print(f"  Not found. Creating new embedding type ({EMBEDDING_DIMS} dims)...")
    embedding = client.create_embedding(EMBEDDING_NAME, EMBEDDING_DIMS)
    print(f"  Created embedding type: {embedding.id}")

# ─── Load dataset ────────────────────────────────────────────────
with open(os.path.join(DATASET_ID_DIR, "dataset_id.txt")) as f:
    dataset_id = f.read().strip()

dataset = client.get_dataset(dataset_id)
print(f"  Dataset: {dataset.name}")

gk_to_dr_id = {}
for dr in dataset.data_rows():
    if dr.global_key:
        gk_to_dr_id[dr.global_key] = dr.uid
print(f"  Data rows with global keys: {len(gk_to_dr_id)}")

# ─── Build upsert payload ────────────────────────────────────────
payload = []
skipped = 0

for entry in embeddings_data:
    gk = entry["global_key"]
    if gk not in gk_to_dr_id:
        print(f"  WARNING: global_key '{gk}' not found in dataset, skipping")
        skipped += 1
        continue
    payload.append({
        "key": lb.UniqueId(gk_to_dr_id[gk]),
        "embeddings": [{
            "embedding_id": embedding.id,
            "vector": entry["embedding"],
        }],
    })

print(f"\n  Payload: {len(payload)} data row(s) to upsert ({skipped} skipped)")

if not payload:
    sys.exit("ERROR: No data rows matched. Check global_key_prefix in config.yaml.")

# ─── Upsert embeddings ───────────────────────────────────────────
print("  Uploading embeddings...")
task = dataset.upsert_data_rows(payload)
task.wait_till_done()

print(f"  Status: {task.status}")
if task.errors:
    print(f"  Errors: {task.errors[:5]}")
else:
    print("  No errors!")

# ─── Verify count ─────────────────────────────────────────────────
print("\n  Waiting 10 seconds for Labelbox to index embeddings...")
time.sleep(10)
count = embedding.get_imported_vector_count()
print(f"  Imported vector count for '{EMBEDDING_NAME}': {count}")

# ─── Summary ─────────────────────────────────────────────────────
summary = {
    "embedding_name": EMBEDDING_NAME,
    "embedding_id": embedding.id,
    "embedding_dims": EMBEDDING_DIMS,
    "model": "Pl@ntNet survey/tiles (show_embeddings=true, mean-pooled tiles)",
    "plantnet_version": plantnet_version,
    "plantnet_project": PROJECT,
    "pooling": "mean",
    "images_processed": len(embeddings_data),
    "embeddings_uploaded": len(payload),
    "skipped": skipped,
    "imported_vector_count": count,
    "timestamp": datetime.now().isoformat(),
}

summary_path = os.path.join(EMBEDDINGS_DIR, "embeddings_summary.json")
with open(summary_path, "w") as f:
    json.dump(summary, f, indent=2)

print(f"""
{'=' * 60}
PL@NTNET EMBEDDINGS UPLOADED
{'=' * 60}
Model:       Pl@ntNet survey/tiles ({plantnet_version})
Pooling:     mean across tiles (L2-normalized)
Images:      {len(embeddings_data)} processed
Uploaded:    {len(payload)} embeddings
Skipped:     {skipped}
LB count:    {count} vectors indexed
Embedding:   {EMBEDDING_NAME} ({embedding.id})
Saved to:    {embeddings_path}
Summary:     {summary_path}
{'=' * 60}

Next: Open Labelbox Catalog -> select an image -> click
      "Find similar" -> choose "{EMBEDDING_NAME}" embedding.
{'=' * 60}
""")
