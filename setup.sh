#!/bin/bash

# Exit on any error
set -e

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Create logs directory if it doesn't exist
mkdir -p logs

# Setup systemd service
if [ -f "gas.service" ]; then
    echo "Setting up systemd service..."
    sudo cp gas.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable gas
    sudo systemctl restart gas
    echo "Service installed and started"
fi

# Print status
echo "Setup complete! Check service status with: sudo systemctl status gas"
