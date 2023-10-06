from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Regexp
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Change this to a random string

# Create SQLite3 database connection
conn = sqlite3.connect('USERS.db')
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone_number TEXT, confirmed INTEGER)')
conn.commit()
conn.close()

class PhoneNumberForm(FlaskForm):
    phone_number = StringField('Phone Number (e.g., 555-555-5555)', validators=[
        DataRequired(),
        Regexp(r'^\d{3}-\d{3}-\d{4}$', message='Phone number must be in the format 555-555-5555')
    ])
    submit = SubmitField('Submit')

@app.route('/', methods=['GET', 'POST'])
def index():
    form = PhoneNumberForm()

    if form.validate_on_submit():
        phone_number = form.phone_number.data

        conn = sqlite3.connect('USERS.db')
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE phone_number=?', (phone_number,))
        user = cursor.fetchone()

        if user:
            if user[2] == 1:  # User is already confirmed
                flash('Phone number already confirmed!')
            else:
                # Send code via Twilio
                # Generate and send code here (using Twilio API)

                flash('Code sent to your phone!')
        else:
            # Add user to database
            cursor.execute('INSERT INTO users (phone_number, confirmed) VALUES (?, ?)', (phone_number, 0))
            conn.commit()

            # Send code via Twilio
            # Generate and send code here (using Twilio API)

            flash('Code sent to your phone!')

        conn.close()

        return redirect(url_for('confirm_code'))

    return render_template('index.html', form=form)

@app.route('/confirm_code', methods=['GET', 'POST'])
def confirm_code():
    # Create a new form for entering the 6-digit code
    # Validate the code and update the database

    return render_template('confirm_code.html')

if __name__ == '__main__':
    app.run(debug=True)

