#
# FGS G.A.S. - GAME ALERT SYSTEM
#  Event Processor and Twilio Handler
#  Handles POSTs from lobby server for new games
#  Handles POSTS from twilio for incoming whatsapp or sms messages
#
# Andy Diller / dillera / 10/2023 - version 1.0.0
# 03/2025 - version 1.0.1
#
from flask import Flask, request, jsonify, g
import sqlite3, os, logging, requests
from twilio.rest import Client
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import urlparse, parse_qs
from functools import wraps
import dotenv
from ratelimit import limits, sleep_and_retry
import socket # Import socket to get hostname

# Load environment variables
try:
    dotenv.load_dotenv()
    print("Loaded environment variables from .env file")
except Exception as e:
    print(f"Warning: Could not load .env file: {e}")

app = Flask(__name__)

# Environment variables with validation
def get_env_var(name, default=None, required=True):
    value = os.getenv(name, default)
    if required and value is None:
        error_msg = f"Missing required environment variable: {name}. "
        error_msg += "Please ensure you have a .env file with this variable or set it in your environment."
        print(error_msg)
        raise ValueError(error_msg)
    return value

# Configuration
try:
    app.config.update(
        TWILIO_ACCT_SID=get_env_var('TWILIO_ACCT_SID'),
        TWILIO_AUTH_TOKEN=get_env_var('TWILIO_AUTH_TOKEN'),
        TWILIO_TN=get_env_var('TWILIO_TN'),
        DISCORD_WEBHOOK=get_env_var('DISCORD_WEBHOOK'),
        WORKING_DIRECTORY=get_env_var('WORKING_DIRECTORY', '/home/ubuntu/fujinetGameAlerts'),
        DEBUG=get_env_var('DEBUG', 'True', required=False).lower() == 'true',
        PORT=get_env_var('PORT', '5100', required=False),
        DATABASE='gameEvents.db'
    )
    print("Configuration loaded successfully")
except ValueError as e:
    print(f"Error in configuration: {e}")
    print("Please check your .env file or environment variables")
    # Re-raise to prevent app from starting with missing config
    raise

# Initialize Twilio client
client = Client(app.config['TWILIO_ACCT_SID'], app.config['TWILIO_AUTH_TOKEN'])

# Constants
TYPE_SMS = 'S'
TYPE_WHATSAPP = 'W'

# Helper functions
def extract_url_and_table_param(url):
    """Extract base URL and table parameter from a URL string."""
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    
    query_params = parse_qs(parsed_url.query)
    table_param = query_params.get('table', [None])[0]

    return base_url, table_param

def send_discord_message(message):
    """Sends a message to the configured Discord webhook."""
    webhook_url = app.config.get('DISCORD_WEBHOOK')
    if not webhook_url:
        logger.warning("Discord webhook URL not configured. Skipping notification.")
        return
    
    payload = {
        "content": message
    }
    try:
        response = requests.post(webhook_url, json=payload)
        response.raise_for_status() # Raise an exception for bad status codes
        logger.info(f"Sent Discord message: {message}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Discord message: {e}")

# Logger
# Ensure logs directory exists
log_dir = os.path.join(app.config['WORKING_DIRECTORY'], 'logs')
try:
    os.makedirs(log_dir, exist_ok=True)
except Exception as e:
    print(f"Warning: Could not create logs directory: {e}")

# File path for your logs
log_file_path = os.path.join(log_dir, 'gas.log')

# Set up logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

try:
    # Set up the handler with error handling
    file_handler = TimedRotatingFileHandler(
        log_file_path, 
        when="W0",  # Rotate every week on Monday
        interval=1,
        backupCount=4  # Keep 4 weeks worth of logs
    )
    file_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
    file_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(file_handler)

    logging.info(f"Logging initialized. Log file: {log_file_path}")
except Exception as e:
    print(f"Warning: Could not initialize file logging: {e}")
    # Fallback to console logging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logging.info("Fallback to console logging due to file logging initialization error")

# Database connection with context manager
class Database:
    def __init__(self, app):
        self.app = app

    def get_db(self):
        if 'db' not in g:
            g.db = sqlite3.connect(self.app.config['DATABASE'])
            g.db.row_factory = sqlite3.Row
        return g.db

    def close_db(self, e=None):
        db = g.pop('db', None)
        if db is not None:
            db.close()

db = Database(app)
app.teardown_appcontext(db.close_db)

