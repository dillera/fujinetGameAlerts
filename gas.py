#
# FGS G.A.S. - GAME ALERT SYSTEM
#  Event Processor and Twilio Handler
#  Handles POSTs from lobby server for new games
#  Handles POSTS from twilio for incoming whatsapp or sms messages
#
# Andy Diller / dillera / 10/2023
#
from flask import Flask, request, jsonify, g
import sqlite3, os, logging, requests
from twilio.rest import Client
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import urlparse, parse_qs


app = Flask(__name__)

# Initialize Twilio client
account_sid = os.getenv('TWILIO_ACCT_SID')
auth_token  = os.getenv('TWILIO_AUTH_TOKEN')
twilio_tn   = os.getenv('TWILIO_TN')
webhook_url = os.getenv('DISCORD_WEBHOOK')
working_dir = os.getenv('WORKING_DIRECTORY')
set_debug     = True
set_port      = '5100'
type_sms      = 'S'
type_whatsapp = 'W'
app.config['DATABASE'] = 'gameEvents.db'
client      = Client(account_sid, auth_token)


###################################################
#
# Logger

# File path for your logs
#log_file_path = f'{working_dir}/logs/gas.log'
log_file_path = '/home/ubuntu/fujinetGameAlerts/logs/gas.log'

# Set up the handler
file_handler = TimedRotatingFileHandler(
    log_file_path, 
    when="W0", # Rotate every week on Monday (you can adjust this as needed)
    interval=1,
    backupCount=4 # Keep 4 weeks worth of logs
)
file_handler.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
file_handler.setFormatter(formatter)

# Set up the logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)


###########################################################################
# Connect to database
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


## Create SQLite database connection
conn = sqlite3.connect('gameEvents.db')
cursor = conn.cursor()

# Create gameEvents table if it doesn't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS gameEvents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created, DATETIME,
        event_type, TEXT,
        game TEXT,
        appkey INTEGER,
        server TEXT,
        region TEXT,
        serverurl TEXT,
        status TEXT,
        maxplayers INTEGER,
        curplayers INTEGER
    )
''')
conn.commit()
conn.close()

## Create SQLite database connection
conn = sqlite3.connect('smsErrors.db')
cursor = conn.cursor()
cursor.execute('''
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
    )
''')
conn.commit()
conn.close()

## Create playerTracking
conn = sqlite3.connect('playerTracking.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS playerTracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game TEXT UNIQUE,
        curplayers INTEGER,
        total_players INTEGER DEFAULT 0,
        created DATETIME
    )
''')
conn.commit()
conn.close()

## Create playerTracking
conn = sqlite3.connect('serverTracking.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS serverTracking (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created DATETIME,
        serverurl TEXT,
        currentplayers INTEGER,
        total_updates INTEGER DEFAULT 0
    )
