from flask import Flask, flash, render_template, request, redirect, session, url_for
from flaskext.mysql import MySQL
from flask_httpauth import HTTPBasicAuth
from passlib import pwd
from passlib.hash import argon2
import RPi.GPIO as GPIO
import logging
import socket
import calculateDistance
from gps import ultimateGPS
gpsModule = ultimateGPS()

app = Flask(__name__)

# MySQL configurations
app.config['MYSQL_DATABASE_USER'] = 'project-longboard'
app.config['MYSQL_DATABASE_PASSWORD'] = 'l0ngb0@rd'
app.config['MYSQL_DATABASE_DB'] = 'longboard_db'
app.config['MYSQL_DATABASE_HOST'] = 'localhost'
mysql = MySQL(app)
auth = HTTPBasicAuth()

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


def get_user_ID(username):
    result = get_data('SELECT user_ID FROM tbl_users WHERE username = %s;', username)
    return optimize_list(result)[0]


def user_ID_session(session_name):
    user_ID = session.get(session_name)
    print('>>> ' + str(user_ID) + '<<<')
    if user_ID is None:
        print('user_ID IS NONE')
        return redirect(url_for('index'))
    else:
        return user_ID


def get_username(user_ID):
    result = get_data('SELECT username FROM tbl_users WHERE user_ID = %s;', user_ID)
    return optimize_list(result)[0]


def get_settings_user(user_ID):
    result = get_data('SELECT status_lights, session_running FROM tbl_users WHERE user_ID = %s;', user_ID)[0]
    return result


def update_password(password, user_ID):
    set_data('UPDATE tbl_users ' +
             'SET password = %s ' +
             'WHERE user_ID = %s;', (password, user_ID))


def get_sessions(user_ID):
    result = get_data('SELECT session.session_ID, session.start_date_time, session.stop_date_time FROM tbl_sessions as session '
                      'WHERE session.user_ID = %s ORDER BY session.session_ID DESC;', user_ID)
    return result


def toggle_session_state(user_ID):
    result = get_data('SELECT session_running FROM tbl_users WHERE user_ID = %s;', user_ID)[0][0]

    set_data('UPDATE tbl_users ' 
             'SET session_running = %s ' 
             'WHERE user_ID = %s;', (not result, user_ID))
    return not result


def get_duration(session_ID):
    result = get_data('SELECT TIMESTAMPDIFF(MINUTE, start_date_time, stop_date_time) FROM tbl_sessions WHERE session_ID = %s;', session_ID)
    return result


def get_total_duration(user_ID):
    result = get_data('SELECT SUM(TIMESTAMPDIFF(MINUTE, start_date_time, stop_date_time)) FROM tbl_sessions WHERE user_ID = %s;', user_ID)
    return optimize_list(result)[0]


def get_table_info(user_ID):
    sql = 'SELECT DATE(session.start_date_time), TIME(session.start_date_time), concat(TIMESTAMPDIFF(MINUTE, start_date_time, stop_date_time), " min") ' \
          'FROM tbl_sessions as session WHERE session.user_ID = %s ORDER BY session.session_ID DESC;'

    result = get_data(sql, user_ID)

    return result


def get_waypoints_from_session(user_ID, session_ID):
    result = get_data('SELECT session.session_ID, waypoints.latitude, waypoints.longitude, waypoints.altitude, waypoints.speed, waypoints.time '
                      'FROM tbl_sessions as session ' 
                      'JOIN tbl_waypoints as waypoints on session.session_ID = waypoints.session_ID ' 
                      'WHERE session.user_ID = %s and session.session_ID = %s ' 
                      'ORDER BY waypoints.time;', (user_ID, session_ID))
    return result


def get_last_waypoints_from_session(user_ID, session_ID):
    result = get_data('SELECT waypoints.latitude, waypoints.longitude, waypoints.time '
                      'FROM tbl_sessions as session ' 
                      'JOIN tbl_waypoints as waypoints on session.session_ID = waypoints.session_ID ' 
                      'WHERE session.user_ID = %s and session.session_ID = %s ' 
                      'ORDER BY waypoints.time DESC LIMIT 1;', (user_ID, session_ID))
    return result[0]


def get_coordinates_from_session(user_ID, session_ID):
    result = get_data('SELECT waypoints.latitude, waypoints.longitude '
                      'FROM tbl_sessions as session ' 
                      'JOIN tbl_waypoints as waypoints on session.session_ID = waypoints.session_ID ' 
                      'WHERE session.user_ID = %s and session.session_ID = %s ' 
                      'ORDER BY waypoints.time;', (user_ID, session_ID))
    return result


def get_coordinate_objects(user_ID, session_ID):
    result = get_coordinates_from_session(user_ID, session_ID)
    new_result = []
    for row in result:
        data = {}
        data['lat'] = row[0]
        data['lng'] = row[1]
        new_result.append(data)
    return new_result


