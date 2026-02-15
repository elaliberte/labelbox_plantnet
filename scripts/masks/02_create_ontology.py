"""
Step 2 (masks): Create Labelbox ontology for segmentation masks.

Creates a RASTER_SEGMENTATION tool called 'Plant' with a nested
Radio classification 'species' containing ~2,464 options.
Each option: label = scientific name, value = GBIF taxon ID.

Reads species from output/masks/species_raw.json (from step 01).
Saves ontology ID to output/masks/ontology_id.txt.
"""

import os
import sys
import json
import labelbox as lb
from dotenv import load_dotenv

# ─── Paths ───────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output", "masks")
os.makedirs(OUTPUT_DIR, exist_ok=True)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
LABELBOX_API_KEY = os.getenv("LABELBOX_API_KEY")

if not LABELBOX_API_KEY or LABELBOX_API_KEY == "your_labelbox_api_key_here":
    print("ERROR: Please add your Labelbox API key to the .env file")
    sys.exit(1)


def main():
    # ─── Load species list ───────────────────────────────────────
    species_path = os.path.join(OUTPUT_DIR, "species_raw.json")
    if not os.path.exists(species_path):
        print(f"ERROR: {species_path} not found. Run 01_fetch_plantnet_species.py first.")
        sys.exit(1)

    with open(species_path, "r", encoding="utf-8") as f:
        species_list = json.load(f)

    print(f"Loaded {len(species_list)} species from species_raw.json")

    # ─── Build species options ───────────────────────────────────
    species_options = []
    skipped = 0
    seen_gbif_ids = set()

    for sp in species_list:
        name = sp.get("scientificNameWithoutAuthor", "")
        gbif_id = str(sp.get("gbifId", ""))

        if not name or not gbif_id or gbif_id == "":
            skipped += 1
            continue

        # Avoid duplicate GBIF IDs (Labelbox requires unique values)
        if gbif_id in seen_gbif_ids:
            skipped += 1
            continue
        seen_gbif_ids.add(gbif_id)

        species_options.append(lb.Option(value=gbif_id, label=name))

    print(f"  Valid species options: {len(species_options)}")
    if skipped:
        print(f"  Skipped (missing data or duplicates): {skipped}")

    if len(species_options) > 4000:
        print(f"  WARNING: {len(species_options)} options exceeds Labelbox limit of 4,000!")
        print(f"  Truncating to 4,000 options.")
        species_options = species_options[:4000]

    # ─── Build ontology ──────────────────────────────────────────
    print("\nConnecting to Labelbox...")
    client = lb.Client(api_key=LABELBOX_API_KEY)

    ontology_builder = lb.OntologyBuilder(
        tools=[
            lb.Tool(
                tool=lb.Tool.Type.RASTER_SEGMENTATION,
                name="Plant",
                classifications=[
                    lb.Classification(
                        class_type=lb.Classification.Type.RADIO,
                        name="species",
                        options=species_options,
                    )
                ],
            )
        ]
    )

    print("Creating ontology...")
    ontology = client.create_ontology(
        "Brazilian Amazon Trees - Segmentation (xprize-final-trees)",
        ontology_builder.asdict(),
        media_type=lb.MediaType.Image,
    )

    print(f"\nOntology created!")
    print(f"  Name: {ontology.name}")
    print(f"  ID:   {ontology.uid}")

    # ─── Save ontology ID ────────────────────────────────────────
    with open(os.path.join(OUTPUT_DIR, "ontology_id.txt"), "w") as f:
        f.write(ontology.uid)
    print(f"  Saved ontology ID to output/masks/ontology_id.txt")

    # ─── Summary ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"ONTOLOGY SUMMARY")
    print(f"{'='*60}")
    print(f"  Tool:           Plant (RASTER_SEGMENTATION)")
    print(f"  Classification: species (Radio, {len(species_options)} options)")
    print(f"  Ontology ID:    {ontology.uid}")


if __name__ == "__main__":
    main()