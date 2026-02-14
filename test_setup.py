"""Quick test to verify the environment is set up correctly."""

import os
from dotenv import load_dotenv

# Load API keys from .env file
load_dotenv()

plantnet_key = os.getenv("PLANTNET_API_KEY")
labelbox_key = os.getenv("LABELBOX_API_KEY")

# Check Pl@ntNet key
if plantnet_key and plantnet_key != "your_plantnet_api_key_here":
    print("✓ Pl@ntNet API key loaded successfully")
else:
    print("✗ Pl@ntNet API key NOT found - check your .env file")

# Check Labelbox key
if labelbox_key and labelbox_key != "your_labelbox_api_key_here":
    print("✓ Labelbox API key loaded successfully")
else:
    print("✗ Labelbox API key NOT found - check your .env file")

# Test imports
try:
    import labelbox as lb
    print(f"✓ Labelbox SDK imported (version: {lb.__version__})")
except ImportError:
    print("✗ Labelbox SDK not installed - run: pip install labelbox")

try:
    import requests
    print(f"✓ Requests library imported (version: {requests.__version__})")
except ImportError:
    print("✗ Requests not installed - run: pip install requests")

try:
    from PIL import Image
    print("✓ Pillow (PIL) imported successfully")
except ImportError:
    print("✗ Pillow not installed - run: pip install Pillow")

print("\nSetup test complete!")