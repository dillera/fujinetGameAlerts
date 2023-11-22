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
# Fail immediately if not given.
if [[ -z "$1" ]] || [[ -z "$2" ]]; then
    print_usage
    exit 1
fi

#
# Edit below for local env

SERVICE_NAME="$1"
PORT_NUMBER="$2"
SERVICE_FILE_PATH="/tmp/${SERVICE_NAME}.service"

check_env_var() {
    local var_name="$1"
    local var_value="${!var_name}"

    if [[ -z "$var_value" ]]; then
        echo "Error: Environment variable $var_name is not set."
        return 1
    else
        echo "Found: $var_name is set to $var_value."
        return 0
    fi
}

# Check if the environment variables are set
check_env_var "FA_SECRET_KEY"
sk_result=$?
check_env_var "TWILIO_ACCT_SID"
ts_result=$?
check_env_var "TWILIO_AUTH_TOKEN"
ta_result=$?
check_env_var "TWILIO_TN"
tn_result=$?
check_env_var "DISCORD_WEBHOOK"
dw_result=$?
check_env_var "WORKING_DIRECTORY"
wd_result=$?
check_env_var "PYTHON_ENV_PATH"
pp_result=$?

# check each variable and fail if something isn't set
if [[ $sk_result -ne 0 ]] || [[ $ts_result -ne 0 ]] || [[ $ta_result -ne 0 ]] || [[ $tn_result -ne 0 ]] || [[ $dw_result -ne 0 ]] || [[ $wd_result -ne 0 ]] || [[ $pp_result -ne 0 ]]; then
    exit 1
fi

echo 'installing prereqs....'
echo 'ignore failures if these are already installed...'
$PYTHON_ENV_PATH/bin/activate
$PYTHON_ENV_PATH/bin/pip install gunicorn flask

echo 'creating temp service file.....'
# Create a systemd service file based on the template
cat <<EOL > ${SERVICE_FILE_PATH}
[Unit]
Description=${SERVICE_NAME}
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=${WORKING_DIRECTORY}

Environment="PATH=${PYTHON_ENV_PATH}"
Environment="TWILIO_ACCT_SID=${TWILIO_ACCT_SID}"
Environment="TWILIO_AUTH_TOKEN=${TWILIO_AUTH_TOKEN}"
Environment="TWILIO_TN=${TWILIO_TN}"
Environment="FA_SECRET_KEY=${FA_SECRET_KEY}"
Environment="DISCORD_WEBHOOK=${DISCORD_WEBHOOK}"

ExecStart=${PYTHON_ENV_PATH}/bin/gunicorn -w 2 -b 0.0.0.0:${PORT_NUMBER} ${SERVICE_NAME}:app
Restart=always

[Install]
WantedBy=multi-user.target
EOL


echo 'moving files into place.....'

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

echo "Service files created and service started, service set to start at boot."
#echo "systemd says:"
#journalctl -u gas -f -b --no-pager

# end

