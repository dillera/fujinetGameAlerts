from datetime import datetime, timedelta
import logging
from db import get_db

def evaluate_server_sync(curplayers, serverurl, game_name):
    logging.info(f">> curplayers for this request is {curplayers}, need to eval server sync... ")

    db = get_db()
    cursor = db.cursor()

    # Check the creation_time and currentplayers for the serverurl in serverTracking
    cursor.execute("SELECT created, currentplayers FROM serverTracking WHERE serverurl = ?", (serverurl,))
    result = cursor.fetchone()

    alert_message = None
    if result:
        logging.info(f">> found row in serverTracking: created: {result[0]} and currentplayers: {result[1]} ")
        creation_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
        current_players_in_db = result[1]

        if current_players_in_db != 0:
            logging.info(f"> inside date OR curplayer 0: setting alert_message to none ")
            alert_message = f'🌐 Server event- GameServer: [{game_name}] the last player has left the game.'

        elif datetime.now() - creation_time < timedelta(hours=24):
            logging.info(f"> inside elif - less than 24 hours: setting alert_message to none ")
            alert_message = None

        else:
            logging.info(f"> inside elif - updating serverTracking row with new time")
            # Update the row with the current time and date
            new_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
            cursor.execute("UPDATE serverTracking SET created = ? WHERE serverurl = ?", (new_time, serverurl))
            db.commit()
            alert_message = f'🌐 Server event- GameServer: game [{game_name}] 24 hour sync.'
    else:
        # No record found, perhaps send the message or handle as needed
        logging.info(f">> No record found in serverTracking ")
        alert_message = f'🌐 Server event- GameServer: [{serverurl}] running game [{game_name}] has 0 players currently.'

    return alert_message