# Error handling decorator
def handle_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logging.error(f"Error in {f.__name__}: {str(e)}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    return decorated_function

# Rate limiting decorator - 100 requests per minute
@sleep_and_retry
@limits(calls=100, period=60)
def rate_limit():
    pass

# Log incoming requests
@app.before_request
def log_request_info():
    rate_limit() # Apply rate limiting before processing
    # Log request details
    log_message = (
        f"Incoming Request:\n"
        f"  Method: {request.method}\n"
        f"  URL: {request.url}\n"
        f"  Headers: {dict(request.headers)}\n"
        f"  Body: {request.get_data(as_text=True)}"
    )
    logger.info(log_message)

########################################################
########################################################
# add or remove whatsapp prefix to TNs
def toggle_whatsapp_prefix(input_string):
    prefix = "whatsapp:"
    
    # If string starts with 'whatsapp:', remove it
    if input_string.startswith(prefix):
        return input_string[len(prefix):]
    
    # If string does not start with 'whatsapp:', append it
    else:
        return prefix + input_string

# send a message to discord for this event
def send_to_discord(message_content):
    logging.info(f'in send_to_discord with message: {message_content}')
    logging.info(f'target url: {app.config["DISCORD_WEBHOOK"]}')

    # Create the message payload
    data = {
        "content": message_content,
    }

    # Send the message to Discord
    response = requests.post(app.config["DISCORD_WEBHOOK"], json=data)

    # Log the response
    if response.status_code == 204:
        logging.info("Message sent to Discord successfully!")
    else:
        logging.error(f"Failed to send message to Discord. Status code: {response.status_code}. Response: {response.text}")

    return response

# send a message via Twilio for this event
def send_sms(to, body):
    """Helper function to send an SMS using Twilio."""
    try:
        message = client.messages.create(
            body=body,
            from_=app.config["TWILIO_TN"],
            to=to
        )
        logging.info(f"> Sent SMS event message: {message.sid} to: {to} ")
    except Exception as e:
        logging.error(f"Error sending SMS to {to}: {e}")
        raise

# send a Whatsapp message via Twilio for this event
def send_whatsapp(to, body):
    """Helper function to send a WhatsApp message using Twilio."""
    try:
        message = client.messages.create(
            body=body,
            from_='whatsapp:' + app.config["TWILIO_TN"],
            to='whatsapp:' + to
        )
        logging.info(f"> Sent whatsapp event message: {message.sid} to: {to} ")
    except Exception as e:
        logging.error(f"Error sending WhatsApp message to {to}: {e}")
        raise

########################################################
########################################################
########################################################
# Route for incoming SERVER update
#
@app.route('/game', methods=['POST'])
@handle_errors
def json_post():
    logging.info(f">>>>> In top json_post, handling a post.... ")
    current_datetime = datetime.now()

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        # Validate required fields
        required_fields = ['game', 'appkey', 'server', 'region']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

        # Insert data into gameEvents
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO gameEvents (created, game, appkey, server, region, serverurl, status, maxplayers, curplayers, event_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                current_datetime, data['game'], data['appkey'], data['server'], data['region'], 
                data.get('serverurl'), data.get('status'), data.get('maxplayers', 0), 
                data.get('curplayers', 0), 'POST'
            ))
            conn.commit()

        # Get the base url and the table name from the serverurl
        base_url, table_param = extract_url_and_table_param(data['serverurl'])
        logging.info(f"> extracted table name:{table_param} for server:{base_url} ") 

        # Logic for playerTracking
        # Check if the game already exists in playerTracking
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, total_players FROM playerTracking WHERE game = ?", (data['game'],))
            game_record = cursor.fetchone()

            if game_record:
                # Update curplayers and increment total_players if game exists
                new_total_players = game_record[1] + 1
                cursor.execute("UPDATE playerTracking SET curplayers = ?, total_players = ? WHERE game = ?", (data['curplayers'], new_total_players, data['game']))
            else:
                # Insert new row if game does not exist
                cursor.execute("INSERT INTO playerTracking (game, curplayers, created, total_players) VALUES (?, ?, ?, 1)", (data['game'], data['curplayers'], datetime.now()))

            conn.commit()

        # Logic for serverTracking
        with db.get_db() as conn:
            cursor = conn.cursor()

            # Check if the server URL already exists in serverUpdates
            cursor.execute("SELECT id, total_updates FROM serverTracking WHERE serverurl = ?", (data['serverurl'],))
            server_record = cursor.fetchone()

            if server_record:
                # Update currentplayers to curplayers in POST and increment total_updates if serverurl exists
                new_total_updates = server_record[1] + 1
                cursor.execute("UPDATE serverTracking SET currentplayers = ?, total_updates = ? WHERE serverurl = ?", (data['curplayers'], new_total_updates, data['serverurl']))
            else:
                # Insert new row if serverurl does not exist
                cursor.execute("INSERT INTO serverTracking (serverurl, currentplayers, created, total_updates) VALUES (?, ?, ?, 1)", (data['serverurl'], data['curplayers'], datetime.now()))

            conn.commit()

        # Send Alerts to game-alert-system recipiends
        alert_message = None

        # this is a player event so evaluate if the curplayers is the same as the last event
        # if yes, this is just another sync event and so don't send anything
        # if no then this is a player add or part- send message
        if data['curplayers'] != 0:
            # Query the two most recent gameEvents for the given serverurl
            with db.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT curplayers FROM gameEvents WHERE serverurl = ? ORDER BY created DESC LIMIT 2", (data['serverurl'],))
                results = cursor.fetchall()

                if len(results) == 2 and results[0][0] != results[1][0]:
                    # There are two records and the curplayers values are different
                    alert_message = f'🎮 Player event- Game: [{data["game"]}] now has {data["curplayers"]} player(s) currently online.'

        # this was a server sync message didn't send any 
        else:
            # Check the creation_time and currentplayers for the serverurl in serverTracking
            with db.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT created, currentplayers FROM serverTracking WHERE serverurl = ?", (data['serverurl'],))
                result = cursor.fetchone()

                if result:
                    creation_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
                    current_players_in_db = result[1]

                    if current_players_in_db != 0:
                        alert_message = f'🌐 Server event- GameServer: [{base_url}] the last player has left the game.'

                    elif datetime.now() - creation_time < timedelta(hours=24):
                        alert_message = None

                    else:
                        # Update the row with the current time and date
                        new_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
                        cursor.execute("UPDATE serverTracking SET created = ? WHERE serverurl = ?", (new_time, data['serverurl']))
                        conn.commit()
                        alert_message = f'🌐 Server event- GameServer: game [{data["game"]}] 24 hour sync.'

        # Send message to Discord and users
        if alert_message is not None:
            discord_response = send_to_discord(alert_message)
            logging.info(f'Sent mesage to Discord: {discord_response}')

            # find users who have opted in for alerts and send them SMS
            with db.get_db() as conn:
                cursor = conn.cursor()

                # SEND SMS
                cursor.execute("SELECT phone_number FROM users WHERE opt_in=1 AND type='S'")
                phone_numbers = cursor.fetchall()

                # Loop over the result set and send SMS notifications
                for row in phone_numbers:
                    phone_number = row[0]
                    send_sms(phone_number, alert_message)
                    logging.info(f'Sent sms message to phone: {phone_number} ')

                # SEND WHATSAPP
                cursor.execute("SELECT phone_number FROM users WHERE opt_in=1 AND type='W'")
                phone_numbers = cursor.fetchall()

                # Loop over the result set and send SMS notifications
                for row in phone_numbers:
                    phone_number = row[0]
                    send_whatsapp(phone_number, alert_message)
                    logging.info(f'Sent whatsapp message to phone: {phone_number} ')

    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return jsonify({"error": "Database error occurred"}), 500
    except Exception as e:
        logging.error(f"Error processing request: {e}")
        return jsonify({"error": str(e)}), 400

    return jsonify({"message": "Received JSON data and processed successfully"}), 200

