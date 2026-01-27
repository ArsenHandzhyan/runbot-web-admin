#!/usr/bin/env python3
"""
RunBot Web Admin - Local Development Server
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.web.app import create_app

if __name__ == "__main__":
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    app = create_app()
    port = int(os.getenv("PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    logging.info("RunBot Web Admin Local Server")
    logging.info("URL: http://127.0.0.1:%s", port)
    logging.info("Login: configure ADMIN_USERNAME/ADMIN_PASSWORD in env")

    app.run(host="0.0.0.0", port=port, debug=debug)
