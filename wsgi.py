"""
WSGI application for BotHost deployment
This file is specifically designed for BotHost hosting platform
"""

import os
import sys
from pathlib import Path

# Add the current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Import the Flask app
from src.web.app import create_app

# Create the application instance
application = create_app()

if __name__ == "__main__":
    # This block runs when executing directly (for local testing)
    port = int(os.environ.get('PORT', 5000))
    application.run(host='0.0.0.0', port=port, debug=False)