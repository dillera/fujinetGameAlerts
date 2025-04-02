# GAS - Game Alert System

GAS is a Python-based service designed to monitor game servers, track player activity, and send notifications about significant events via Discord and SMS.

## Features

*   **Game Server Monitoring:** Receives status updates from game servers via a JSON POST request to the `/game` endpoint.
*   **Event Tracking:** Logs game server events (startup, player count changes) and player join/leave times in an SQLite database (`gameEvents.db` by default).
*   **Server Status Tracking:** Maintains a record of known servers and their last reported status (`serverTracking` table).
*   **Player Event Notifications:**
    *   Sends Discord messages when a player joins or leaves a monitored game server.
    *   Sends optional SMS messages to opted-in users for player join/leave events.
    *   Sends a "last player left" notification to Discord and SMS when a server becomes empty.
*   **Daily System Sync:**
    *   Uses APScheduler to run a daily task (default: 3 AM UTC).
    *   Checks for servers that have been empty (`currentplayers = 0`) for over 24 hours based on their last update timestamp.
    *   Updates the timestamp for these idle servers.
    *   Sends a **single, consolidated** notification to Discord summarizing how many idle servers had their timestamps updated.
*   **SMS/WhatsApp Interaction:**
    *   Handles incoming SMS/WhatsApp messages via Twilio webhook at the `/incoming` endpoint.
    *   Supports user opt-in/out commands (`START`, `STOP`, `SUBSCRIBE`, `UNSUBSCRIBE`).
    *   Manages user phone numbers and preferences in the `users` table.
*   **Service Monitoring Endpoints:**
    *   `/health`: Basic health check, returns server time.
    *   `/alive`: Returns startup time and uptime, confirming the service is running.
*   **Status Page:**
    *   `/status`: Provides an HTML page displaying the current status of tracked game servers and players.
*   **Rate Limiting:** Protects endpoints from excessive requests.
*   **Logging:** Comprehensive logging to both console/journald and a rotating file (`logs/gas.log`).

## Architecture

*   **Web Framework:** Flask
*   **WSGI Server:** Gunicorn (recommended for production)
*   **Reverse Proxy:** Nginx (recommended for production, handles SSL, proxies requests to Gunicorn)
*   **Database:** SQLite
*   **Scheduling:** APScheduler (for the daily sync task)
*   **SMS/WhatsApp:** Twilio API
*   **Notifications:** Discord Webhooks

## Setup

1.  **Clone Repository:**
    ```bash
    git clone https://github.com/dillera/fujinetGameAlerts.git
    cd fujinetGameAlerts
    ```
2.  **Python Version:** Requires Python 3.10 or newer.
3.  **Create Virtual Environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
5.  **Environment Variables:**
    Create a `.env` file in the project root directory and add the following variables:

    ```dotenv
    # Required
    TWILIO_ACCT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    TWILIO_AUTH_TOKEN=your_twilio_auth_token
    TWILIO_TN=+1xxxxxxxxxx # Your Twilio phone number
    DISCORD_WEBHOOK=https://discord.com/api/webhooks/your/webhook_url

    # Optional (Defaults shown)
    # PORT=5100
    # DATABASE=gameEvents.db
    # WORKING_DIRECTORY=/path/to/fujinetGameAlerts # Usually set automatically
    # DEBUG=False
    ```
    *   `TWILIO_ACCT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_TN`: Obtain from your Twilio account.
    *   `DISCORD_WEBHOOK`: Create a webhook integration in your Discord server.
    *   `PORT`: Port for the Flask development server or Gunicorn binding (if not using a socket).
    *   `DATABASE`: Path to the SQLite database file.
    *   `WORKING_DIRECTORY`: Base directory for logs and DB (usually the project root).
    *   `DEBUG`: Set to `True` for Flask debug mode (useful for development, **do not use in production**).

## Running Locally (Development)

Ensure your `.env` file is configured and the virtual environment is active.

```bash
python gas.py
```

*   This runs the Flask development server.
*   The APScheduler task for the daily sync will also start.
*   Note: The development server runs with `use_reloader=False` to prevent issues with the scheduler starting multiple times.

## Deployment (Production - Example using Systemd/Gunicorn/Nginx)

This is a typical production setup on a Linux server (e.g., Ubuntu).

1.  **Systemd Service (`gas.service`):**
    Create a service file (e.g., `/etc/systemd/system/gas.service`) like the one included in the repository. Key aspects:
    *   Sets the `User`, `Group`, and `WorkingDirectory`.
    *   Loads environment variables from the `.env` file.
    *   Specifies the `ExecStart` command to run Gunicorn, binding to a Unix socket (`gas.sock`). Binding to a socket is generally preferred over a port when using Nginx locally.
    ```ini
    [Unit]
    Description=Gunicorn instance to serve GAS (Game Alert System)
    After=network.target

    [Service]
    User=ubuntu # Change to your deployment user
    Group=www-data # Or your deployment group
    WorkingDirectory=/home/ubuntu/fujinetGameAlerts # Change path as needed
    Environment="PATH=/home/ubuntu/fujinetGameAlerts/venv/bin" # Change path as needed
    EnvironmentFile=/home/ubuntu/fujinetGameAlerts/.env # Change path as needed
    ExecStart=/home/ubuntu/fujinetGameAlerts/venv/bin/gunicorn --workers 3 --bind unix:gas.sock -m 007 gas:app # Change path & worker count as needed
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    ```
    *   **Important:** Adjust paths, `User`, `Group`, and worker count as necessary for your environment. Ensure the `.env` file path is correct.
    *   Enable and start the service:
        ```bash
        sudo systemctl enable gas.service
        sudo systemctl start gas.service
        sudo systemctl status gas.service
        ```

