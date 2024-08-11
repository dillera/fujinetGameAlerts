
import logging
from logging.handlers import TimedRotatingFileHandler
from config import Config

def setup_logger(app):
    file_handler = TimedRotatingFileHandler(
        Config.LOG_FILE_PATH, 
        when="W0",
        interval=1,
        backupCount=4
    )
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
    file_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
