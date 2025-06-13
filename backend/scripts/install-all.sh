#!/bin/bash

echo "Installing system packages..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg imagemagick libsm6 libxext6 libmagic1 python-is-python3

echo "Creating virtual environment in ../ (backend root)..."
cd ..  # Moves from scripts/ to backend/
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing Python packages from scripts/requirements.txt..."
pip install --upgrade pip
pip install -r scripts/requirements.txt

echo "Setup complete!"
