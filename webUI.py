from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Regexp
from twilio.rest import Client
import random,os, logging, sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Change this to a random string
# Twilio credentials
account_sid = os.getenv('TWILIO_ACCT_SID')
auth_token  = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)
twilio_tn = '+13073646363'
phone_number = '+12673532203'

# Create SQLite3 database connection
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone_number TEXT, code TEXT, name TEXT, confirmed INTEGER)')
conn.commit()
conn.close()


# Create SQLite3 database connection for events
conn_events = sqlite3.connect('events.db')
cursor_events = conn_events.cursor()
cursor_events.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, date TEXT, time TEXT, game_name TEXT, number_of_players INTEGER)')
conn_events.commit()
conn_events.close()


# Setup Logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] - %(message)s',
                    handlers=[logging.StreamHandler()])


###################################################

class PhoneNumberForm(FlaskForm):
    phone_number = StringField('Phone Number (e.g., 555-555-5555)', validators=[
        DataRequired(),
        Regexp(r'^\d{3}-\d{3}-\d{4}$', message='Phone number must be in the format 555-555-5555')
    ])
    submit = SubmitField('Submit')


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



###################################################
###################################################
# Routes
###################################################


@app.route('/', methods=['GET', 'POST'])
def index():

    form = PhoneNumberForm()
    if form.validate_on_submit():
        phone_number = form.phone_number.data

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE phone_number=?', (phone_number,))
        user = cursor.fetchone()

        if user:

            # User is here, already confirmed so show them the dashboard page
            if user[4] == 1:  # User is already confirmed
                logging.info(f"> found in db and confirmed:  {user}")
                return redirect(url_for('dashboard'))

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
                logging.info(f"> sent new code as SMS ")
                flash('Another new code was sent to your phone!')

        # they are not in the DB - get a new code, and add them to db and send the intial code via sms
        else:
            code = generate_random_code()
            cursor.execute('INSERT INTO users (phone_number, code, confirmed) VALUES (?, ?, ?)', (phone_number, code, 0))
            conn.commit()
            message = client.messages.create(
                body=f'Your verification code is: {code}',
                from_=twilio_tn,
                to=phone_number
            )
            flash('Code sent to your phone!')
        conn.close()
        return redirect(url_for('confirm_code'))

    return render_template('index.html', form=form)



@app.route('/dashboard')
def dashboard():
    conn_users = sqlite3.connect('users.db')
    cursor_users = conn_users.cursor()

    cleaned_phone = clean_phone(phone_number)


    # Check if the user is in the USERS database and confirmed
    # We should check again in case someone just clicked on the Menu Navbar
    cursor_users.execute('SELECT * FROM users WHERE phone_number=? AND confirmed=1', (cleaned_phone,))
    user = cursor_users.fetchone()
    logging.info(f">in /dashboard for phone: {phone_number}")
    logging.info(f">in /dashboard for phone: {cleaned_phone}")


    if user:
        logging.info(f">in /dashboard found a user....")
        logging.info(f">> user[1] = {user[1]}")
        logging.info(f">> user[2] = {user[2]}")
        logging.info(f">> user[3] = {user[3]}")
        logging.info(f">> user[4] = {user[4]}")

        # Fetch events from events.db
        conn_events = sqlite3.connect('events.db')
        cursor_events = conn_events.cursor()

        cursor_events.execute('SELECT * FROM events')
        events = cursor_events.fetchall()
        conn_events.close()
        
        return render_template('dashboard.html', events=events)

    else:
        flash('Invalid user not found in DB.')

    flash('Something bad - > Welcome to the Dashboard Page.')
    conn_users.close()
    return redirect(url_for('index'))





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
            flash('Phone number confirmed!')
            logging.info(f">in /confirm ...updated db for {user[1]}")
        else:
            flash('Invalid code. Please try again.')
    else:
        flash('Invalid request.')

    return redirect(url_for('index'))


@app.route('/confirm_code', methods=['GET', 'POST'])
def confirm_code():
    return render_template('confirm_code.html')


if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True, port=5101)

