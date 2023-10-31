#
# FGS Event Processor and Twilio Handler
# Handles POSTs from lobby server for new games
# Handles POSTS from twilio for incoming whatsapp or sms messages
# dillera 10.2023
#
from flask import Flask, request, jsonify, g
import sqlite3, os, logging
from twilio.rest import Client
from dotenv import load_dotenv
from datetime import datetime
import requests

app = Flask(__name__)


# Initialize Twilio client
account_sid = os.getenv('TWILIO_ACCT_SID')
auth_token  = os.getenv('TWILIO_AUTH_TOKEN')
twilio_tn   = os.getenv('TWILIO_TN')
webhook_url = os.getenv('DISCORD_WEBHOOK')

type_sms      = 'S'
type_whatsapp = 'W'
app.config['DATABASE'] = 'gameEvents.db'

client      = Client(account_sid, auth_token)


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

# Set up logger
logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [%(levelname)s] - %(message)s',
    handlers=[logging.StreamHandler()])


## Create SQLite database connection
conn = sqlite3.connect('gameEvents.db')
cursor = conn.cursor()

# Create gameEvents table if it doesn't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS gameEvents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created, DATETIME,
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

## add or remove whatsapp prefix to TNs
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
        print("Message sent to Discord successfully!")
    else:
        print(f"Failed to send message to Discord. Status code: {response.status_code}. Response: {response.text}")

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
        print(f"Error sending SMS to {to}: {e}")

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
        print(f"Error sending SMS to {to}: {e}")


########################################################
########################################################
########################################################
# Route for incoming JSON POST
#
@app.route('/game', methods=['POST'])
def json_post():
    current_datetime = datetime.now()

    try:
        data = request.get_json()

        # Log the request data
        logging.info(f'Received JSON data: {data}')

        # Insert data into the database
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO gameEvents (created, game, appkey, server, region, serverurl, status, maxplayers, curplayers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            current_datetime, data['game'], data['appkey'], data['server'], data['region'], 
            data['serverurl'], data['status'], data['maxplayers'], data['curplayers']
        ))
        db.commit()

    except Exception as e:
        # Log any exceptions
        logging.error(f'Error processing JSON data: {e}')
        return jsonify({"error": str(e)}), 400


    # Send SMS using Twilio API
    #client = Client(account_sid, auth_token)

    game = data['game']
    server = data['server']
    players = data['curplayers']
    alert_message = f'New game participant on Game: [{game}] running on Server: [{server}] with {players} players currently online.'

    #message = client.messages.create(
    #                          body=alert_message,
    #                          from_=twilio_tn,
    #                          to=failsafe_mt
    #                      )


    ########################################################
    # find users who have opted in for alerts and send them SMS
    # Connect to the SQLite database
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # Execute the SELECT query
    cursor.execute("SELECT phone_number FROM users WHERE opt_in=1 AND type='S'")
    phone_numbers = cursor.fetchall()
    #conn.close()

    # Loop over the result set and send SMS notifications
    for row in phone_numbers:
        phone_number = row[0]
        send_sms(phone_number, alert_message)
        logging.info(f'Sent sms message to phone: {phone_number} ')


    # Execute the SELECT query
    cursor.execute("SELECT phone_number FROM users WHERE opt_in=1 AND type='W'")
    phone_numbers = cursor.fetchall()
    conn.close()

    # Loop over the result set and send SMS notifications
    for row in phone_numbers:
        phone_number = row[0]
        send_whatsapp(phone_number, alert_message)
        logging.info(f'Sent whatsapp message to phone: {phone_number} ')


    conn.close()


    ########################################################
    # Send Discord Event for every event posted into this app
    # 
    discord_response = send_to_discord(alert_message)
    logging.info(f'Sent to Discord: {discord_response}')
     # ... (rest of the code remains the same)

    return jsonify({"message": "Received JSON data and inserted into database"}), 200



########################################################
########################################################
# Route for Twilio SMS
#
@app.route('/sms', methods=['POST'])
def twilio_sms():
    logging.info(f'> in /sms route, about to parse the twilio request....')

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
        print(f'> SMS > Sent sms to {mo} with SID: {message.sid}')


    return jsonify({"message": "handled incoming message"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True, port=5100)


