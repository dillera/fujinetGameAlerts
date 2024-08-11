from datetime import datetime
import logging
from db import get_db
from discord_handler import send_to_discord
from twilio_handler import send_sms, send_whatsapp
from server_sync import evaluate_server_sync  # Import the new server sync logic
from utils import toggle_whatsapp_prefix


def handle_game_event(data):
    db = get_db()
    cursor = db.cursor()

    # Extract data from the request
    curplayers = data['curplayers']
    game_name = data['game']
    serverurl = data['serverurl']
    current_datetime = datetime.now()

    # Insert event into gameEvents database
    cursor.execute('''
        INSERT INTO gameEvents (created, game, appkey, server, region, serverurl, status, maxplayers, curplayers, event_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        current_datetime, data['game'], data['appkey'], data['server'], data['region'], 
        data['serverurl'], data['status'], data['maxplayers'], data['curplayers'], 'POST'
    ))
    db.commit()

    # Decide if this is a server sync event or a player event
    if curplayers == 0:
        alert_message = evaluate_server_sync(curplayers, serverurl, game_name)
    else:
        alert_message = evaluate_event_for_notification(data, cursor)

    # Update serverTracking
    update_server_tracking(data, cursor)

    # Send notifications if necessary
    if alert_message:
        send_notifications(alert_message)


def handle_delete_event(data):
    db = get_db()
    cursor = db.cursor()
    current_datetime = datetime.now()

    serverurl = data.get('serverurl')
    if not serverurl:
        raise ValueError("serverurl is required")

    # Insert 'DELETE' event into the gameEvents database
    cursor.execute('''
        INSERT INTO gameEvents (created, serverurl, event_type)
        VALUES (?, ?, ?)
    ''', (current_datetime, serverurl, 'DELETE'))
    db.commit()

    # Extract URL and table parameter (if applicable)
    base_url, table_param = extract_url_and_table_param(serverurl)

    # Prepare the alert message
    alert_message = f'🌐 Server event - GameServer: [{base_url}] running game [{table_param}] has been deleted from Lobby.'
    
    # Send the alert to Discord
    discord_response = send_to_discord(alert_message)
    logging.info(f'Sent to Discord: {discord_response}')

    return {"message": f"'DELETE' event added for serverurl {serverurl}"}


def handle_sms_error(data):
    db = get_db()
    cursor = db.cursor()
    timestamp = datetime.now()

    # Extracting necessary data from the payload
    resource_sid = data.get('resource_sid', '')
    service_sid = data.get('service_sid', '')
    error_code = data.get('error_code', '')
    error_message = data.get('more_info', {}).get('Msg', '')
    callback_url = data.get('webhook', {}).get('request', {}).get('url', '')
    request_method = data.get('webhook', {}).get('request', {}).get('method', '')

    # Insert data into the smsErrors database
    cursor.execute('''
        INSERT INTO smsErrors (timestamp, resource_sid, service_sid, error_code, error_message, callback_url, request_method, error_details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        timestamp, resource_sid, service_sid, error_code, error_message, 
        callback_url, request_method, json.dumps(data)
    ))
    db.commit()

    return {"message": "Error data stored successfully"}

def handle_incoming_sms(data):
    logging.info("Processing incoming SMS/WhatsApp message")

    # Extract necessary information from the POST data
    body = data.get('Body', '')
    mt = data.get('To', '')
    mo = data.get('From', '')

    logging.info(f"Received message: {body} from: {mo} to: {mt}")

    # Get the count of rows in the gameEvents database
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT COUNT(*) FROM gameEvents')
    count = cursor.fetchone()[0]

    response_message = f'There are currently {count} rows in the event database.'

    # Check if the message is from WhatsApp or SMS
    if mo.startswith("whatsapp:"):
        clean_tn = toggle_whatsapp_prefix(mo)
        send_whatsapp(clean_tn, response_message)
        logging.info(f'Sent WhatsApp message to: {mo}')
    else:
        send_sms(mo, response_message)
        logging.info(f'Sent SMS message to: {mo}')

    return {"message": "handled incoming message"}
    

def evaluate_event_for_notification(data, cursor):
    # Logic to decide if an alert needs to be sent
    curplayers = data['curplayers']
    game_name = data['game']
    serverurl = data['serverurl']

    # Query the most recent gameEvents for this serverurl
    cursor.execute("SELECT curplayers FROM gameEvents WHERE serverurl = ? ORDER BY created DESC LIMIT 2", (serverurl,))
    results = cursor.fetchall()

    if len(results) == 2 and results[0][0] != results[1][0]:
        # Players joined or left, send a notification
        return f'🎮 Player event- Game: [{game_name}] now has {curplayers} player(s) currently online.'
    elif curplayers == 0:
        # Handle server sync logic here...
        return f'🌐 Server event- GameServer: [{game_name}] the last player has left the game.'

    return None  # No notification needed

def update_server_tracking(data, cursor):
    # Logic to update the serverTracking database
    serverurl = data['serverurl']
    curplayers = data['curplayers']
    
    cursor.execute("SELECT id, total_updates FROM serverTracking WHERE serverurl = ?", (serverurl,))
    server_record = cursor.fetchone()

    if server_record:
        new_total_updates = server_record[1] + 1
        cursor.execute("UPDATE serverTracking SET currentplayers = ?, total_updates = ? WHERE serverurl = ?", 
                       (curplayers, new_total_updates, serverurl))
    else:
        cursor.execute("INSERT INTO serverTracking (serverurl, currentplayers, created, total_updates) VALUES (?, ?, ?, 1)", 
                       (serverurl, curplayers, datetime.now()))

    db.commit()


def send_notifications(alert_message):
    # Send the alert to Discord
    discord_response = send_to_discord(alert_message)
    logging.info(f'Sent message to Discord: {discord_response}')

    # Send SMS and WhatsApp notifications
    db = get_db()
    cursor = db.cursor()

    # Send SMS notifications
    cursor.execute("SELECT phone_number FROM users WHERE opt_in=1 AND type='S'")
    phone_numbers = cursor.fetchall()
    for row in phone_numbers:
        send_sms(row[0], alert_message)
        logging.info(f'Sent SMS to {row[0]}')

    # Send WhatsApp notifications
    cursor.execute("SELECT phone_number FROM users WHERE opt_in=1 AND type='W'")
    phone_numbers = cursor.fetchall()
    for row in phone_numbers:
        send_whatsapp(row[0], alert_message)
        logging.info(f'Sent WhatsApp to {row[0]}')


