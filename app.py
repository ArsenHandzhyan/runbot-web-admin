"""
RunBot Web Admin - Standalone Web Application
Separate web interface that can run independently from the Telegram bot
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add current directory to Python path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Import the Flask app
from src.web.app import create_app

# Create the application instance
application = create_app()

if __name__ == "__main__":
    # This block runs when executing directly
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    application.run(host='0.0.0.0', port=port, debug=debug)