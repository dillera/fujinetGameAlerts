# FGS G.A.S. - GAME ALERT SYSTEM

August 2024 Update
Version 2.0

## Overview

This project is a refactored version of the FGS Game Alert System (G.A.S.), which handles event processing and notifications for game servers. The system processes incoming POST requests from a lobby server for new games, manages incoming SMS and WhatsApp messages from Twilio, and handles errors. It also sends alerts via Discord and Twilio (SMS/WhatsApp) based on specific conditions.

## Project Structure

The project has been modularized to improve maintainability, scalability, and readability. Below is a breakdown of the key modules and scripts, along with their roles within the system:

### 1. **app.py**
   - **Purpose**: This is the main entry point of the Flask application.
   - **Functionality**:
     - Initializes the Flask application.
     - Configures logging.
     - Sets up the application routes.
     - Starts the Flask server.

### 2. **config.py**
   - **Purpose**: Manages the configuration settings for the application.
   - **Functionality**:
     - Holds environment variables and paths such as database file paths, Twilio credentials, Discord webhook URL, and logging configuration.
     - Centralizes configuration settings, making them easy to manage and update.

### 3. **logging_setup.py**
   - **Purpose**: Configures and manages logging for the application.
   - **Functionality**:
     - Sets up a rotating file handler for logs.
     - Configures logging levels and formats.
     - Ensures that logs are consistently managed across the application.

### 4. **db.py**
   - **Purpose**: Handles database connections and operations.
   - **Functionality**:
     - Manages SQLite database connections.
     - Provides functions to initialize and set up necessary databases (`gameEvents.db`, `smsErrors.db`, `playerTracking.db`, `serverTracking.db`).
     - Ensures that database connections are properly opened and closed.

### 5. **event_logic.py**
   - **Purpose**: Encapsulates the core logic for handling game events, SMS errors, and incoming SMS/WhatsApp messages.
   - **Functionality**:
     - **`handle_game_event(data)`**: Processes game events received via POST requests. Inserts data into the `gameEvents` database and determines if notifications should be sent.
     - **`handle_delete_event(data)`**: Processes DELETE requests to handle the removal of game servers. Logs the deletion and sends notifications.
     - **`handle_sms_error(data)`**: Handles incoming error reports from Twilio. Logs the errors in the `smsErrors` database.
     - **`handle_incoming_sms(data)`**: Processes incoming SMS/WhatsApp messages. Queries the database and responds to the sender with relevant information.

### 6. **server_sync.py**
   - **Purpose**: Manages logic related to server synchronization events.
   - **Functionality**:
     - **`evaluate_server_sync(curplayers, serverurl, game_name)`**: Evaluates server sync events, determines if a notification should be sent, and updates the `serverTracking` database as needed.

### 7. **twilio_handler.py**
   - **Purpose**: Handles the sending of SMS and WhatsApp messages using Twilio.
   - **Functionality**:
     - **`send_sms(to, body)`**: Sends an SMS to the specified number.
     - **`send_whatsapp(to, body)`**: Sends a WhatsApp message to the specified number.

### 8. **discord_handler.py**
   - **Purpose**: Manages sending notifications to a Discord channel via a webhook.
   - **Functionality**:
     - **`send_to_discord(message_content)`**: Sends a message to a Discord channel using the configured webhook URL.

### 9. **utils.py**
   - **Purpose**: Provides utility functions to support other modules.
   - **Functionality**:
     - **`toggle_whatsapp_prefix(input_string)`**: Adds or removes the WhatsApp prefix from a phone number.
     - **`extract_url_and_table_param(url)`**: Extracts the base URL and table parameter from a server URL.

### 10. **routes.py**
   - **Purpose**: Defines and manages the Flask routes for handling HTTP requests.
   - **Functionality**:
     - Sets up routes for handling POST/DELETE requests for game events.
     - Handles routes for SMS errors and incoming Twilio SMS/WhatsApp messages.
     - Delegates the logic to the relevant functions in `event_logic.py`.

## Installation & Setup

1. **Clone the repository**:  
   ```bash
   git clone https://github.com/your-repository/fgs-gas.git
   cd fgs-gas
   ```

2. **Install dependencies**:  
   Ensure you have Python 3.x installed and install the necessary packages:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:  
   Set up your environment variables for Twilio, Discord, and other configurations by creating a `.env` file or exporting them directly:
   ```bash
   export TWILIO_ACCT_SID="your_twilio_account_sid"
   export TWILIO_AUTH_TOKEN="your_twilio_auth_token"
   export TWILIO_TN="your_twilio_phone_number"
   export DISCORD_WEBHOOK="your_discord_webhook_url"
   export WORKING_DIRECTORY="/path/to/your/working/directory"
   ```

4. **Run the application**:  
   Start the Flask server:
   ```bash
   python app.py
   ```

## Usage

- The application will listen for incoming HTTP requests on the specified port.
- You can interact with the game events and SMS/WhatsApp endpoints as described in the `routes.py`.

## Contributing

Feel free to submit issues or pull requests for improvements and bug fixes.

## License

This project is licensed under the MIT License.

---

This README breakdown provides a comprehensive guide to the structure and functionality of your refactored codebase, making it easier for others (and yourself) to understand, maintain, and contribute to the project.