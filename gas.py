#
# FGS G.A.S. - GAME ALERT SYSTEM
#  Event Processor and Twilio Handler
#  Handles POSTs from lobby server for new games
#  Handles POSTS from twilio for incoming whatsapp or sms messages
#
# Andy Diller / dillera / 10/2023 - version 1.0.0
# 03/2025 - version 1.0.1
#
import logging
import os
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import urlparse, parse_qs
import platform # Added for system info
import atexit # For scheduler shutdown

import dotenv
import requests
from flask import Flask, g, jsonify, request, render_template # Added render_template
from ratelimit import limits, sleep_and_retry
from twilio.rest import Client
import socket # Import socket to get hostname
from apscheduler.schedulers.background import BackgroundScheduler # Added for scheduled tasks
from apscheduler.triggers.cron import CronTrigger # Added for cron-style scheduling

# --- Global Variables ---
APP_START_TIME = datetime.now() # Record startup time
# ----------------------

# --- Early Logger Initialization ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__) # Define logger at module level
# ---------------------------------

# --- Environment Variable Loading & Checking ---
def get_env_var(name, default=None, required=True, is_secret=False):
    """Gets an environment variable, logs its presence (masked if secret), and validates if required."""
    value = os.getenv(name, default)
    if required and value is None:
        error_msg = f"Missing required environment variable: {name}. Please check .env file or environment."
        logger.critical(error_msg) # Log critical before raising
        raise ValueError(error_msg)
    log_value = "********" if is_secret and value else value
    logger.info(f"Env Var Loaded: {name} = {log_value}")
    return value

def check_required_env_vars():
    """Checks all required environment variables at startup."""
    logger.info("Checking required environment variables...")
    required_vars = [
        ('TWILIO_ACCT_SID', True),
        ('TWILIO_AUTH_TOKEN', True),
        ('TWILIO_TN', False),
        ('DISCORD_WEBHOOK', True),
        ('WORKING_DIRECTORY', False),
        ('DATABASE', False), # Check for DATABASE name as well
    ]
    all_present = True
    for var_name, is_secret in required_vars:
        try:
            get_env_var(var_name, required=True, is_secret=is_secret)
        except ValueError:
            # Error already logged in get_env_var
            all_present = False
    
    if all_present:
        logger.info("All required environment variables seem present.")
    else:
        logger.critical("One or more required environment variables MISSING. Startup aborted.")
        # Halt startup if critical variables are missing
        raise RuntimeError("Missing required environment variables, cannot start.")
    return all_present

# Load .env file first
try:
    dotenv_path = dotenv.find_dotenv()
    if dotenv_path:
        logger.info(f"Loading environment variables from: {dotenv_path}")
        dotenv.load_dotenv(dotenv_path)
    else:
        logger.warning(".env file not found. Relying on system environment variables.")
except Exception as e:
    logger.error(f"Error loading .env file: {e}")

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Configuration Loading ---
try:
    logger.info("Loading Flask app configuration...")
    app.config.update(
        TWILIO_ACCT_SID=get_env_var('TWILIO_ACCT_SID', required=True, is_secret=True),
        TWILIO_AUTH_TOKEN=get_env_var('TWILIO_AUTH_TOKEN', required=True, is_secret=True),
        TWILIO_TN=get_env_var('TWILIO_TN', required=True),
        DISCORD_WEBHOOK=get_env_var('DISCORD_WEBHOOK', required=True, is_secret=True), # Mark as secret
        WORKING_DIRECTORY=get_env_var('WORKING_DIRECTORY', default=os.getcwd()), # Default to current dir if not set
        DEBUG=get_env_var('DEBUG', default='False', required=False).lower() == 'true',
        PORT=get_env_var('PORT', default='5100', required=False),
        DATABASE=get_env_var('DATABASE', default='gameEvents.db')
    )
    logger.info("Flask app configuration loaded successfully.")
