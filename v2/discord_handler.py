
import requests
import logging
from config import Config

def send_to_discord(message_content):
    logging.info(f'in send_to_discord with message: {message_content}')
    data = {
        "content": message_content,
    }

    response = requests.post(Config.DISCORD_WEBHOOK, json=data)

    if response.status_code == 204:
        logging.info("Message sent to Discord successfully!")
    else:
        logging.info(f"Failed to send message to Discord. Status code: {response.status_code}. Response: {response.text}")

    return response
