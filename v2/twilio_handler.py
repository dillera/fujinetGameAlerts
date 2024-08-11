
from twilio.rest import Client
import logging
from config import Config

client = Client(Config.TWILIO_ACCT_SID, Config.TWILIO_AUTH_TOKEN)

def send_sms(to, body):
    try:
        message = client.messages.create(
            body=body,
            from_=Config.TWILIO_TN,
            to=to
        )
        logging.info(f"> Sent SMS event message: {message.sid} to: {to} ")
    except Exception as e:
        logging.info(f"Error sending SMS to {to}: {e}")

def send_whatsapp(to, body):
    try:
        message = client.messages.create(
            body=body,
            from_='whatsapp:' + Config.TWILIO_TN,
            to='whatsapp:' + to
        )
        logging.info(f"> Sent whatsapp event message: {message.sid} to: {to} ")
    except Exception as e:
        logging.info(f"Error sending WhatsApp to {to}: {e}")