def get_average_speed_from_session(user_ID, session_ID):
    result = get_data('SELECT ROUND(AVG(waypoints.speed), 2) '
                      'FROM tbl_sessions as session ' 
                      'JOIN tbl_waypoints as waypoints on session.session_ID = waypoints.session_ID ' 
                      'WHERE session.user_ID = %s and session.session_ID = %s ' 
                      'ORDER BY waypoints.time;', (user_ID, session_ID))
    return optimize_list(result)[0]


def get_last_session(user_ID):
    result = get_data('SELECT session_ID, TIMESTAMPDIFF(MINUTE, start_date_time, stop_date_time), start_date_time '
                      'FROM tbl_sessions as session '
                      'WHERE user_ID = %s '
                      'ORDER BY session.session_ID DESC LIMIT 1;', user_ID)
    return result[0]


def calculate_distance(user_ID, session_ID):
    return calculateDistance.totalDistance(get_coordinates_from_session(user_ID, session_ID))


def get_total_distance_from_user(user_ID):
    info = get_sessions(user_ID)
    distance = 0
    for row in info:
        distance += calculate_distance(user_ID, row[0])                      # id

    return round(distance, 2)


def get_users():
    result = get_data('SELECT user_ID, username FROM tbl_users;')
    return result


def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip_address = s.getsockname()[0]
    s.close()
    return ip_address


def optimize_list(start_list):
    new_list = []
    for item in start_list:
        new_list.append(item[0])
    return new_list


def add_user(login, mail, password):
    try:
        if get_data('SELECT username FROM tbl_users WHERE username = %s', login):
            flash('User <{}> already exists!'.format(login), 'error')
            return False

        argon_hash = argon2.hash(password)

        if set_data('INSERT INTO tbl_users (username, email, password) VALUES (%s, %s, %s);', (login, mail, argon_hash)):
            flash('Added user {}'.format(login), 'success')
            return True

    except Exception as ex:
        flash('Error adding user {}: {}'.format(login, ex), 'error')
        log.exception(str(ex))
        return False


@auth.verify_password
def verify_credentials(username, password):
    authorized = False

    if not (password and username):
        flash('Fill in all the fields', 'error')
    else:
        record = get_data('SELECT password FROM tbl_users WHERE username = %s', username)
        if not record:
            flash('User doesn\'t exist', 'error')
        else:
            authorized = argon2.verify(password, record[0][0])
            if authorized:
                session['user_ID'] = get_user_ID(username)
            else:
                flash('Password incorrect', 'error')
    return authorized


@app.route('/', methods=['GET', 'POST'])
def index():
    session['user_ID'] = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if verify_credentials(username, password):
            return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        mail = request.form['mail']
        password = request.form['password']
        repeat_password = request.form['rep_password']
        print('post')
        if not (username and mail and password and repeat_password):
            flash("Fill in all the fields!", 'error')
            print('empty')
        elif not (password == repeat_password):
            flash("Passwords don't match", 'error')
            print('pass')
        else:
            result = add_user(username, mail, password)
            print('user added')
            if result:
                session['user_ID'] = get_user_ID(username)
                return redirect(url_for('dashboard'))

    return render_template('register.html')


#@auth.login_required
@app.route('/dashboard')
def dashboard():
    user_ID = session.get('user_ID')
    log.debug("< {}".format(user_ID))
    try:
        last_session = get_last_session(user_ID)
        if last_session[1] == None:
            # there is a session running
            time = '...'
        else:
            time = last_session[1]
        template_data = {
            'id': last_session[0],
            'distance': calculate_distance(user_ID, last_session[0]),
            'time': time,
            'speed': get_average_speed_from_session(user_ID, last_session[0]),
            'total_distance': get_total_distance_from_user(user_ID),
            'total_time': get_total_duration(user_ID),
            'coordinates': get_coordinate_objects(user_ID, last_session[0])
        }
    except Exception as ex:
        log.exception(str(ex))
        template_data = {
            'id': 0,
            'distance': 0,
            'time': 0,
            'speed': 0,
            'total_distance': 0,
            'total_time': 0,
            'coordinates': (0, 0)
        }
        # except IndexError:
        # # user_ID is empty ->  redirect login
        # return redirect(url_for('index'))
    return render_template('dashboard.html', **template_data)


@app.route('/routes', methods=['GET', 'POST'])
def routes():
    user_ID = session.get('user_ID')
    table_headers = ["Id", "Date", "Startime", "Duration", "Distance"]

    data_grid = []
    info = get_table_info(user_ID)

    for row in info:
        data_row = []
        data_row.append(len(info) - info.index(row))
        for col in row:
            if col == None or col == '':
                col = '/'
            data_row.append(col)
        co = get_coordinates_from_session(user_ID, data_row[0])
        data_row.append(str(calculateDistance.totalDistance(co)) + " km")
        data_grid.append(data_row)

    return render_template('routes.html', header_list=table_headers, datalist_of_list=data_grid)