########################################################
########################################################
# Route for incoming DELETE server
#
@app.route('/game', methods=['DELETE'])
@handle_errors
def delete_event():
    logging.info(f">> In DELETE for /game ")
    try:
        data = request.get_json()
        serverurl = data.get('serverurl')

        # Validate serverurl
        if not serverurl:
            return jsonify({"error": "serverurl is required"}), 400

        current_datetime = datetime.now()

        # Insert 'DELETE' event into the database
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO gameEvents (created, serverurl, event_type)
                VALUES (?, ?, ?)
            ''', (current_datetime, serverurl, 'DELETE'))
            conn.commit()

        base_url, table_param = extract_url_and_table_param(serverurl)

        alert_message = f'🌐 Server event - GameServer: [{base_url}] running game [{table_param}] has been deleted from Lobby.'
        discord_response = send_to_discord(alert_message)
        logging.info(f'Sent to Discord: {discord_response}')

        return jsonify({"message": f"'DELETE' event added for serverurl {serverurl}"}), 200

    except Exception as e:
        logging.error(f'Error processing DELETE request: {e}')
        return jsonify({"error": str(e)}), 500

    # Default return, in case none of the above are executed
    return jsonify({"error": "Unknown error occurred"}), 500



########################################################
########################################################
# Route for Twili SMS errors
#
@app.route('/sms/errors', methods=['POST'])
@handle_errors
def sms_errors():
    logging.info(f">> In POST for /sms/errors ")
    try:
        data = request.get_json()
        timestamp = datetime.now()

        # Extracting necessary data from the payload
        resource_sid = data.get('resource_sid', '')
        service_sid = data.get('service_sid', '')
        error_code = data.get('error_code', '')
        error_message = data.get('more_info', {}).get('Msg', '')
        callback_url = data.get('webhook', {}).get('request', {}).get('url', '')
        request_method = data.get('webhook', {}).get('request', {}).get('method', '')

        # Insert data into the database
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO smsErrors (timestamp, resource_sid, service_sid, error_code, error_message, callback_url, request_method, error_details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, resource_sid, service_sid, error_code, error_message, callback_url, request_method, json.dumps(data)))
            conn.commit()

        return jsonify({"message": "Error data stored successfully"}), 200

    except Exception as e:
        # Handle exceptions
        return jsonify({"error": str(e)}), 500

    # Default return, in case none of the above are executed
    return jsonify({"error": "Unknown error occurred"}), 500

########################################################
########################################################
# Route for Twilio SMS
#
@app.route('/sms', methods=['POST'])
@handle_errors
def twilio_sms():
    logging.info(f">> In POST for /sms ")

   # Log all incoming POST parameters from Twilio
    for key, value in request.form.items():
        logging.info(f"{key}: {value}")

     # Get the parameters from request.form instead of request.get_json()
    body    = request.form.get('Body', '')
    mt      = request.form.get('To', '')
    mo      = request.form.get('From', '')
    #profile = request.form.get('ProfileName', '')  # Not a standard Twilio field, ensure it's being sent

    logging.info(f"> WA body is: >>{body}<< ")
    logging.info(f"> WA mt is: >>{mt}<< ")
    logging.info(f"> WA mo is: >>{mo}<< ")


    # Get the count of rows in the database
    with db.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM gameEvents')
        count = cursor.fetchone()[0]
        # Prepare response message
        response_message = f'There are currently {count} rows in the event database.'

    if mo.startswith("whatsapp:"):
        logging.info(f"> WA >mo is whats app ")
        clean_tn = toggle_whatsapp_prefix(mo)
        logging.info(f"> WA >mo cleaned to: {clean_tn} ")

        # Send response to WA
        logging.info(f"> WA > about to send message to: {mo} ")
 
        message = client.messages.create(
            body=f'There are currently {count} rows in the event database.',
            from_='whatsapp:' + app.config["TWILIO_TN"],
            to=mo
        )

        logging.info(f"> WA > Sent whatsapp message: {response_message} to number {mo} ")


    else: 
        clean_tn = mo
        logging.info(f"> mo is SMS tn: {clean_tn} ")

        message = client.messages.create(
            body=f'There are currently {count} rows in the event database.',
            from_=mt,
            to=mo
        )
        logging.info(f'> SMS > Sent sms to {mo} with SID: {message.sid}')


    return jsonify({"message": "handled incoming message"}), 200


if __name__ == '__main__':
    # Ensure all tables exist
    with db.get_db() as conn:
        cursor = conn.cursor()
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS gameEvents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created DATETIME,
                event_type TEXT,
                game TEXT,
                appkey INTEGER,
                server TEXT,
                region TEXT,
                serverurl TEXT,
                status TEXT,
                maxplayers INTEGER,
                curplayers INTEGER
            );
            
            CREATE TABLE IF NOT EXISTS smsErrors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME,
                resource_sid TEXT,
                service_sid TEXT,
                error_code TEXT,
                error_message TEXT,
                callback_url TEXT,
                request_method TEXT,
                error_details TEXT
            );
            
            CREATE TABLE IF NOT EXISTS playerTracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game TEXT UNIQUE,
                curplayers INTEGER,
                total_players INTEGER DEFAULT 0,
                created DATETIME
            );
            
            CREATE TABLE IF NOT EXISTS serverTracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created DATETIME,
                serverurl TEXT,
                currentplayers INTEGER,
                total_updates INTEGER DEFAULT 0
            );
        ''')
        
    # Send startup message to Discord
    try:
        hostname = socket.gethostname()
        startup_message = f"GAS server started successfully on {hostname}."
        send_discord_message(startup_message)
    except Exception as e:
        logger.error(f"Failed to send startup Discord message: {e}")

    # Start Flask development server (for local testing)
    app.run(
        host='0.0.0.0',
        debug=app.config['DEBUG'],
        port=int(app.config['PORT'])
    )
else:
    # Send startup message when run with Gunicorn
    try:
        hostname = socket.gethostname()
        startup_message = f"GAS server started successfully on {hostname} (via Gunicorn)."
        send_discord_message(startup_message)
    except Exception as e:
        logger.error(f"Failed to send startup Discord message (Gunicorn): {e}")