2.  **Web UI Service (`gasui.service`):**
    Similar to the main service, the web UI needs its own systemd service:
    ```bash
    sudo cp gasui.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable gasui.service
    sudo systemctl start gasui.service
    ```
    
    You'll also need to configure Nginx to proxy to this service, similar to the main service configuration.

3.  **Nginx Configuration:**
    Configure Nginx as a reverse proxy to forward requests to the Gunicorn socket. Create a site configuration (e.g., `/etc/nginx/sites-available/gas`):
    ```nginx
    server {
        listen 80;
        server_name your_domain.com;  # Replace with your domain or IP
 
        # Redirect HTTP to HTTPS (optional but recommended)
        return 301 https://$host$request_uri;
    }
 
    server {
        listen 443 ssl;
        server_name your_domain.com;  # Replace with your domain or IP
 
        # SSL configuration (if using HTTPS)
        ssl_certificate /etc/letsencrypt/live/your_domain.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/your_domain.com/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_prefer_server_ciphers on;
 
        # Main API endpoint
        location /game {
            # Proxy to the Gunicorn socket
            proxy_pass http://unix:/home/ubuntu/fujinetGameAlerts/gas.sock;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
 
        # Web UI endpoints (for gasui.py)
        location / {
            # Proxy to the gasui Gunicorn socket
            proxy_pass http://unix:/home/ubuntu/fujinetGameAlerts/gasui.sock;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
 
        # Special handling if game servers post to a different path prefix externally
        # For example, if servers post to http://your_domain.com/fuji/game
        location /fuji/game {
            # Proxy to the Gunicorn socket BUT tell Flask the route is /game
            proxy_pass http://unix:/home/ubuntu/fujinetGameAlerts/gas.sock:/game; # Adjust socket path
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
 
        # Add other locations as needed (e.g., for static files if any)
    }
    ```
    *   **Important:** Adjust `server_name`, socket path, and SSL configuration as needed. The `/fuji/game` block is only necessary if your external URL differs from the internal Flask route (`/game`).
    *   Enable the site and test Nginx configuration:
        ```bash
        sudo ln -s /etc/nginx/sites-available/gas /etc/nginx/sites-enabled/
        sudo nginx -t
        sudo systemctl restart nginx
        ```

4.  **Deployment Script (`deploy.sh`):**
    The repository includes a `deploy.sh.example` script that automates pulling changes, running setup (installing/updating dependencies), and restarting both the `gas.service` and `gasui.service`. 
    
    To use it:
    ```bash
    # Copy the example to your actual deployment script
    cp deploy.sh.example deploy.sh
    
    # Edit the script to set your server details
    nano deploy.sh
    
    # Make it executable
    chmod +x deploy.sh
    
    # Run the deployment
    ./deploy.sh
    ```
    
    Run it from your local machine where you have SSH access to the server. It assumes SSH keys are configured for passwordless login.

## Monitoring

*   **Systemd Service Logs:**
    ```bash
    # Monitor the main service
    sudo journalctl -u gas.service -f
    
    # Monitor the web UI service
    sudo journalctl -u gasui.service -f
    
    # Monitor both services together
    sudo journalctl -u gas.service -u gasui.service -f
    ```
*   **Application Log File:**
    ```bash
    tail -f /path/to/fujinetGameAlerts/logs/gas.log
    ```
*   **Discord:** Check the configured channel for startup messages, event notifications, and the daily sync message.

## Interacting with Game Servers

Game servers need to send POST requests with a JSON payload to the `/game` endpoint of the running GAS instance (e.g., `http://your_domain.com/game` or `http://your_domain.com/fuji/game` depending on your Nginx setup).

**Required JSON Payload Fields:**

*   `game`: (String) Name or identifier of the game being played.
*   `appkey`: (String) A key for potential future use/authentication (currently logged but not strictly validated).
*   `server`: (String) Identifier for the specific server instance (e.g., IP address, hostname).
*   `region`: (String) Geographic region of the server (e.g., "US East", "EU West").
*   `serverurl`: (String) A unique URL or identifier for the game instance, often including the game name/table ID (e.g., `http://lobby.example.com/?table=123`). This is used as the primary key for tracking server state.
*   `curplayers`: (Integer) The current number of players on the server *at the time of the update*.
*   `maxplayers`: (Integer) The maximum player capacity of the server.

**Example `curl` command:**

```bash
curl -X POST http://your_domain.com/game \\
     -H "Content-Type: application/json" \\
     -d '{
           "game": "Five Card Stud",
           "appkey": "somekey",
           "server": "192.168.1.100",
           "region": "Local Dev",
           "serverurl": "http://192.168.1.100:8081/?table=lobby",
           "curplayers": 2,
           "maxplayers": 5
         }'
```

---
