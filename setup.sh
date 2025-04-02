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

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "Please edit .env file with your actual credentials"
        echo "Press Enter to open the file for editing, or Ctrl+C to skip"
        read
        ${EDITOR:-nano} .env
    else
        echo "ERROR: .env.example file not found. Please create a .env file manually."
        exit 1
    fi
fi

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
