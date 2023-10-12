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



app = Flask(__name__)


# Initialize Twilio client
account_sid = os.getenv('TWILIO_ACCT_SID')
auth_token  = os.getenv('TWILIO_AUTH_TOKEN')
twilio_tn   = '+17177166502'

account_sid = os.getenv('TWILIO_ACCT_SID')
auth_token  = os.getenv('TWILIO_AUTH_TOKEN')
client      = Client(account_sid, auth_token)
#twilio_mo   = '+13073646363'
twilio_mo   = '+17177166502'
failsafe_mt = '+12673532203'
type_sms      = 'S'
type_whatsapp = 'W'
app.config['DATABASE'] = 'gameEvents.db'


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
        game TEXT,
        gametype INTEGER,
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



########################################################
# Route for incoming JSON POST
#
@app.route('/game', methods=['POST'])
def json_post():
    try:
        data = request.get_json()

        # Log the request data
        logging.info(f'Received JSON data: {data}')

        # Insert data into the database
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO gameEvents (game, gametype, server, region, serverurl, status, maxplayers, curplayers)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['game'], data['gametype'], data['server'], data['region'], 
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
    gametype = data['gametype']

    message = client.messages.create(
                              body=f'New game entry: Game: {game}, Game Type: {gametype}',
                              from_=twilio_tn,
                              to=to_phone_number
                          )

    print(f'Sent message with SID: {message.sid}')

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
    #response_message = f'There are currently {count} rows in the event database.'


    if mo.startswith("whatsapp:"):
        logging.info(f"> WA >mo is whats app ")
        clean_tn = toggle_whatsapp_prefix(mo)
        logging.info(f"> WA >mo cleaned to: {clean_tn} ")

        # Send response to WA
        logging.info(f"> WA > about to send message to twilio for {clean_tn} ")
 

        message = client.messages.create(
            body=f'There are currently {count} rows in the event database.',
            from_='whatsapp:' + twilio_tn,
            to='whatsapp:' + mo
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



    # Send the response back to Twilio
    #response = MessagingResponse()
    #response.message(response_message)
    #return str(response)

    return jsonify({"message": "handled incoming message"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True, port=5100)


