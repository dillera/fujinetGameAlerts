from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Regexp
from twilio.rest import Client
import random,os, logging, sqlite3
from twilio.base.exceptions import TwilioRestException

app = Flask(__name__)

# Setup Logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] - %(message)s',
                    handlers=[logging.StreamHandler()])

app.config['SECRET_KEY'] = 'your_secret_key'  # Change this to a random string
csrf = CSRFProtect(app)

# Twilio credentials
account_sid = os.getenv('TWILIO_ACCT_SID')
auth_token  = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)
twilio_tn = '+13073646363'
phone_number = '+12673532203'

# Create SQLite3 database connection
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone_number TEXT, code TEXT, name TEXT, confirmed INTEGER, opt_in INTEGER)')
logging.info(f"> >> creating connection to users.db")
conn.commit()
conn.close()


# Create SQLite3 database connection for events
conn_events = sqlite3.connect('events.db')
cursor_events = conn_events.cursor()
cursor_events.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, date TEXT, time TEXT, game_name TEXT, number_of_players INTEGER)')
logging.info(f"> >> creating connection to  events.db")
conn_events.commit()
conn_events.close()



###################################################

class PhoneNumberForm(FlaskForm):
    phone_number = StringField('Phone Number (e.g., 555-555-5555)', validators=[
        DataRequired()
    ])
    submit = SubmitField('Submit US Number for SMS')

class WhatsAppRegistrationForm(FlaskForm):
    whatsapp_number = StringField('WhatsApp Number (e.g., +123 456 7890)', validators=[
        DataRequired()
    ])
    submit_whatsapp = SubmitField('Submit WhatsApp Registration')



def generate_random_code():
    return ''.join(str(random.randint(0, 9)) for _ in range(6))


def clean_phone(phone_number):
    logging.info(f"> cleaning a tn:  {phone_number}")
    # Remove the leading '+' and spaces (if any)
    phone_number = phone_number.lstrip('+').replace(' ', '')
    logging.info(f">>> cleaning a tn:  {phone_number}")

    # Ensure the phone number has at least 10 digits
    if len(phone_number) >= 10:
        # Remove the first digit
        phone_number = phone_number[1:]
        logging.info(f">>> cleaning a tn:  {phone_number}")

        # Format the phone number as "###-###-####"
        cleaned_phone = f'{phone_number[:3]}-{phone_number[3:6]}-{phone_number[6:]}'
        logging.info(f"> cleaning number to:  {cleaned_phone}")
        return cleaned_phone
    else:
        logging.info(f"> cleaning invalid format")
        return None  # Invalid phone number format


def send_twilio_message(body, from_, to):
    try:
        message = client.messages.create(
            body=body,
            from_=from_,
            to=to
        )
        return message.sid
    except TwilioRestException as e:
        flash(f'Twilio Error: {e.msg}', 'error')
        return None


def get_opt_in_status_from_db(phone_number):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # Execute a query to retrieve the opt_in status for the given phone number
    cursor.execute('SELECT opt_in FROM users WHERE phone_number=?', (phone_number,))
    result = cursor.fetchone()

    conn.close()

    if result:
        return result[0]  # Assuming the result is a single value, return it
    else:
        return None  # Return None if no result was found for the given phone number




###################################################
###################################################
# Routes
###################################################


@app.route('/', methods=['GET', 'POST'])
def index():

    phone_form = PhoneNumberForm()
    whatsapp_form = WhatsAppRegistrationForm()

    if request.method == 'POST':


        if phone_form.validate_on_submit():
            phone_number = phone_form.phone_number.data

            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE phone_number=?', (phone_number,))
            user = cursor.fetchone()

            if user:
                # User is here, already confirmed so show them the dashboard page
                # pass along the phone number so we can use it to determine opt_in
                if user[4] == 1:  # User is already confirmed
                    logging.info(f"> found in db and confirmed:  {user}")
                    return redirect(url_for('dashboard', phone_number=phone_number))
                    #return redirect(url_for('dashboard'))

                # they are in the db but not confirmed send them a new code....
                else:
                    logging.info(f"> found in db but NOT CONFIRMED:  {user}")
                    code = generate_random_code()
                    cursor.execute('UPDATE users SET code=? WHERE phone_number=?', (code, phone_number))
                    logging.info(f"> generated new code and updated users with new code: {code} for tn: {phone_number}")
                    conn.commit()
                    message = client.messages.create(
                        body=f'Your verification code is: {code}',
                        from_=twilio_tn,
                        to=phone_number
                    )
                    logging.info(f"> sent a new OTC as SMS ")
                    flash('Another new code was sent to your phone!')

            # they are not in the DB - get a new code, and add them to db and send the intial code via sms
            else:
                code = generate_random_code()
                body = f'Your verification code is: {code}'
                from_= twilio_tn
                to   = phone_number
                message_sid = send_twilio_message(body, from_, to)

                # check for Twilio errors and report them
                if message_sid:
                    flash('Code sent to your phone!', 'success')
                    cursor.execute('INSERT INTO users (phone_number, code, confirmed) VALUES (?, ?, ?)', (phone_number, code, 0))
                    conn.commit()
                    logging.info(f"> sent first OTC as SMS ")
                else:
                    flash('Failed to send you a code to verify your number. Please check the number and try again.', 'error')
                    return redirect(url_for('index'))

            # close any DB connections
            conn.close()
            return redirect(url_for('confirm_code'))


        # Whats App number was submitted
        if whatsapp_form.validate_on_submit():
            logging.info(f"> Submitted a whats app number............ ")
            code = generate_random_code()

            # Send OTC via WhatsApp
            message = client.messages.create(
                body=f'Your verification code is: {code}',
                from_='whatsapp:' + twilio_whatsapp_number,
                to='whatsapp:' + whatsapp_number
            )

            # Store the code and WhatsApp number for later verification
            # Treat WA as a phone number
            conn = sqlite3.connect('users.db')
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (phone_number, code, confirmed) VALUES (?, ?, ?)', (whatsapp_number, code, 0))
            conn.commit()
            conn.close()

            flash('Code sent to your WhatsApp!')
        else:
            flash('Invalid WhatsApp number format')
            logging.info(f"> calling confirm_code for whats up............ ")
            return redirect(url_for('confirm_code'))

    return render_template('index.html', phone_form=phone_form, whatsapp_form=whatsapp_form)