except (ValueError, RuntimeError) as e:
    # Errors during env var check/load are critical
    logger.critical(f"CRITICAL ERROR during configuration: {e}. Application cannot start.")
    # Exit cleanly if config fails
    import sys
    sys.exit(1)
# ---------------------------

# --- File Logging Configuration (Now that WORKING_DIRECTORY is known) ---
try:
    log_dir = os.path.join(app.config['WORKING_DIRECTORY'], 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, 'gas.log')
    
    file_handler = TimedRotatingFileHandler(
        log_file_path, 
        when="W0", interval=1, backupCount=4
    )
    file_handler.setLevel(logging.INFO)
    # Include logger name in format
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] [%(name)s] - %(message)s') 
    file_handler.setFormatter(formatter)
    
    # Add handler to the root logger (or specific logger if preferred)
    logging.getLogger().addHandler(file_handler) # Add to root logger
    logger.info(f"File logging configured. Log file: {log_file_path}")
except Exception as e:
    logger.warning(f"Could not initialize file logging to {log_file_path}: {e}. Continuing with console logging.")
# -----------------------------------------------------------------------

# --- Twilio Client Initialization ---
client = None
try:
    # Check if keys actually exist in config before initializing
    if app.config.get('TWILIO_ACCT_SID') and app.config.get('TWILIO_AUTH_TOKEN'):
        client = Client(app.config['TWILIO_ACCT_SID'], app.config['TWILIO_AUTH_TOKEN'])
        logger.info("Twilio client initialized successfully.")
    else:
        logger.warning("Twilio credentials not found in config. Twilio client not initialized.")
except Exception as e:
    logger.error(f"Failed to initialize Twilio client even with credentials present: {e}")
# ----------------------------------

# --- Constants ---
TYPE_SMS = 'S'
TYPE_WHATSAPP = 'W'
# ---------------

# --- Helper Functions ---
def extract_url_and_table_param(url):
    """Extract base URL and table parameter from a URL string."""
    try:
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        query_params = parse_qs(parsed_url.query)
        table_param = query_params.get('table', [None])[0]
        return base_url, table_param
    except Exception as e:
        logger.error(f"Error parsing URL '{url}': {e}")
        return None, None

def send_discord_message(message):
    """Sends a message to the configured Discord webhook."""
    webhook_url = app.config.get('DISCORD_WEBHOOK')
    if not webhook_url:
        logger.warning("Discord webhook URL not configured. Skipping notification.")
        return
    
    partial_url = webhook_url[:webhook_url.rfind('/') + 1] + "..." # Mask secret part
    logger.info(f"Attempting to send Discord message to: {partial_url}")
    payload = {"content": message}
    try:
        response = requests.post(webhook_url, json=payload, timeout=10) # Add timeout
        response.raise_for_status()
        logger.info(f"Sent Discord message successfully.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send Discord message to {partial_url}: {e}")
# ----------------------

# --- Database Class and Setup ---
class Database:
    def __init__(self, app):
        self.app = app
        self.db_path = os.path.join(self.app.config['WORKING_DIRECTORY'], self.app.config['DATABASE'])

    def get_db(self):
        if 'db' not in g:
            try:
                logger.debug(f"Opening DB connection to {self.db_path}")
                g.db = sqlite3.connect(self.db_path)
                g.db.row_factory = sqlite3.Row
                logger.info(f"Database connection opened: {self.db_path}")
            except sqlite3.Error as e:
                logger.exception(f"Failed to connect to database {self.db_path}")
                raise
        return g.db

    def close_db(self, e=None):
        db = g.pop('db', None)
        if db is not None:
            try:
                db.close()
                logger.info("Database connection closed.")
            except sqlite3.Error as e:
                logger.error(f"Error closing database connection: {e}")

    def init_db_schema(self):
        logger.info("Initializing database schema...")
        # Use executescript for multiple statements
        schema_sql = '''
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
            
            CREATE TABLE IF NOT EXISTS users (
                phone_number TEXT PRIMARY KEY,
                opt_in INTEGER DEFAULT 0,
                type TEXT DEFAULT 'S' CHECK(type IN ('S', 'W')), -- S=SMS, W=WhatsApp
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''' # (Keep your full schema here)
        try:
            with self.get_db() as conn:
                conn.executescript(schema_sql) 
                conn.commit()
                logger.info("Database schema initialization/verification complete.")
        except sqlite3.Error as e:
            logger.exception("Failed to initialize database schema")
            raise # Reraise to indicate critical failure