''')
conn.commit()
conn.close()


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
    logging.info(f'target url: {webhook_url}')
    # Replace with the webhook URL you copied from Discord
    #webhook_url = 'YOUR_DISCORD_WEBHOOK_URL'
    # defined above

    # Create the message payload
    data = {
        "content": message_content,
        # Optionally, you can also add "username" and "avatar_url" parameters here to customize the webhook's appearance
    }

    # Send the message to Discord
    response = requests.post(webhook_url, json=data)

    # Log the response (optional)
    if response.status_code == 204:
        logging.info("Message sent to Discord successfully!")
    else:
        logging.info(f"Failed to send message to Discord. Status code: {response.status_code}. Response: {response.text}")

    return response

# send a message via Twilio for this event
def send_sms(to, body):
    """Helper function to send an SMS using Twilio."""
    try:
        message = client.messages.create(
            body=body,
            from_=twilio_tn,
            to=to
        )
        logging.info(f"> Sent SMS event message: {message.sid} to: {to} ")
    except Exception as e:
        logging.info(f"Error sending SMS to {to}: {e}")

# send a Whatsapp message via Twilio for this event
def send_whatsapp(to, body):
    try:
        message = client.messages.create(
            body=body,
            from_='whatsapp:' + twilio_tn,
            to='whatsapp:' + to
        )
        logging.info(f"> Sent whatsapp event message: {message.sid} to: {to} ")
    except Exception as e:
        logging.info(f"Error sending SMS to {to}: {e}")


def extract_url_and_table_param(url):
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    
    query_params = parse_qs(parsed_url.query)
    table_param = query_params.get('table', [None])[0]

    return base_url, table_param



########################################################
########################################################
########################################################
# Route for incoming SERVER update
#
@app.route('/game', methods=['POST'])

def json_post():
    logging.info(f">> In POST for /game ")
    current_datetime = datetime.now()

    try:
        data = request.get_json()

        # Log the request data
        logging.info(f'Received JSON data: {data}')

        curplayers = data['curplayers']
        game_name = data['game']
        serverurl = data['serverurl']
        logging.error(f'> Data in this post is: currentplayers:{curplayers} game_name:{game_name}, serverurl:{serverurl}  ')

########################################################
        # Insert data into the gameEvents database
        conn = sqlite3.connect('gameEvents.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO gameEvents (created, game, appkey, server, region, serverurl, status, maxplayers, curplayers, event_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            current_datetime, data['game'], data['appkey'], data['server'], data['region'], 
            data['serverurl'], data['status'], data['maxplayers'], data['curplayers'], 'POST'
        ))
        conn.commit()
        logging.info(f">> committed update for gameEvents ")
        #conn.close()

########################################################
    # When a new game is POSTed, a new row is inserted with total_players initialized to 1.
    # When an existing game is POSTed, the total_players is incremented by 1.
    # This setup will ensure that each POST request for a game will either create a new record 
    # with a total_players count of 1 or update an existing record by incrementing the total_players count. 

        # Logic for playerTracking
        # Check if the game already exists in playerTracking
        conn = sqlite3.connect('playerTracking.db')
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
        logging.info(f">> committed update for playerTracking ")
        # conn.close()

 
########################################################
    # When a new game is POSTed, a new row is inserted with total_players initialized to 1.
    # When an existing game is POSTed, the total_players is incremented by 1.
    # This setup will ensure that each POST request for a game will either create a new record 
    # with a total_players count of 1 or update an existing record by incrementing the total_players count. 





        # Get the base url and the table name from the serverurl
        base_url, table_param = extract_url_and_table_param(serverurl)
        logging.info(f">>> extracted table name {table_param} for server {base_url} ") 

        logging.info(f">> open db connection for serverTracking ") 
        conn = sqlite3.connect('serverTracking.db')
        cursor = conn.cursor()



        # This could be a server message that all players have left, or it could be a
        # server 'sync' message sent every 10min in order to clean up abandoned clients
        # that didn't cleanly leave the server. Figure out which by looking at the row
        # in serverTracking to see if the last update to it had any value except 0.
        #
        # If it's 0 we know it's just another sync and so don't send anything.
        # if it's not 0 then that was the last player leaving the server so send an update.

        if curplayers == 0:
            logging.info(f">> curplayers for this request is {curplayers}, need to eval server sync... ") 

            # Check the creation_time and currentplayers for the serverurl in serverTracking
            cursor.execute("SELECT created, currentplayers FROM serverTracking WHERE serverurl = ?", (serverurl,))
            result = cursor.fetchone()

            if result:
                logging.info(f">> found row in serverTracking: created: {result[0]} and currentplayers: {result[1]} ") 
                creation_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
                current_players_in_db = result[1]
               
                if datetime.now() - creation_time < timedelta(hours=24) or current_players_in_db != 0:
                    logging.info(f"> if: setting alert_message to none ") 
                    alert_message = None
                else:
                    logging.info(f"> if/else: setting alert message to server event ")
                    alert_message = f'🌐 Server event- GameServer: [{base_url}] running game [{game_name}] on [{table_param}] has 0 players currently.'
            else:
                # No record found, perhaps send the message or handle as needed
                logging.info(f">> No record found in serverTracking ") 
                alert_message = f'🌐 Server event- GameServer: [{base_url}] running game [{game_name}] on [{table_param}] has 0 players currently.'

        # this is a player event so send a message
        else:
            logging.info(f">> curplayers for this request is {curplayers}, create alert_message ") 
            alert_message = f'🎮 Player event- Game: [{game_name}] now has {curplayers} player(s) currently online.'



# now that we've decided to send the message or not go ahead and update the serverTracking db for this event.

        # Logic for serverTracking
        #logging.info(f">> About to eval curplayers for serverTracking ") 
        #if data['curplayers'] == 0:


        logging.info(f">> Heading into  servertracking.... ") 

        # Check if the server URL already exists in serverUpdates
        cursor.execute("SELECT id, total_updates FROM serverTracking WHERE serverurl = ?", (data['serverurl'],))
        server_record = cursor.fetchone()

        logging.info(f">> server_record--- {server_record} ")
        
        if server_record:
            # Update currentplayers and increment total_updates if serverurl exists
            new_total_updates = server_record[1] + 1
            cursor.execute("UPDATE serverTracking SET currentplayers = ?, total_updates = ? WHERE serverurl = ?", (data['curplayers'], new_total_updates, data['serverurl']))
        else:
            # Insert new row if serverurl does not exist
            cursor.execute("INSERT INTO serverTracking (serverurl, currentplayers, created, total_updates) VALUES (?, ?, ?, 1)", (data['serverurl'], data['curplayers'], datetime.now()))

        conn.commit()
        logging.info(f">> committed update serverTracking ")
        conn.close()


########################################################
########################################################
        # Send Alerts to game-alert-system recipiends

        # if it's not a server-sync message (at least once in 24 hours)
        if alert_message is not None:

            discord_response = send_to_discord(alert_message)
            logging.info(f'Sent to Discord: {discord_response}')


            ########################################################
            # find users who have opted in for alerts and send them SMS
            # Connect to the SQLite database
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()

            ########################################################
            # SEND SMS
            # Execute the SELECT query
            cursor.execute("SELECT phone_number FROM users WHERE opt_in=1 AND type='S'")
            phone_numbers = cursor.fetchall()
            #conn.close()

            # Loop over the result set and send SMS notifications
            for row in phone_numbers:
                phone_number = row[0]
                send_sms(phone_number, alert_message)
                logging.info(f'Sent sms message to phone: {phone_number} ')

            ########################################################
            # SEND WHATSAPP
            # Execute the SELECT query
            cursor.execute("SELECT phone_number FROM users WHERE opt_in=1 AND type='W'")
            phone_numbers = cursor.fetchall()
            #conn.close()

            # Loop over the result set and send SMS notifications
            for row in phone_numbers:
                phone_number = row[0]
                send_whatsapp(phone_number, alert_message)
                logging.info(f'Sent whatsapp message to phone: {phone_number} ')
            conn.close()



        # this was a server sync message didn't send any 
        else:
            logging.info(f'GAS Alert was NOT Sent : - just a server sync')


########################################################



    except Exception as e:
        # Log any exceptions
        logging.error(f'Error processing JSON data: {e}')
        return jsonify({"error": str(e)}), 400


    return jsonify({"message": "Received JSON data and inserted into database"}), 200


########################################################
# Route for incoming DELETE server
#
@app.route('/game', methods=['DELETE'])

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
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO gameEvents (created, serverurl, event_type)
            VALUES (?, ?, ?)
        ''', (current_datetime, serverurl, 'DELETE'))
        db.commit()

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
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO smsErrors (timestamp, resource_sid, service_sid, error_code, error_message, callback_url, request_method, error_details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (timestamp, resource_sid, service_sid, error_code, error_message, callback_url, request_method, json.dumps(data)))
        db.commit()

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
    db = get_db()
    cursor = db.cursor()
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
            from_='whatsapp:' + twilio_tn,
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
    app.run(host='0.0.0.0',debug=set_debug, port=set_port)