######################################################################################################

@app.route('/dashboard')
def dashboard():

    # if we were called from / then we have the phone_number already
    phone_number = request.args.get('phone_number')
    #opt_in_status = get_opt_in_status_from_db(phone_number)


    # I don't know why but phone_number is +1 format here for some reason
    # clean it so that there is a match in the DB
    #cleaned_phone = clean_phone(phone_number)


    # Check if the user is in the USERS database and confirmed
    # We should check again in case someone just clicked on the Menu Navbar
    conn_users = sqlite3.connect('users.db')
    cursor_users = conn_users.cursor()
    cursor_users.execute('SELECT * FROM users WHERE phone_number=? AND confirmed=1', (phone_number,))
    user = cursor_users.fetchone()
    logging.info(f">in /dashboard for phone: {phone_number}")
 #   logging.info(f">in /dashboard for phone: {cleaned_phone}")



    if user:
        opt_in_status = user[5]  # Assuming `opt_in` is the 6th column in your users table

        logging.info(f">in /dashboard found a user....")
        logging.info(f">> user[1] = {user[1]}")
        logging.info(f">> user[2] = {user[2]}")
        logging.info(f">> user[3] = {user[3]}")
        logging.info(f">> user[4] = {user[4]}")
        logging.info(f">> user[5] = {user[5]}")

        # Fetch events from events.db
        conn_events = sqlite3.connect('events.db')
        cursor_events = conn_events.cursor()

        cursor_events.execute('SELECT * FROM events')
        events = cursor_events.fetchall()
        conn_events.close()
        
        # set the opt_in stats
        opt_in_status = user[5]

        #return render_template('dashboard.html', events=events, phone_number=cleaned_phone, opt_in=opt_in_status)
        return render_template('dashboard.html', events=events, phone_number=phone_number)


    else:
        flash('Invalid user not found in DB.')

    flash('Something bad - > Welcome to the Dashboard Page.')
    conn_users.close()
    return redirect(url_for('index'))


@app.route('/update_opt_in', methods=['POST'])
def update_opt_in():
    logging.info(f">in update_opt_in going to update opt-in status....")
    logging.info(f"Received request: {request.json}")
 
    try:

        opt_in_status = request.json.get('opt_in_status')
        phone         = request.json.get('phone')

        logging.info(f"Received request to update opt_in_status to {opt_in_status} for phone {phone}")

        # Update the database with the new opt_in_status value
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET opt_in=? WHERE phone_number=?', (opt_in_status, phone))
        conn.commit()
        conn.close()

        return jsonify({'success': True}), 200
    except Exception as e:
        logging.error(f"Error updating opt-in status: {str(e)}")
        return jsonify({'success': False}), 500




######################################################################################################

@app.route('/confirm', methods=['POST'])
def confirm():
    

    code = request.form.get('code')  # Get the submitted code
    logging.info(f">in /confirm code:{code}")

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE code=? AND confirmed=0', (code,))
    user = cursor.fetchone()
    logging.info(f">in /confirm user:{user}")

    if user and user[4] == 0:
        logging.info(f">in /confirm ...not confirmed yet")
        logging.info(f">> user[1] = {user[1]}")
        logging.info(f">> user[2] = {user[2]}")
        logging.info(f">> user[3] = {user[3]}")
        logging.info(f">> user[4] = {user[4]}")
        if user[2] == code:
            cursor.execute('UPDATE users SET confirmed=1 WHERE id=?', (user[0],))
            conn.commit()
            conn.close()
            flash('Phone number confirmed! Now Please enter it again below to visit your Dashboard.')
            logging.info(f">in /confirm ...updated db for {user[1]}")
        else:
            flash('Invalid code. Please try again.')
    else:
        flash('Invalid request.')

    return redirect(url_for('index'))

######################################################################################################

@app.route('/confirm_code', methods=['GET', 'POST'])
def confirm_code():
    logging.info(f">in /confirm_code route, calling confirm_code.html for code")
    return render_template('confirm_code.html')

######################################################################################################
######################################################################################################
######################################################################################################

# Route to serve favicon.ico
@app.route('/favicon.ico')
def favicon():
    logging.info(f">looking for favicon")
    return send_from_directory(app.root_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')



if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True, port=5101)

