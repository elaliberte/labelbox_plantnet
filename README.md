# Labelbox × Pl@ntNet Integration

Integrating Pl@ntNet multi-species predictions (survey/plot API) as model 
predictions in Labelbox for model-assisted labeling of ultra high-resolution 
drone photos of tropical trees. This demo uses photos from the Brazilian Amazon.

Two types of predictions are demonstrated:

1. **Single-species predictions:** The most likely species is predicted for each tree in the image, and predictions are imported as single-label classification.
2. **Multi-species predictions:** The most likely species are predicted for each tree in the image, and predictions are imported as bounding boxes, each with single-label classification.

## Setup
1. Clone this repo
2. Create a virtual environment: `python -m venv .venv`
3. Activate it: `.venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and add your API keys

## Flora used
- **Pl@ntNet microproject:** Trees of the Brazilian Amazon (`xprize-final-trees`)
- ~2,464 tree species