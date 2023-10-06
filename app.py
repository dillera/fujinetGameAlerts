from flask import Flask, request, jsonify, g
import sqlite3
from twilio.rest import Client
from dotenv import load_dotenv
import os
import logging
# Load environment variables
#load_dotenv()


app = Flask(__name__)


# Initialize Twilio client
account_sid = os.getenv('TWILIO_ACCT_SID')
auth_token  = os.getenv('TWILIO_AUTH_TOKEN')
twilio_tn   = '+17177166502'
#twilio_tn = '+13073646363'
to_phone_number        = '+12673532203'
app.config['DATABASE'] = 'gameEvents.db'
client = Client(account_sid, auth_token)


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

########################################################
# Route for incoming JSON POST
# Route for incoming JSON POST
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

# Route for Twilio SMS
@app.route('/fuji/sms', methods=['POST'])
def twilio_sms():
    # Get the count of rows in the database
    cursor.execute('SELECT COUNT(*) FROM gameEvents')
    count = cursor.fetchone()[0]

    # Prepare response message
    response_message = f'There are {count} rows in the database.'

    # Send the response back to Twilio
    response = MessagingResponse()
    response.message(response_message)

    return str(response)


if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True, port=5100)


