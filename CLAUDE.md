# CLAUDE.md

## Project Overview
Labelbox x Pl@ntNet pipeline for annotating Brazilian Amazon drone tree images.
Three annotation workflows (classification, bounding boxes, segmentation masks)
plus embeddings for similarity search.

## Tech Stack
- Python 3.10+, virtual environment in `.venv/`
- Pl@ntNet API (species identification)
- Labelbox SDK (annotation platform)
- Config in `config.yaml`, secrets in `.env`

## Project Structure
- `scripts/` — Pipeline scripts numbered by step (01-07)
- `output/` — Generated files (IDs, predictions, masks, embeddings)
- `images/` — Input drone photos
- `config.yaml` — Central configuration
- `.env` — API keys (never commit)

## Running Scripts
Scripts are run individually in order from the project root:
  python scripts/01_species/01_fetch_species.py
  python scripts/02_images/02_upload_images.py
  etc.

## Key Conventions
- All config values in config.yaml, no hardcoded values in scripts
- Inter-script communication via files in output/ (IDs, JSON)
- Global keys link images across Labelbox dataset, predictions, and embeddings
