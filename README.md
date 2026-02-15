# 🌿 Labelbox × Pl\@ntNet — Brazilian Amazon Trees

| Boxes | Classification | Masks |
|:---:|:---:|:---:|
| <img src="media/boxes.jpg" alt="Boxes" height="180"/> | <img src="media/class.jpg" alt="Classification" height="180"/> | <img src="media/masks.jpg" alt="Masks" height="180"/> |

Integrating [Pl\@ntNet](https://plantnet.org/) multi-species predictions with [Labelbox](https://labelbox.com/) for model-assisted labelling of ultra high-resolution drone close-up photos of tropical trees (Brazilian Amazon).

Three annotation workflows are demonstrated:

| Workflow | Annotation type | Active learning? | Script folder |
|------------------|------------------|------------------|------------------|
| **📦 Bounding boxes** | `BBOX` + nested Radio | ✅ Yes (confidence works) | `scripts/boxes/` |
| 🎯 **Classification** | Global Radio | ✅ Yes (confidence works) | `scripts/class/` |
| 🎭 **Segmentation masks** | `RASTER_SEGMENTATION` + nested Radio | ⚠️ Confidence stored but UI filter broken | `scripts/masks/` |

Pl\@ntNet micro-project used: [Trees of the Brazilian Amazon](https://identify.plantnet.org/xprize-final-trees/species) (\~2 464 taxa).

------------------------------------------------------------------------

## 💻 Prerequisites

-   **Python 3.10+** (tested with 3.13)
-   **Git** installed ([git-scm.com](https://git-scm.com/))
-   A **Pl\@ntNet API key** → [my.plantnet.org](https://my.plantnet.org/)
-   A **Labelbox API key** → [app.labelbox.com](https://app.labelbox.com/) → Settings → API Keys

------------------------------------------------------------------------

## ⚙️ Setup

### 1. Clone this repo

``` bash
git clone https://github.com/<YOUR_USERNAME>/labelbox_plantnet.git
cd labelbox_plantnet
```

### 2. Create a virtual environment

``` bash
python -m venv .venv
```

### 3. Activate the virtual environment

**Windows (Power Shell):**

``` powershell
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**

``` cmd
.venv\Scripts\activate.bat
```

**macOS / Linux:**

``` bash
source .venv/bin/activate
```

### 4. Install dependencies

``` bash
pip install -r requirements.txt
```

### 5. Set up your API keys

Copy the example file:

``` bash
copy .env.example .env
```

Then open `.env` in a text editor and paste your real keys:

``` bash
PLANTNET_API_KEY=your-plantnet-api-key-here
LABELBOX_API_KEY=your-labelbox-api-key-here
```

> ⚠️ **Never commit `.env`** — it is already in `.gitignore`.

### 6. Add your drone images

Place your `.JPG` drone photos in the `images/` folder:

``` bash
images/
DJI_20250405090025_0008_V_121zoom.JPG
DJI_20250405090425_0018_V_93zoom.JPG
```

------------------------------------------------------------------------

## 🏃 How to run — step by step

All commands assume you are in the project root (`labelbox_plantnet/`) with the virtual environment activated.

### 🌱 Step 1 — Fetch species list from Pl\@ntNet

Downloads the \~2 464 species (scientific names + GBIF IDs) from the "Trees of the Brazilian Amazon" micro-project.

``` bash
python scripts/<workflow>01_fetch_plantnet_species.py
```

**Output**: `output/<workflow>/species_raw.json`

### 📦 Bounding box workflow

#### Step 2 — Create the Labelbox ontology

Creates a `tree` bounding box tool with a nested `species` Radio classification (\~2 464 options).

``` bash
python scripts/boxes/02_create_ontology.py
```

**Output:** `output/boxes/ontology_id.txt`

#### Step 3 — Create the Labelbox project + upload images

Creates a dataset, uploads images, creates a project, and sends a batch.

``` bash
python scripts/boxes/03_create_project.py
```

**Output:** `output/boxes/project_id.txt`, `output/boxes/dataset_id.txt`

#### Step 4 — Generate mock Pl\@ntNet predictions

> ⚠️ Replace with actual predictions once you have Pl\@ntNet API access for multi-species predictions.

Simulates Pl\@ntNet multi-species predictions (518×518 non-overlapping tiles) for each image.

``` bash
python scripts/boxes/04_mock_predictions.py
```

**Output:** `output/boxes/plantnet_predictions.json`

#### Step 5 — Import predictions as MAL pre-labels

Imports bounding box predictions with nested species classifications into the Labelbox project as Model-Assisted Labeling (MAL) pre-labels.

> ⚠️ **Optional step:** Useful for pre-labelling, but no confidence scores imported so cannot be used for active learning workflows. See next step.

``` bash
python scripts/boxes/05_mal_import.py
```

#### Step 6 — Import predictions into a Model Run

Creates a Model + Model Run and uploads predictions with confidence scores for active learning.

``` bash
python scripts/boxes/06_model_run.py
```

------------------------------------------------------------------------

### 🎯 Classification workflow

#### Step 2 — Create the classification ontology

``` bash
python scripts/class/02_create_ontology.py
```

#### Step 3 — Create the project + upload images

``` bash
python scripts/class/03_create_project.py
```

#### Step 4 — Generate mock predictions

> ⚠️ Replace with actual predictions once you have Pl\@ntNet API access for multi-species predictions.

``` bash
python scripts/class/04_mock_predictions.py
```

#### Step 5 — Import predictions into a Model Run

``` bash
python scripts/class/05_model_run.py
```

------------------------------------------------------------------------

### 🎭 Segmentation mask workflow

#### Step 2 — Create the segmentation ontology

Creates a `Plant` raster segmentation tool with a nested `species` Radio classification.

``` bash
python scripts/masks/02_create_ontology.py
```

#### Step 3 — Create the project + upload images

``` bash
python scripts/masks/03_create_project.py
```

#### Step 4 — Generate mock predictions

> ⚠️ Replace with actual predictions once you have Pl\@ntNet API access for multi-species predictions.

``` bash
python scripts/masks/04_mock_predictions.py
```

#### Step 5 — Build composite mask images

Generates per-species binary masks and a composite mask image per photo.

``` bash
python scripts/masks/05_build_masks.py
```

**Output:** `output/masks/mask_images/<image_name>/composite.png` + per-species PNGs

#### Step 6 — Import masks into a Model Run

> ⚠️ **Warning!** Confidence scores do not get imported per segmentation mask, despite what the Labelbox documentation says.

``` bash
python scripts/masks/06_model_run.py
```

------------------------------------------------------------------------

## 🏗️ Project structure

```         
labelbox_plantnet/
├── .env.example          # Template for API keys
├── .env                  # Your actual API keys (git-ignored)
├── .gitignore
├── requirements.txt
├── README.md
├── images/               # Your drone photos
│   └── *.JPG
├── scripts/
│   ├── boxes/
│   │   ├── 01_fetch_plantnet_species.py
│   │   ├── 02_create_ontology.py
│   │   ├── 03_create_project.py
│   │   ├── 04_plantnet_predict.py
│   │   ├── 04b_mock_predictions.py
│   │   ├── 05_import_predictions.py
│   │   └── 06_model_run.py
│   ├── class/
│   │   ├── 01_fetch_plantnet_species.py
│   │   ├── 02_create_ontology.py
│   │   ├── 03_create_project.py
│   │   ├── 04_plantnet_predict.py
│   │   └── 05_model_run.py
│   └── masks/
│   │   ├── 01_fetch_plantnet_species.py
│       ├── 02_create_ontology.py
│       ├── 03_create_project.py
│       ├── 04b_mock_predictions.py
│       ├── 05_build_masks.py
│       ├── 06_model_run.py
│   │   └── 07_import_predictions.py
└── output/               # Generated files
    ├── boxes/
    ├── class/
    └── masks/
```

------------------------------------------------------------------------

## 🚫 Known limitations

-   **Confidence threshold slider does not filter segmentation masks** in the Labelbox Model Run gallery view. Confidence scores are stored correctly (visible in the Parsed view) but the UI slider has no effect on mask predictions. This works correctly for bounding boxes.

-   **Max 4 000 classes per ontology** — the 2 464 taxa from the Brazilian Amazon micro-project fits within this limit, but the full Pl\@ntNet global flora (82K species) would not.

-   The Labelbox docs show `confidence=0.5` inside `lb_types.Mask()`, but the `Mask` class has no `confidence` field. The correct placement is on `ObjectAnnotation(confidence=...)` **and** `ClassificationAnswer(confidence=...)`. Both parent and child nodes must have confidence or neither can. Despite this working for bounding boxes however, it does not work in Labelbox.

------------------------------------------------------------------------

## 🔗 Useful links

-   [Pl\@ntNet API — Survey (multi-species)](https://my.plantnet.org/doc/api/survey)

-   [Labelbox — Image editor & ontology](https://docs.labelbox.com/docs/image-editor#set-up-an-ontology)

-   [Labelbox — Upload image predictions](https://docs.labelbox.com/reference/upload-image-predictions)

-   [Labelbox — Active learning](https://docs.labelbox.com/docs/active-learning)

-   [Labelbox — Limits (4K classes)](https://docs.labelbox.com/docs/limits)