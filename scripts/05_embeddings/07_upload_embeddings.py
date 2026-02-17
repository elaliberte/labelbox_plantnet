"""
05_upload_embeddings.py
Generate BioCLIP2 image embeddings and upload them to Labelbox.

BioCLIP2 is a foundation model for biological images (ViT-L/14, 304M params).
It produces 768-dimensional embeddings that capture biological similarity,
enabling powerful similarity search in Labelbox Catalog.

Requirements:
  pip install open_clip_torch timm

Inputs:
  - config.yaml
  - images/*.JPG
  - output/images/dataset_id.txt

Outputs:
  - output/embeddings/embeddings.json
  - Embeddings uploaded to Labelbox
"""

import os
import sys
import json
import yaml
import glob
import torch
import numpy as np
from PIL import Image
import open_clip
import labelbox as lb
from dotenv import load_dotenv
from datetime import datetime

# ─── Paths ───────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

with open(os.path.join(PROJECT_ROOT, "config.yaml"), "r") as f:
    cfg = yaml.safe_load(f)

lb_cfg = cfg["labelbox"]
IMAGES_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["images"])
DATASET_ID_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_images"])
EMBEDDINGS_DIR = os.path.join(PROJECT_ROOT, cfg["folders"]["output_embeddings"])
os.makedirs(EMBEDDINGS_DIR, exist_ok=True)

GLOBAL_KEY_PREFIX = lb_cfg["global_key_prefix"]
EMBEDDING_NAME = lb_cfg["embedding_name"]
EMBEDDING_DIMS = lb_cfg["embedding_dims"]

# ─── Load BioCLIP2 model ─────────────────────────────────────────
print("=" * 60)
print("STEP 1: Loading BioCLIP2 model (ViT-L/14, 304M params)")
print("=" * 60)

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"  Device: {device}")
if device == "cpu":
    print("  NOTE: Running on CPU. This is fine for a small number of images.")
    print("        For hundreds of images, a GPU would be faster.")

model, _, preprocess = open_clip.create_model_and_transforms(
    "hf-hub:imageomics/bioclip-2"
)
model = model.to(device)
model.eval()
print("  BioCLIP2 model loaded successfully.")

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

print(f"\n  Found {len(image_files)} image(s) in {IMAGES_DIR}")

# ─── Generate embeddings ─────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2: Generating BioCLIP2 embeddings")
print("=" * 60)

embeddings_data = []

for i, img_path in enumerate(image_files):
    filename = os.path.basename(img_path)
    print(f"  [{i+1}/{len(image_files)}] {filename}", end="", flush=True)

    image = Image.open(img_path).convert("RGB")
    image_tensor = preprocess(image).unsqueeze(0).to(device)

    with torch.no_grad():
        image_features = model.encode_image(image_tensor)
        # Normalize to unit length (standard for CLIP embeddings)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

    embedding_vector = image_features.cpu().numpy().flatten().tolist()
    print(f"  → {len(embedding_vector)} dims ✓")

    assert len(embedding_vector) == EMBEDDING_DIMS, (
        f"Expected {EMBEDDING_DIMS} dims, got {len(embedding_vector)}"
    )

    embeddings_data.append({
        "filename": filename,
        "global_key": f"{GLOBAL_KEY_PREFIX}{filename}",
        "embedding": embedding_vector,
    })

# ─── Save embeddings locally ─────────────────────────────────────
embeddings_path = os.path.join(EMBEDDINGS_DIR, "embeddings.json")
with open(embeddings_path, "w") as f:
    json.dump(embeddings_data, f)
print(f"\n  Saved {len(embeddings_data)} embeddings to {embeddings_path}")

# ─── Connect to Labelbox ─────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3: Uploading embeddings to Labelbox")
print("=" * 60)

API_KEY = os.getenv("LABELBOX_API_KEY")
if not API_KEY:
    sys.exit("ERROR: LABELBOX_API_KEY not found in .env")