@app.route('/details_route/<route_id>')
def details_route(route_id):
    user_ID = session.get('user_ID')
    last_session = get_last_session(user_ID)
    distance = calculate_distance(user_ID, route_id)
    time = last_session[1]
    coordinates = get_coordinate_objects(user_ID, route_id)
    return render_template('detail_route.html', distance=distance, time=time, coordinates=coordinates)


@app.route('/longboard', methods=['GET', 'POST'])
def longboard():
    user_ID = session.get('user_ID')
    session_running = get_settings_user(user_ID)[1]

    if request.method == 'POST':
        print('post')
        # -> create a new session if the gps has a fix
        print('all')
        print(gpsModule.get_parsed_gps_data()['fix'])
        print('fix')
        print(gpsModule.get_parsed_gps_data()['fix'])
        if not gpsModule.get_parsed_gps_data()['fix'] and not session_running:
            print('Session could not be started, no fix.')
            flash('Session could not be started, no fix.', 'error')
        elif not gpsModule.get_parsed_gps_data()['fix'] and session_running:
            print('Session could not be stopped, no fix.')
            flash('Session could not be stopped, no fix.', 'error')
        else:
            print('Toggle session')
            print(toggle_session_state(user_ID))
            # reload protection
            return redirect(url_for('longboard'))

    lat, lng = 0, 0
    window_content = 'Currently unavailable, refresh to try again.'
    username = get_username(user_ID)

    try:
        if session_running:
            # avoid cross threading serial communication
            session_ID = get_last_session(user_ID)[0]
            print("SESSION_ID: {}".format(session_ID))
            print("LAST WAYPOINT: {}".format(get_last_waypoints_from_session(user_ID, session_ID)))
            lat, lng = get_last_waypoints_from_session(user_ID, session_ID)[0], get_last_waypoints_from_session(user_ID, session_ID)[1]
        else:
            # No session running -> serial port is available
            if not gpsModule.get_parsed_gps_data()['fix'] or not gpsModule.get_parsed_gps_data()['valid']:
                lat, lng = gpsModule.get_current_location()
                print("Serial gps data")
            else:
                flash('GPS not available. Try again later', 'error')
        window_content = 'Located here'
        print('Got location {} | {}'.format(lat, lng))
    except Exception as ex:
        flash('GPS not available. Try again later', 'error')
        log.exception(str(ex))
        print(str(ex))

    # time.sleep(1)
    list_settings_bool = get_settings_user(user_ID)
    list_settings_class = []
    for setting in list_settings_bool:
        if setting == 0:
            list_settings_class.append('off')
        elif setting == 1:
            list_settings_class.append('on')
    class_lights = list_settings_class[0]
    class_session = list_settings_class[1]

    return render_template('longboard.html', lat=lat, lng=lng, window_content=window_content, username=username, lights=class_lights, running=class_session)


def update_lights(user_ID):
    result = get_data('SELECT status_lights FROM tbl_users WHERE user_ID = %s;', user_ID)[0][0]

    for name, pin in light_pins.items():
        GPIO.output(pin, not result)

    set_data('UPDATE tbl_users ' 
             'SET status_lights = %s ' 
             'WHERE user_ID = %s;', (not result, user_ID))


@app.route('/<redirect_to>/toggle_lights')
def toggle(redirect_to):
    user_ID = session.get('user_ID')
    update_lights(user_ID)
    return redirect(redirect_to)


@app.route('/account', methods=['GET', 'POST'])
def account():
    user_ID = session.get('user_ID')
    username = get_username(user_ID)

    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        repeated_password = request.form['repeated_password']

        if not (username and new_password and repeated_password):
            flash("Fill in all the fields!", 'error')
        elif not (new_password == repeated_password):
            flash('Passwords do not match', 'error')
        elif new_password == current_password:
            flash('Pick a new password', 'error')
        else:
            record = get_data('SELECT password FROM tbl_users WHERE username = %s', username)
            password_correct = argon2.verify(current_password, record[0][0])
            if password_correct:
                argon_hash = argon2.hash(new_password)
                update_password(argon_hash, user_ID)
                flash('Password changed', 'success')
            else:
                flash('Old password is wrong', 'error')

    return render_template('account.html', username=username)


@app.errorhandler(500)
def internal_error(error):
    return redirect(url_for('index'))


@app.errorhandler(502)
def bad_gateway(error):
    return redirect(url_for('index'))


@app.errorhandler(400)
def bad_request(error):
    return redirect(url_for('index'))


@app.errorhandler(404)
def page_not_found(error):
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=False)
