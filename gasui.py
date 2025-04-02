# webUI  G.A.S. - GAME ALERT SYSTEM
#
#  Web ui for signup and opt-in for alerts
#  Shows current opt-in, handles otc, shows event table
#
# Andy Diller / dillera / 10/2023
#
import random, os, logging, sqlite3
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from flask import send_from_directory

from flask.sessions import SecureCookieSession
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Regexp
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


app = Flask(__name__)

# Setup Logging
#logging.basicConfig(level=logging.INFO,
 #                   format='%(asctime)s [%(levelname)s] - %(message)s',
 #                   handlers=[logging.StreamHandler()])

VERSION = '1.0.0'
app.config['SECRET_KEY'] = os.getenv('FA_SECRET_KEY')
account_sid              = os.getenv('TWILIO_ACCT_SID')
auth_token               = os.getenv('TWILIO_AUTH_TOKEN')
twilio_tn                = os.getenv('TWILIO_TN')
working_dir              = os.getenv('WORKING_DIRECTORY', os.getcwd())
database_path            = os.getenv('DATABASE', 'gameEvents.db')
database_file            = os.path.join(working_dir, database_path)
type_sms      = 'S'
type_whatsapp = 'W'
set_debug     = False
set_port      = '5101'
client = Client(account_sid, auth_token)
csrf   = CSRFProtect(app)

###################################################
#
# Logger