db_manager = Database(app) # Create instance for app context

@app.teardown_appcontext
def teardown_db(exception):
    db_manager.close_db(exception)

# Initialize DB schema ONCE at startup (outside request context)
def initialize_database():
    with app.app_context():
        try:
            db_manager.init_db_schema()
        except Exception as e:
            logger.critical(f"DATABASE INITIALIZATION FAILED: {e}. Exiting.")
            import sys
            sys.exit(1)
# -----------------------------

# --- Rate Limiting and Request Handling ---
@sleep_and_retry
@limits(calls=100, period=60)
def rate_limit_check():
    """Performs rate limit check. Called before processing requests."""
    pass # The decorators handle the logic

@app.before_request
def before_request_checks():
    """Runs before each request."""
    try:
        rate_limit_check() # Check rate limit first
    except Exception as e:
        # Log rate limit errors but don't necessarily stop request
        logger.warning(f"Rate limit check failed: {e}") 
        # Optionally return an error response: return jsonify(...), 429
        
    # Log request details
    try:
        # Use request.get_data carefully, might consume the stream
        body_preview = request.get_data(cache=True, as_text=True)
        body_log = (body_preview[:200] + '...') if len(body_preview) > 200 else body_preview
        
        log_message = (
            f"Incoming Request: {request.remote_addr} - {request.method} {request.url}\n"
            f"  Headers: {dict(request.headers)}\n"
            f"  Body Preview: {body_log}"
        )
        logger.info(log_message)
    except Exception as e:
        logger.error(f"Error logging request details: {e}")

