import logging
from time import sleep, time
import mysql.connector as mysql

from datetime import datetime, timedelta
from pytz import timezone
from tzwhere import tzwhere
from gps import ultimateGPS
gpsModule = ultimateGPS()

log = logging.getLogger('output')
running = True

def get_data(sql, params=None):
    conn = mysql.connect(database='longboard_db', user='project-longboard', password='l0ngb0@rd')
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
    conn = mysql.connect(database='longboard_db', user='project-longboard', password='l0ngb0@rd')
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


def toggle_session_state(user_ID):
    result = get_data('SELECT session_running FROM tbl_users WHERE user_ID = %s;', user_ID)[0][0]

    set_data('UPDATE tbl_users ' 
             'SET session_running = %s ' 
             'WHERE user_ID = %s;', (not result, user_ID))
    return not result


def get_users():
    result = get_data('SELECT user_ID, username FROM tbl_users;')
    return result


def get_session_state_user(user_ID):
    result = optimize_list(get_data('SELECT session_running FROM tbl_users WHERE user_ID = %s ;', [user_ID]))[0]
    return result


def optimize_list(start_list):
    new_list = []
    for item in start_list:
        new_list.append(item[0])
    return new_list


def get_last_session(user_ID):
    result = get_data('SELECT session_ID, TIMESTAMPDIFF(MINUTE, start_date_time, stop_date_time), start_date_time '
                      'FROM tbl_sessions as session '
                      'WHERE user_ID = %s '
                      'ORDER BY session.session_ID DESC LIMIT 1;', user_ID)
    return result[0]


def create_session(start_datetime, user_ID, tag_ID):
    set_data('INSERT INTO tbl_sessions (start_date_time, user_ID, tag_ID) '
             'VALUES (%s, %s, %s);', (start_datetime, user_ID, tag_ID))

    return get_last_session(user_ID)[0]


def set_waypoint(session_ID, data):
    log.debug("Set waypoint: {}, {}, {}, {}, {}, {}".format(data['datetime'].time(), data['latitude'], data['longitude'], data['speed'], session_ID, data['altitude']))
    set_data('INSERT INTO tbl_waypoints(time , latitude, longitude, speed, session_ID, altitude) '
             'VALUES(%s, %s, %s, %s, %s, %s);',
             (data['datetime'].time(), data['latitude'], data['longitude'], data['speed'], session_ID, data['altitude']))


def get_timezone(datetime):
    utc_format  = "%Y-%m-%d %H:%M:%S %Z%z"
    now_utc_str = '2018-06-15 20:15:35 UTC+0000'
    now_utc     = datetime.strptime(now_utc_str, utc_format)
    print(now_utc)

    zone = tzwhere.tzwhere(forceTZ=True)
    local_tz = timezone(zone.tzNameAt(51.0894, 3.96788, forceTZ=True)) # match to the closest timezone -> forceTZ parameter

    # datetime_format = "%Y-%m-%d %H:%M:%S"
    # now_here = now_utc.astimezone(local_tz)
    # print(now_here.strftime(datetime_format))

    print(local_tz)


def set_session(user_ID):
    session_ID = None
    session_running = True

    print('_____________________CREATE NEW SESSION_____________________')
    # create session
    try:
        if not gpsModule.get_parsed_gps_data()['fix']:
            start_datetime = gpsModule.get_parsed_gps_data()['datetime']
            print("{}: {}".format(start_datetime))
            session_ID = create_session(start_datetime, user_ID)

            print("> Created session {}".format(session_ID))
        else:
            raise ValueError('No fix')
    except Exception as ex:
        log.exception(str(ex))

    # if the previous step didn't fail
    if not session_ID == None:
        # a limit of 50 times for testing
        lim = 50
        i = 0
        while session_running:
            # record waypoints
            try:
                if i < lim:
                    data = gpsModule.get_parsed_gps_data()
                    if data['valid']:
                        set_waypoint(session_ID, data)
                    i += 1
                    # wait until the user presses the button again
                    session_running = get_session_state_user(user_ID)
            except Exception as ex:
                log.exception(str(ex))
        # session stopped running -> end session
        print('_______________________END THE SESSION______________________')
        try:
            session_ID = get_last_session(user_ID)[0]
            print(session_ID)
            start_date = get_last_session(user_ID)[2].date()

            stop_date = start_date
            stop_time = get_last_waypoints_from_session(user_ID, session_ID)[2]
            print("Date: {}|{}  <> Time: {}|{}".format(stop_date, type(stop_date), stop_time, type(stop_time)))
            stop_datetime = str(stop_date) + " " + str(stop_time)

            print("Session stopped at {}".format(stop_datetime))
            set_data('UPDATE tbl_sessions '
                     'SET stop_date_time = %s'
                     'WHERE user_ID = %s AND session_ID = %s;', (stop_datetime, user_ID, session_ID))
        except Exception as ex:
            log.exception(str(ex))
    else:
        # if there is no fix. cancel the session
        toggle_session_state(user_ID)

def loop():
    for user in get_users():
        if get_session_state_user(user[0]):
            log.info('{} started a session.'.format(user[1]))
            print('{} started a session.'.format(user[1]))
            # user started a session on the website
            set_session(user[0])
    sleep(2)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    try:
        while running:
            loop()
    except KeyboardInterrupt:
        pass