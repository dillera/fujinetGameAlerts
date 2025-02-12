from datetime import datetime, timedelta
import logging
from flask import current_app
from db import get_db

def check_global_sync(db):
    """Check if we need to send a global sync message"""
    cursor = db.cursor()
    cursor.execute("SELECT last_sync FROM globalSync WHERE sync_type = 'daily' ORDER BY last_sync DESC LIMIT 1")
    result = cursor.fetchone()

    if not result:
        # First time sync
        current_time = datetime.now()
        cursor.execute("INSERT INTO globalSync (last_sync, sync_type) VALUES (?, 'daily')", (current_time,))
        db.commit()
        return True

    last_sync = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
    if datetime.now() - last_sync >= timedelta(hours=24):
        # Update last sync time
        current_time = datetime.now()
        cursor.execute("UPDATE globalSync SET last_sync = ? WHERE sync_type = 'daily'", (current_time,))
        db.commit()
        return True

    return False

def get_active_servers(db):
    """Get a list of all active servers"""
    cursor = db.cursor()
    cursor.execute("SELECT DISTINCT serverurl, game FROM gameEvents WHERE status = 'active' ORDER BY game")
    return cursor.fetchall()

def evaluate_server_sync(curplayers, serverurl, game_name):
    logging.info(f">> curplayers for this request is {curplayers}, need to eval server sync... ")

    db = get_db(current_app)
    cursor = db.cursor()

    # Check the creation_time and currentplayers for the serverurl in serverTracking
    cursor.execute("SELECT created, currentplayers FROM serverTracking WHERE serverurl = ?", (serverurl,))
    result = cursor.fetchone()

    alert_message = None
    if result:
        logging.info(f">> found row in serverTracking: created: {result[0]} and currentplayers: {result[1]} ")
        current_players_in_db = result[1]

        if current_players_in_db != 0 and curplayers == 0:
            logging.info(f"> Player count changed to 0: setting alert message")
            alert_message = f'🌐 Server event- GameServer: [{game_name}] the last player has left the game.'

        # Check if we need to send a global sync message
        elif curplayers == 0 and check_global_sync(db):
            # Get all active servers
            active_servers = get_active_servers(db)
            if active_servers:
                server_list = "\n".join([f"- [{game}] at {url}" for url, game in active_servers])
                alert_message = f'🌐 Daily Server Status Update\nCurrently active game servers:\n{server_list}'
            else:
                alert_message = '🌐 Daily Server Status Update\nNo active game servers at this time.'

    else:
        # No record found, this is a new server with 0 players
        logging.info(f">> No record found in serverTracking ")
        alert_message = f'🌐 Server event- GameServer: [{serverurl}] running game [{game_name}] has 0 players currently.'

    return alert_message
