
import os

class Config:
    DATABASE = 'gameEvents.db'
    WORKING_DIRECTORY = os.getenv('WORKING_DIRECTORY', '/home/ubuntu/fujinetGameAlerts')
    TWILIO_ACCT_SID = os.getenv('TWILIO_ACCT_SID')
    TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
    TWILIO_TN = os.getenv('TWILIO_TN')
    DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')
    LOG_FILE_PATH = f'{WORKING_DIRECTORY}/logs/gas.log'
    DEBUG = True
    PORT = 5100
