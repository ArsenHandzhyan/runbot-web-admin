#!/bin/bash

# RunBot Web Admin - Start Script
# Script for easy launching of the standalone web application

set -e

echo "🚀 Starting RunBot Web Admin (Standalone)..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
fi

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from .env.web template..."
    cp .env.web .env
    echo "✅ Created .env file. Please edit it with your configuration."
    echo "Required variables:"
    echo "  - TELEGRAM_BOT_TOKEN"
    echo "  - ADMIN_USERNAME" 
    echo "  - ADMIN_PASSWORD"
    echo "  - WEB_SECRET_KEY"
    exit 1
fi

# Set default values if not provided
export PORT=${PORT:-5000}
export FLASK_DEBUG=${FLASK_DEBUG:-False}

echo "Starting web server on port $PORT..."
echo "Access the admin panel at: http://localhost:$PORT"
echo "Configuration file: .env"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the application (wrapper with Web prefix)
python WebApp.py