client = lb.Client(api_key=API_KEY)
print("  Connected to Labelbox")

# ─── Create or get embedding type ────────────────────────────────
print(f"\n  Looking for embedding type: '{EMBEDDING_NAME}'")
embedding = None
try:
    embedding = client.get_embedding_by_name(EMBEDDING_NAME)
    print(f"  Found existing embedding type: {embedding.id} ({embedding.dims} dims)")
except Exception:
    print(f"  Not found. Creating new embedding type: '{EMBEDDING_NAME}' ({EMBEDDING_DIMS} dims)")
    embedding = client.create_embedding(EMBEDDING_NAME, EMBEDDING_DIMS)
    print(f"  Created embedding type: {embedding.id}")

# ─── Load dataset ────────────────────────────────────────────────
with open(os.path.join(DATASET_ID_DIR, "dataset_id.txt")) as f:
    dataset_id = f.read().strip()

dataset = client.get_dataset(dataset_id)
print(f"  Dataset: {dataset.name}")

# Build global_key → data_row_id mapping
gk_to_dr_id = {}
for dr in dataset.data_rows():
    if dr.global_key:
        gk_to_dr_id[dr.global_key] = dr.uid

print(f"  Found {len(gk_to_dr_id)} data row(s) with global keys")

# ─── Build upsert payload ────────────────────────────────────────
payload = []
skipped = 0

for entry in embeddings_data:
    gk = entry["global_key"]
    if gk not in gk_to_dr_id:
        print(f"  WARNING: global_key '{gk}' not found in dataset, skipping")
        skipped += 1
        continue

    dr_id = gk_to_dr_id[gk]
    payload.append({
        "key": lb.UniqueId(dr_id),
        "embeddings": [{
            "embedding_id": embedding.id,
            "vector": entry["embedding"],
        }],
    })

print(f"\n  Payload: {len(payload)} data row(s) to upsert ({skipped} skipped)")

if not payload:
    sys.exit("ERROR: No data rows matched. Check global_key_prefix in config.yaml.")

# ─── Upsert embeddings ───────────────────────────────────────────
print(f"  Uploading embeddings via dataset.upsert_data_rows()...")
task = dataset.upsert_data_rows(payload)
task.wait_till_done()

print(f"  Status: {task.status}")
if task.errors:
    print(f"  Errors: {task.errors[:5]}")
else:
    print(f"  No errors!")

# ─── Verify count ─────────────────────────────────────────────────
import time
print(f"\n  Waiting 10 seconds for Labelbox to index embeddings...")
time.sleep(10)
count = embedding.get_imported_vector_count()
print(f"  Imported vector count for '{EMBEDDING_NAME}': {count}")

# ─── Summary ─────────────────────────────────────────────────────
summary = {
    "embedding_name": EMBEDDING_NAME,
    "embedding_id": embedding.id,
    "embedding_dims": EMBEDDING_DIMS,
    "model": "BioCLIP2 (ViT-L/14, imageomics/bioclip-2)",
    "device": device,
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
BIOCLIP2 EMBEDDINGS UPLOADED
{'=' * 60}
Model:       BioCLIP2 (ViT-L/14, 304M params, 768 dims)
Device:      {device}
Images:      {len(embeddings_data)} processed
Uploaded:    {len(payload)} embeddings
Skipped:     {skipped}
LB count:    {count} vectors indexed
Embedding:   {EMBEDDING_NAME} ({embedding.id})
Saved to:    {embeddings_path}
Summary:     {summary_path}
{'=' * 60}

NOTE: Similarity search in Labelbox Catalog works best with
      at least 1,000 data rows. With {len(payload)} image(s), you can
      still view embeddings but similarity search may be limited.

Next: Open Labelbox Catalog → select an image → click
      "Find similar" → choose "{EMBEDDING_NAME}" embedding.
{'=' * 60}
""")