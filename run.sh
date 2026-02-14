#!/bin/bash
# Simple run script for IRC Ebook Fetcher

# Change to script directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update requirements
echo "Installing requirements..."
pip install -q -r requirements.txt

# Run the application
echo "Starting IRC Ebook Fetcher..."
python main.py
