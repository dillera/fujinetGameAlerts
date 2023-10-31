#!/bin/bash
#
# create flask startup scripts for FujiNet and other flask apps.
# a typical path: /home/ubuntu/fujinetGameAlerts
# with a venv at: /home/ubuntu/fujinetGameAlerts/venv
#
# adiller oct 2023
#
#################################################################
# Function to display usage notes
print_usage() {
    echo "Usage: $0 <service_name> <port_number>"
    echo ""
    echo "Notes:"
    echo "1. This script assumes you are using the same working directory and Python environment for all Flask apps."
    echo "   Adjust 'WORKING_DIRECTORY' and 'PYTHON_ENV_PATH' in the script as necessary if they differ per Flask app."
    echo "2. The systemd service file template assumes that your Flask app's main entry is of the format '<service_name>:app'."
    echo "   Modify the template in the script if your Flask app's naming convention is different."
    echo "3. This script places the temporary service file in '/tmp'. Adjust the path in the script if needed."
}

# Check for service name and port number input
if [[ -z "$1" ]] || [[ -z "$2" ]]; then
    print_usage
    exit 1
fi

SERVICE_NAME="$1"
PORT_NUMBER="$2"
SERVICE_FILE_PATH="/tmp/${SERVICE_NAME}.service"
WORKING_DIRECTORY="/home/ubuntu/fujinetGameAlerts"
PYTHON_ENV_PATH="/home/ubuntu/fujinetGameAlerts/venv"

# Create a systemd service file based on the template
cat <<EOL > ${SERVICE_FILE_PATH}
[Unit]
Description=${SERVICE_NAME}
After=network.target

[Service]
User=yourusername
Group=yourusername
WorkingDirectory=${WORKING_DIRECTORY}
Environment="PATH=${PYTHON_ENV_PATH}"
ExecStart=${PYTHON_ENV_PATH}/bin/gunicorn -w 4 -b 0.0.0.0:${PORT_NUMBER} ${SERVICE_NAME}:app
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Copy the service file to systemd directory
sudo cp ${SERVICE_FILE_PATH} /etc/systemd/system/

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable ${SERVICE_NAME}

# Start the service
sudo systemctl start ${SERVICE_NAME}

# Display the status of the service
sudo systemctl status ${SERVICE_NAME}