# File path for your logs
log_dir = os.path.join(working_dir, 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file_path = os.path.join(log_dir, 'gasui.log')

# Set up the handler
file_handler = TimedRotatingFileHandler(
    log_file_path, 
    when="W0", # Rotate every week on Monday (you can adjust this as needed)
    interval=1,
    backupCount=4 # Keep 4 weeks worth of logs
)
file_handler.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
file_handler.setFormatter(formatter)

# Set up the logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)


####################################################
# Database Setup
#

def get_db_connection():
    """Get a connection to the database."""
    try:
        conn = sqlite3.connect(database_file)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logging.error(f"Database connection error: {e}")
        raise

# Initialize database schema if tables don't exist
def init_db_schema():
    """Initialize the database schema if tables don't exist."""
    logging.info(f"Initializing database schema in {database_file}")
    
    # Schema matches the one in gas.py
    schema_sql = '''
        CREATE TABLE IF NOT EXISTS gameEvents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created DATETIME,
            event_type TEXT,
            game TEXT,
            appkey INTEGER,
            server TEXT,
            region TEXT,
            serverurl TEXT,
            status TEXT,
            maxplayers INTEGER,
            curplayers INTEGER
        );
        
        CREATE TABLE IF NOT EXISTS smsErrors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            resource_sid TEXT,
            service_sid TEXT,
            error_code TEXT,
            error_message TEXT,
            callback_url TEXT,
            request_method TEXT,
            error_details TEXT
        );
        
        CREATE TABLE IF NOT EXISTS playerTracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game TEXT UNIQUE,
            curplayers INTEGER,
            total_players INTEGER DEFAULT 0,
            created DATETIME
        );
        
        CREATE TABLE IF NOT EXISTS serverTracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created DATETIME,
            serverurl TEXT,
            currentplayers INTEGER,
            total_updates INTEGER DEFAULT 0
        );
        
        CREATE TABLE IF NOT EXISTS users (
            phone_number TEXT PRIMARY KEY,
            opt_in INTEGER DEFAULT 0,
            type TEXT DEFAULT 'S' CHECK(type IN ('S', 'W')), -- S=SMS, W=WhatsApp
            created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            code TEXT,
            name TEXT,
            confirmed INTEGER DEFAULT 0
        );
        
        CREATE TABLE IF NOT EXISTS sentEvents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created DATETIME,
            target TEXT,
            game TEXT,
            event_id INT
        );
    '''
    
    try:
        conn = get_db_connection()
        conn.executescript(schema_sql)
        conn.commit()
        logging.info("Database schema initialization complete")
    except sqlite3.Error as e:
        logging.error(f"Failed to initialize database schema: {e}")
        raise
    finally:
        if conn:
            conn.close()

# Initialize the database schema
init_db_schema()

###################################################

class MySession(SecureCookieSession):
    def __init__(self, *args, **kwargs):
        kwargs["samesite"] = "None"
        super(MySession, self).__init__(*args, **kwargs)

app.session_cookie_class = MySession



class PhoneNumberForm(FlaskForm):
    phone_number = StringField('Phone Number (start with area code)', validators=[DataRequired()])
    submit = SubmitField('Submit US Number for SMS')

class WhatsAppRegistrationForm(FlaskForm):
    whatsapp_number = StringField('WhatsApp Number (do not type +)', validators=[DataRequired()])
    submit_whatsapp = SubmitField('Submit WhatsApp number for any country')

class ConfirmationForm(FlaskForm):
    otc_code = StringField('Enter 6-digit Code)', validators=[DataRequired() ])
    submit_code = SubmitField('Submit code to verify account')

class DeletionForm(FlaskForm):
    phone_number = StringField('Phone Number (e.g., 555-555-5555)', validators=[DataRequired()])
    submit_code = SubmitField('Delete all my Data')


def generate_random_code():
    return ''.join(random.choices('0123456789', k=6))


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


def transform_phone_number(phone_str):
    # Remove non-numeric characters
    cleaned_number = ''.join(filter(str.isdigit, phone_str))
    
    # Prepend country code and return
    return '+1' + cleaned_number

def transform_whatsapp_number(phone_str):
    # Remove non-numeric characters
    cleaned_number = ''.join(filter(str.isdigit, phone_str))
    
    # Prepend the '+' sign and return
    return '+' + cleaned_number


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
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT opt_in FROM users WHERE phone_number=?', (phone_number,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0]
        else:
            return None
    except Exception as e:
        logging.error(f"Error getting opt-in status: {e}")
        return None

def get_user_count():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logging.error(f"Error getting user count: {e}")
        return 0

def get_sent_events_count():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM sentEvents')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logging.error(f"Error getting sent events count: {e}")
        return 0


###################################################
###################################################
# Routes
###################################################

@app.route('/', methods=['GET', 'POST'])
def index():

    phone_form = PhoneNumberForm()
    whatsapp_form = WhatsAppRegistrationForm()
    current_datetime = datetime.now()

    if request.method == 'POST':

        if phone_form.validate_on_submit():
            phone_number = transform_phone_number(phone_form.phone_number.data)
#            transformed_phone=transform_phone_number(phone_number)
            logging.info(f"> In / - TN:  {phone_number} - going to check if in db")

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE phone_number=?', (phone_number,))
            user = cursor.fetchone()

            if user:
                # User is here, and already confirmed show them the dashboard page
                # pass along the phone number so we can use it to determine opt_in
                if user['confirmed'] == 1:  # User is already confirmed
                    logging.info(f"> found in db and confirmed:  {user}")
                    opt_in_status=get_opt_in_status_from_db(phone_number)
                    logging.info(f"> opt in status found:  {opt_in_status}")
                    return redirect(url_for('dashboard', phone_number=phone_number, opt_in_status=opt_in_status))
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
                logging.info(f"> Got a new tn: {phone_number} not found in the DB, going to clean, add it....")
                code = generate_random_code()
  
                body = f'Your verification code is: {code}'
                from_= twilio_tn
                to   = phone_number
                message_sid = send_twilio_message(body, from_, to)
                transformed_phone=transform_phone_number(phone_number)
                logging.info(f"> transformed_phone tn: {transformed_phone}")

                # check for Twilio errors and report them
                if message_sid:
                    flash('Code sent to your phone!', 'success')
                    cursor.execute('INSERT INTO users (phone_number, code, confirmed, type, created) VALUES (?, ?, ?, ?, ?)', (transformed_phone, code, 0, type_sms, current_datetime))
                    conn.commit()
                    logging.info(f"> sent first OTC and created row in users.db")
                else:
                    logging.info(f"> There was an error, bailing out. ")
                    flash('Failed to send you a code to verify your number. Please check the number and try again.', 'error')
                    return redirect(url_for('index'))

            # close any DB connections
            conn.close()
            return redirect(url_for('confirm_code'))


        ####################################################
        # Whats App number was submitted
        if whatsapp_form.validate_on_submit():
            logging.info(f"> WA > Submitted a whats app number............ ")

            whatsapp_number = transform_whatsapp_number(whatsapp_form.whatsapp_number.data)

            logging.info(f"> WA > Original Number is: {whatsapp_form.whatsapp_number.data} ")
            logging.info(f"> WA > Trans Number is: {whatsapp_number} ")
            logging.info(f"> WA > twilio mo: {twilio_tn} ")

            code = generate_random_code()

            # Find out if the user has a row in the DB
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE phone_number=?', (whatsapp_number,))
            user = cursor.fetchone()

            if user:
                # User is here, AND already confirmed show them the dashboard page
                # pass along the phone number so we can use it to determine opt_in
                if user['confirmed'] == 1:  # User is already confirmed
                    logging.info(f"> WA > found in db and confirmed:  {user}")
                    return redirect(url_for('dashboard', phone_number=whatsapp_number))
                    #return redirect(url_for('dashboard'))

                # they are in the db but not confirmed send them a new code....
                else:
                    logging.info(f"> WA >found in db but NOT CONFIRMED:  {user}")
                    cursor.execute('UPDATE users SET code=? WHERE phone_number=?', (code, whatsapp_number))
                    logging.info(f"> WA >generated new code and updated users with new code: {code} for tn: {whatsapp_number}")
                    conn.commit()
                    conn.close()

                    # Send another code to the WA number
                    message = client.messages.create(
                        body=f'*{code}* is your verification code. For your security, do not share this code.',
                        from_='whatsapp:' + twilio_tn,
                        to='whatsapp:' + whatsapp_number
                    )
                    logging.info(f"> WA > Sent whatsapp message: {message.sid} with new code {code} ")
                    flash('A new code was sent to WhatsApp please check your phone!')
                    return redirect(url_for('confirm_code'))

            # they are not in the DB - get a new code, and add them to db and send the intial code via sms
            else:

                # Send OTC via WhatsApp
                message = client.messages.create(
                    body=f'*{code}* is your verification code. For your security, do not share this code.',
                    from_='whatsapp:' + twilio_tn,
                    to='whatsapp:' + whatsapp_number
                )
                logging.info(f"> WA >Sent whatsapp message: {message.sid} ")

                # Store the code and WhatsApp number for later verification
                # Treat WA as a phone number
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('INSERT INTO users (phone_number, code, confirmed, type, created) VALUES (?, ?, ?, ?, ?)', (whatsapp_number, code, 0, type_whatsapp, current_datetime))
                conn.commit()
                conn.close()

                flash('A code was sent to your WhatsApp- Please check.')
                logging.info(f"> WA > calling confirm_code for whats up............ ")
                return redirect(url_for('confirm_code'))

        else:
            flash('Invalid WhatsApp number format')
            logging.info(f"> WA >error submitting proper WA number, reload index page ")
            return redirect(url_for('index'))

            # close any DB connections
            return redirect(url_for('confirm_code'))


    # nothing submitted, this is the first GET so load the page
    return render_template('index.html', phone_form=phone_form, whatsapp_form=whatsapp_form)



######################################################################################################
######################################################################################################
@app.route('/dashboard')
def dashboard():

    # if we were called from / then we have the phone_number already
    phone_number = request.args.get('phone_number')
    logging.info(f">loading dashboard for tn: {phone_number}")

    # Check if the user is in the database and confirmed
    # We should check again in case someone just clicked on the Menu Navbar
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE phone_number=? AND confirmed=1', (phone_number,))
        user = cursor.fetchone()
        logging.info(f">in /dashboard for phone: {phone_number}")

        if user:
            # if they have already confirmed their tn lets login
            opt_in_status = user['opt_in']

            logging.info(f">in /dashboard")
            logging.info(f">> user phone_number = {user['phone_number']}")
            logging.info(f">> user opt_in = {user['opt_in']}")
            logging.info(f">> user type = {user['type']}")
            logging.info(f">> user confirmed = {user['confirmed']}")

            # Fetch events from the database
            cursor.execute('SELECT * FROM gameEvents ORDER BY created DESC')
            events = cursor.fetchall()
            
            # to be finished
            delete_form = DeletionForm()

            conn.close()
            return render_template('dashboard.html', events=events, phone_number=phone_number, delete_form=delete_form)
        else:
            flash('Invalid user- please register first with a number below.')
            conn.close()
            flash('Welcome back to the index page- try that again.')
            return redirect(url_for('index'))
    except Exception as e:
        logging.error(f"Error in dashboard: {e}")
        flash('An error occurred. Please try again later.')
        return redirect(url_for('index'))

######################################################################################################
@app.route('/update_opt_in', methods=['POST'])
def update_opt_in():
    logging.info(f">in update_opt_in going to update opt-in status....")
    logging.info(f"Received request: {request.json}")
 
    try:
        opt_in_status = request.json.get('opt_in_status')
        phone = request.json.get('phone')

        logging.info(f"Received request to update opt_in_status to {opt_in_status} for phone {phone}")

        # Update the database with the new opt_in_status value
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET opt_in=?, last_updated=CURRENT_TIMESTAMP WHERE phone_number=?', (opt_in_status, phone))
        conn.commit()
        conn.close()

        return jsonify({'success': True}), 200
    except Exception as e:
        logging.error(f"Error updating opt-in status: {str(e)}")
        return jsonify({'success': False}), 500



######################################################################################################
# Confirming OTC Routes
@app.route('/confirm_code', methods=['GET', 'POST'])
def confirm_code():
    confirm_form = ConfirmationForm()
    logging.info(f">in /confirm_code route, calling confirm_code.html for code")
    return render_template('confirm_code.html', confirm_form=confirm_form)


############################################
@app.route('/confirm', methods=['POST'])
def confirm():
    
    code = request.form.get('otc_code')  # Get the submitted code
    cleaned_code = code.strip()
    logging.info(f">in CONFIRM with code:{cleaned_code}")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE code=? AND confirmed=0', (cleaned_code,))
    user = cursor.fetchone()
    logging.info(f">in CONFIRM with user:{user}")

    if user and user['confirmed'] == 0:
        logging.info(f">in CONFIRM ...found the row:")
        logging.info(f">> user phone_number = {user['phone_number']}")
        logging.info(f">> user code = {user['code']}")
        logging.info(f">> user confirmed = {user['confirmed']}")
        if user['code'] == cleaned_code:
            logging.info(f">in CONFIRM if true for  {user['code']} = {cleaned_code}")
            cursor.execute('UPDATE users SET confirmed=1 WHERE phone_number=?', (user['phone_number'],))
            conn.commit()
            conn.close()
            flash('Phone number confirmed! Now Please enter it again below to visit your Dashboard.')
            logging.info(f">in CONFIRM ...updated db and CONFIRMED {user['phone_number']}")
        else:
            flash('Invalid code. Please try again.')
    else:
        flash('Invalid request.')

    return redirect(url_for('index'))


######################################################################################################
# Deleting users
############################################
@app.route('/delete_user', methods=['POST'])
def delete_user():
    logging.info(f">in delete_user top of the try.")

    try:
        # Get the phone number from the form
        phone_number = request.form.get('phone')

        # Check if the phone number is empty
        if not phone_number:
            flash('Please enter a phone number.')
            #return redirect(url_for('dashboard'))
            return render_template('dashboard.html', phone_number=phone_number )

        logging.info(f">in delete_user going to try and delete from users....")
        logging.info(f"Received request: {request}")
        #phone_number = request.form.get('phone_number')
        phone_number = phone_form.phone_number.data

        # Delete the user from the database based on the current phone_number
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE phone_number=?', (phone_number,))
        conn.commit()
        conn.close()

        # You can use flash to display a message if needed
        flash('Going to remove user data from the system.....')

        # Redirect the user to a new page (e.g., a confirmation page)
        return redirect(url_for('deleted_confirmation'))

 
    except Exception as e:
        logging.info(f">in delete_user handling an exception....")
        # Handle other exceptions if needed
        flash('An error occurred. Please try again later.')
        return render_template('dashboard.html', phone_number=phone_number )



############################################
@app.route('/deleted_confirmation')
def deleted_confirmation():
    logging.info(f">in deleted_confirmation good bye....")
    # Your view logic here
    flash('Confirmed: your user and all data are deleted from the system.')
    return render_template('deleted_confirmation.html')



######################################################################################################
######################################################################################################
# ancillary routes for mostly static pages
#
@app.route('/favicon.ico')
def favicon():
    logging.info(f">looking for favicon")
    return send_from_directory(app.root_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/about')
def about():
    users_count = get_user_count()
    events_count = get_sent_events_count()
    return render_template('about.html', version=VERSION, users_count=users_count, events_count=events_count)


if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=set_debug, port=set_port)
