from time import sleep

from flask import Flask, url_for, redirect, render_template, request, flash
from passlib import pwd
from flaskext.mysql import MySQL
import RPi.GPIO as GPIO
import logging
import socket

app = Flask(__name__)

# MySQL configurations
app.config['MYSQL_DATABASE_USER'] = 'project-longboard'
app.config['MYSQL_DATABASE_PASSWORD'] = 'l0ngb0@rd'
app.config['MYSQL_DATABASE_DB'] = 'longboard_db'
app.config['MYSQL_DATABASE_HOST'] = 'localhost'
mysql = MySQL(app)

# session config
app.secret_key = pwd.genword(entropy=128)

light_pins = {}
light_pins['Front'] = 20
light_pins['Tail'] = 21

logging.basicConfig(level=logging.DEBUG, filename='output.log', filemode='a')
log = logging.getLogger("output")

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

for name, pin in light_pins.items():
    GPIO.setup(pin, GPIO.OUT)


def get_user_ID(username):
    result = get_data('SELECT user_ID FROM tbl_users WHERE username = %s;', username)
    return optimize_list(result)[0]


def get_username(user_ID):
    result = get_data('SELECT username FROM tbl_users WHERE user_ID = %s;', user_ID)
    return optimize_list(result)[0]


def get_settings_user(user_ID):
    result = get_data('SELECT status_lights, session_running FROM tbl_users WHERE user_ID = %s;', user_ID)[0]
    return result


def toggle_session_state(user_ID):
    result = get_data('SELECT session_running FROM tbl_users WHERE user_ID = %s;', user_ID)[0][0]

    set_data('UPDATE tbl_users ' 
             'SET session_running = %s ' 
             'WHERE user_ID = %s;', (not result, user_ID))
    return not result


def get_users():
    result = get_data('SELECT user_ID, username FROM tbl_users;')
    return result


def optimize_list(start_list):
    new_list = []
    for item in start_list:
        new_list.append(item[0])
    return new_list


def get_data(sql, params=None):
    conn = mysql.connect()
    cursor = conn.cursor()
    records = []

    try:
        log.debug(sql)
        cursor.execute(sql, params)
        result = cursor.fetchall()
        for row in result:
            records.append(list(row))

    except Exception as e:
        log.exception("Fout bij het ophalen van data: {0})".format(e))

    cursor.close()
    conn.close()
    return records


def set_data(sql, params=None):
    conn = mysql.connect()
    cursor = conn.cursor()

    try:
        log.debug(sql)
        cursor.execute(sql, params)
        conn.commit()
        log.debug("SQL uitgevoerd")

    except Exception as e:
        log.exception("Fout bij uitvoeren van sql: {0})".format(e))
        return False

    cursor.close()
    conn.close()
    return True


def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip_address = s.getsockname()[0]
    s.close()
    return ip_address


@app.route('/', methods=['GET', 'POST'])
def kiosk_page():
    flash('You can find me at ' + str(get_ip_address()), 'success')
    users = get_users()
    return render_template('kiosk_page.html', users=users)


@app.route('/kiosk_page/<user_ID>', methods=['GET', 'POST'])
def kiosk_page_start(user_ID):
    session_running = get_settings_user(user_ID)[1]

    if request.method == 'POST':
        # -> create a new session
        print('Toggle session ')
        print(toggle_session_state(user_ID))
        # reload protection
        return redirect('/kiosk_page/{}'.format(user_ID))

    sleep(1)
    print("Session is now: {}".format(session_running))
    list_settings_bool = get_settings_user(user_ID)
    list_settings_class = []
    for setting in list_settings_bool:
        if setting == 0:
            list_settings_class.append('off')
        elif setting == 1:
            list_settings_class.append('on')
    class_lights = list_settings_class[0]
    class_session = list_settings_class[1]

    return render_template('session.html', running=class_session, lights=class_lights, user_ID=user_ID)


def update_lights(user_ID):
    result = get_data('SELECT status_lights FROM tbl_users WHERE user_ID = %s;', user_ID)[0][0]

    for name, pin in light_pins.items():
        GPIO.output(pin, not result)

    set_data('UPDATE tbl_users ' 
             'SET status_lights = %s ' 
             'WHERE user_ID = %s;', (not result, user_ID))


@app.route('/getlog')
def getlog():
    def generate():
        with open('output.log') as f:
            while True:
                yield f.read()
                sleep(1)
    return app.response_class(generate(), mimetype='text/plain')


@app.route('/show_log')
def show_log():
   return render_template('log_info.html')


@app.route('/<redirect_to>/<user_ID>/toggle_lights')
def toggle(redirect_to, user_ID):
    update_lights(user_ID)
    return redirect(redirect_to+'/'+user_ID)


@app.errorhandler(500)
def internal_error(error):
    return redirect(url_for('kiosk_page'))


@app.errorhandler(502)
def internal_error(error):
    return redirect(url_for('kiosk_page'))


@app.errorhandler(400)
def internal_error(error):
    return redirect(url_for('kiosk_page'))

if __name__ == '__main__':
    app.run(port=8080, debug=True)
