#!/usr/bin/env python3
"""RunBot Web Admin - Web entry point (wrapper)"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

try:
    # Prefer the newer WebApp module if it exists; fall back to legacy path for compatibility
    from src.web.WebApp import create_app  # type: ignore
except Exception:
    from src.web.app import create_app  # type: ignore

if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
