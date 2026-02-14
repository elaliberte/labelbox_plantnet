# Labelbox × Pl@ntNet Integration

Integrating Pl@ntNet multi-species predictions (survey/plot API) as model 
predictions in Labelbox for model-assisted labeling of ultra high-resolution 
drone photos of tropical trees from the Brazilian Amazon.

## Setup
1. Clone this repo
2. Create a virtual environment: `python -m venv .venv`
3. Activate it: `.venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and add your API keys

## Flora used
- **Pl@ntNet microproject:** Trees of the Brazilian Amazon (`xprize-final-trees`)
- ~2,464 tree species