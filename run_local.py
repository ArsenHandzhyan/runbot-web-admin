#!/usr/bin/env python3
"""
RunBot Web Admin - Local Development Server
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.web.app import create_app

if __name__ == "__main__":
    app = create_app()
    port = 5001  # Use port 5001 for local development
    print(f"🚀 RunBot Web Admin Local Server")
    print(f"📊 Database: Render PostgreSQL")
    print(f"🌐 URL: http://127.0.0.1:{port}")
    print(f"🔑 Login: admin / admin123")
    app.run(host='0.0.0.0', port=port, debug=True)