from flask import request, jsonify
import logging
from datetime import datetime
from db import get_db, close_connection
from twilio_handler import send_sms, send_whatsapp
from discord_handler import send_to_discord
from utils import toggle_whatsapp_prefix, extract_url_and_table_param
from event_logic import (
    handle_game_event,
    handle_delete_event,
    handle_sms_error,
    handle_incoming_sms
)

def setup_routes(app):
    @app.teardown_appcontext
    def teardown_db(exception):
        close_connection(exception)


    @app.route('/game', methods=['POST'])
    def json_post():
        try:
            data = request.get_json()
            handle_game_event(data)
            return jsonify({"message": "Game event processed successfully"}), 200
        except Exception as e:
            logging.error(f"Error processing request: {e}")
            return jsonify({"error": "An error occurred"}), 500


    @app.route('/game', methods=['DELETE'])
    def delete_event():
        try:
            data = request.get_json()
            response = handle_delete_event(data)
            return jsonify(response), 200
        except ValueError as e:
            logging.error(f"Validation error: {e}")
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            logging.error(f"Error processing DELETE request: {e}")
            return jsonify({"error": "An error occurred"}), 500


    @app.route('/sms/errors', methods=['POST'])
    def sms_errors():
        try:
            data = request.get_json()
            response = handle_sms_error(data)
            return jsonify(response), 200
        except Exception as e:
            logging.error(f"Error processing SMS error: {e}")
            return jsonify({"error": "An error occurred"}), 500


    @app.route('/sms', methods=['POST'])
    def twilio_sms():
        try:
            data = request.form  # Twilio sends data as form-encoded, not JSON
            response = handle_incoming_sms(data)
            return jsonify(response), 200
        except Exception as e:
            logging.error(f"Error processing incoming SMS: {e}")
            return jsonify({"error": "An error occurred"}), 500