# --- Error Handling Decorator ---
def handle_errors(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            # Access DB within the request context if needed
            # db = db_manager.get_db()
            return f(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Error processing request in {f.__name__}") # Log with stack trace
            return jsonify({"error": "An internal server error occurred."}), 500
    return decorated_function
# --------------------------------------

# --- Application Routes ---
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
        with db_manager.get_db() as conn:
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
        with db_manager.get_db() as conn:
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
        with db_manager.get_db() as conn:
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
            with db_manager.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT curplayers FROM gameEvents WHERE serverurl = ? ORDER BY created DESC LIMIT 2", (data['serverurl'],))
                results = cursor.fetchall()
                logger.info(f"Player change check: Found {len(results)} previous events for {data['serverurl']} -> {results}")

            # Check if we have enough data to compare
            if results and len(results) == 2:
                previous_players = results[1][0] # The second most recent event
                current_players = results[0][0] # The most recent event
                logger.info(f"Player change check: Comparing prev={previous_players} vs curr={current_players} (Incoming data['curplayers']={data['curplayers']})")

                # Compare player counts
                if previous_players < current_players:
                    alert_message = f'🧑‍🤝‍🧑 Player event - GameServer: [{base_url}] running game [{table_param}] player joined. Total players: [{current_players}]'
                    logger.info("Player change check: Player JOIN detected.")
                elif previous_players > current_players:
                    alert_message = f'💨 Player event - GameServer: [{base_url}] running game [{table_param}] player left. Total players: [{current_players}]'
                    logger.info("Player change check: Player LEAVE detected.")
                else:
                    logger.info("Player change check: Player count unchanged.")
            else:
                logger.info("Player change check: Not enough history or condition not met for comparison.")
        
        # this was a server sync message didn't send any 
        else:
            # Check the creation_time and currentplayers for the serverurl in serverTracking
            with db_manager.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT created, currentplayers FROM serverTracking WHERE serverurl = ?", (data['serverurl'],))
                result = cursor.fetchone()

            if result:
                creation_time_str, current_players_in_db = result # Unpack result
                # Only send "last player left" if the DB showed players previously
                if current_players_in_db != 0:
                    alert_message = f'🌐 Server event- GameServer: [{base_url}] the last player has left the game.'
                    logger.info(f"Last player left detected for {data['serverurl']}")
                # Removed the 24-hour sync logic from here - handled by scheduler
                # else:
                #    logger.info(f"Server {data['serverurl']} has 0 players, sync handled by scheduler.")
            else:
                logger.warning(f"No serverTracking record found for {data['serverurl']} when processing 0 player event.")

        logger.info(f"Calculated alert_message: {alert_message}") # Add logging

        # Send message to Discord and users
        if alert_message is not None:
            send_discord_message(alert_message) 
            # find users who have opted in for alerts and send them SMS
            with db_manager.get_db() as conn:
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
        with db_manager.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO gameEvents (created, serverurl, event_type)
                VALUES (?, ?, ?)
            ''', (current_datetime, serverurl, 'DELETE'))
            conn.commit()

        base_url, table_param = extract_url_and_table_param(serverurl)

        alert_message = f'🌐 Server event - GameServer: [{base_url}] running game [{table_param}] has been deleted from Lobby.'
        send_discord_message(alert_message)

        return jsonify({"message": f"'DELETE' event added for serverurl {serverurl}"}), 200

    except Exception as e:
        logging.error(f'Error processing DELETE request: {e}')
        return jsonify({"error": str(e)}), 500

    # Default return, in case none of the above are executed
    return jsonify({"error": "Unknown error occurred"}), 500

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
        with db_manager.get_db() as conn:
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
    with db_manager.get_db() as conn:
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

@app.route('/health', methods=['GET'])
def health_check():
    # Can add checks here (e.g., DB connectivity)
    return jsonify({"status": "ok"}), 200

@app.route('/alive', methods=['GET'])
def alive_status():
    """Returns an HTML page with detailed application and server status."""
    try:
        # Gather information
        hostname = socket.gethostname()
        os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
        python_version = platform.python_version()
        pid = os.getpid()
        now = datetime.now()
        uptime_delta = now - APP_START_TIME
        
        # Format uptime
        total_seconds = int(uptime_delta.total_seconds())
        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"

        # Database Check
        db_status = "Unknown"
        try:
            db = db_manager.get_db()
            # Simple check: Can we execute a basic query?
            cursor = db.execute("SELECT 1")
            cursor.fetchone()
            db_status = "Connected"
            # Note: This opens a connection if not already open for the request
        except sqlite3.Error as db_err:
            logger.error(f"Database check failed for /alive: {db_err}")
            db_status = f"Error: {db_err}"
        except Exception as e:
             logger.error(f"Unexpected error during DB check for /alive: {e}")
             db_status = "Error checking connection"

        status_data = {
            'current_time': now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            'hostname': hostname,
            'os_info': os_info,
            'python_version': python_version,
            'pid': pid,
            'start_time': APP_START_TIME.strftime("%Y-%m-%d %H:%M:%S %Z"),
            'uptime': uptime_str,
            'config': { # Expose only non-sensitive config
                'WORKING_DIRECTORY': app.config.get('WORKING_DIRECTORY'),
                'DATABASE': app.config.get('DATABASE'),
                'DEBUG': app.config.get('DEBUG'),
                'PORT': app.config.get('PORT')
            },
            'db_status': db_status
        }
        return render_template('alive.html', **status_data)

    except Exception as e:
        logger.exception("Error generating /alive status page")
        # Return a simpler error response if template rendering fails
        return "<h1>Error Generating Status Page</h1><p>Check server logs for details.</p>", 500
# ------------------------

# --- Scheduled Task --- #
def perform_daily_sync_check():
    """Scheduled task to check for idle servers and update their sync time."""
    with app.app_context(): # Need app context to access config and db_manager
        logger.info("Scheduler: Running daily sync check...")
        servers_to_update = []
        try:
            twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
            with db_manager.get_db() as conn:
                cursor = conn.cursor()
                # Find servers with 0 players whose timestamp is older than 24h
                cursor.execute("SELECT serverurl FROM serverTracking WHERE currentplayers = 0 AND created < ?", 
                               (twenty_four_hours_ago.strftime('%Y-%m-%d %H:%M:%S.%f'),))
                servers_to_update = [row[0] for row in cursor.fetchall()]

                if servers_to_update:
                    logger.info(f"Scheduler: Found {len(servers_to_update)} idle server(s) needing timestamp update.")
                    new_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
                    
                    # Update timestamps in bulk
                    placeholders = ', '.join('?' * len(servers_to_update))
                    sql = f"UPDATE serverTracking SET created = ? WHERE serverurl IN ({placeholders})"
                    params = [new_time] + servers_to_update
                    cursor.execute(sql, params)
                    conn.commit()
                    logger.info(f"Scheduler: Updated timestamps for {len(servers_to_update)} server(s).")
                    
                    # Send single Discord message
                    discord_message = f"🌐 System Sync: Daily check completed. Updated timestamps for {len(servers_to_update)} idle server(s)."
                    send_discord_message(discord_message)
                else:
                    logger.info("Scheduler: No idle servers required timestamp updates.")
                    # Optionally send a "heartbeat" message even if no updates?
                    # send_discord_message("🌐 System Sync: Daily check completed. No updates needed.")

        except sqlite3.Error as e:
            logger.error(f"Scheduler: Database error during daily sync check: {e}")
        except Exception as e:
            logger.error(f"Scheduler: Unexpected error during daily sync check: {e}")

# --- Main Execution --- #
if __name__ == '__main__':
    logger.info("Starting Flask application...")
    db_manager.init_db() # Ensure DB is ready

    # Initialize Scheduler
    scheduler = BackgroundScheduler(daemon=True)
    # Schedule the job to run daily at 3:00 AM server time
    scheduler.add_job(perform_daily_sync_check, CronTrigger(hour=3, minute=0))
    scheduler.start()
    logger.info("Background scheduler started for daily sync check.")

    # Register scheduler shutdown hook for clean exit
    atexit.register(lambda: scheduler.shutdown())

    # Get port from config, default handled by get_env_var
    port = int(app.config.get('PORT', 5100))
    debug_mode = app.config.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Running on port {port} with debug mode: {debug_mode}")

    # Note: When running with Gunicorn, this block is not executed.
    # Gunicorn manages the process and workers.
    # The scheduler needs to be started when the app is loaded by Gunicorn.
    # We might need to adjust this slightly for Gunicorn deployment.
    app.run(host='0.0.0.0', port=port, debug=debug_mode)

    # Shutdown scheduler (though atexit should handle it)
    # try:
    #     pass # app.run blocks here
    # finally:
    #     logger.info("Shutting down scheduler...")
    #     scheduler.shutdown()

# --- Gunicorn Adjustment --- #
# To ensure the scheduler runs with Gunicorn, we start it when the module is loaded,
# outside the if __name__ == '__main__' block, but ensuring it only happens once.

scheduler_started = False
if not scheduler_started:
    logger.info("Initializing scheduler for Gunicorn...")
    db_manager.init_db() # Ensure DB is ready before scheduler might access it
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(perform_daily_sync_check, CronTrigger(hour=3, minute=0))
    scheduler.start()
    logger.info("Background scheduler started for daily sync check (Gunicorn context).")
    atexit.register(lambda: scheduler.shutdown())
    scheduler_started = True

def toggle_whatsapp_prefix(input_string):
    prefix = "whatsapp:"
    
    # If string starts with 'whatsapp:', remove it
    if input_string.startswith(prefix):
        return input_string[len(prefix):]
    
    # If string does not start with 'whatsapp:', append it
    else:
        return prefix + input_string

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
