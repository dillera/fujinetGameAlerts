
from flask import Flask
import logging
from config import Config
from logging_setup import setup_logger
from routes import setup_routes

app = Flask(__name__)
app.config.from_object(Config)

setup_logger(app)
setup_routes(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=Config.DEBUG, port=Config.PORT)
