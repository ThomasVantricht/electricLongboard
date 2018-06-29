from serial import Serial
from datetime import datetime, time

class ultimateGPS():

    def __init__(self, port="/dev/ttyS0", baudrate=9600, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout

    def __str__(self):
        return "Port: {0}; baudrate: {1}; timeout: {2}".format(self.port, self.baudrate, self.timeout)

    def flush_input(self):
        with Serial(self.port, self.baudrate, timeout=self.timeout) as serial:
            serial.read_all()

    def get_raw_gps_data(self):
        self.flush_input()
        gps_data_dic = {}                                                                                               # create dictionary for gps data

        try:
            with Serial(self.port, self.baudrate, timeout=self.timeout) as serial:
                line = str(serial.readline().rstrip()).split(",")                                                       # get the first string of gps data
                while line[0] != "b'$GPGGA" and line[0] != "b''":                                                       # wait for the right string
                    line = str(serial.readline().rstrip()).split(",")                                                   # create a list of the string
                    print(line)
                gps_data_dic["fix"] = line[6]                                                                           # get the fix
                gps_data_dic["altitude"] = line[9]                                                                      # and altitude from the list

                while line[0] != "b'$GPRMC" and line[0] != "b''":                                                       # wait for the right string
                    line = str(serial.readline().rstrip()).split(",")                                                   # create a list of the string
                    print(line)
                gps_data_dic["time"] = line[1]                                                                          # get the time
                gps_data_dic["valid"] = line[2]                                                                         # V -> data is Void (invalid) A -> GPS Active
                gps_data_dic["latitude"] = line[3]                                                                      # latitude
                gps_data_dic["direction_lat"] = line[4]                                                                 # direction latitude
                gps_data_dic["longitude"] = line[5]                                                                     # longitude
                gps_data_dic["direction_lng"] = line[6]                                                                 # direction longitude
                gps_data_dic["speed"] = line[7]                                                                         # speed
                gps_data_dic["date"] = line[9]                                                                          # date
        except Exception as ex:
            print(str(ex))
            gps_data_dic["valid"] = 0
            gps_data_dic["fix"] = 0

        return gps_data_dic                                                                                             # return the dictionary with raw gps data

    def get_parsed_gps_data(self):
        # get the raw data from the gps
        raw_data = self.get_raw_gps_data()
        parsed_data = {}                                                                                                # create an empty dictionary for parsed data

        try:
            # parse fix
            parsed_data["fix"] = int(raw_data["fix"])                                                                       # str to int
            # parse altitude
            parsed_data["altitude"] = float(raw_data["altitude"])                                                           # str to float
            # parse validation
            parsed_data["valid"] = ultimateGPS.check_validity(raw_data["valid"])                                            # char to boolean
            # parse latitude
            parsed_data["latitude"] = int(raw_data["latitude"][:2]) + float(raw_data["latitude"][2:])/60                    # DDMM.MMMM (The first two characters are the degrees)
            # parse latitude direction
            parsed_data["direction_lat"] = raw_data["direction_lat"]
            # add sign to latitude
            parsed_data["latitude"] = float(ultimateGPS.direction_to_sign(parsed_data["direction_lat"]) + str(parsed_data["latitude"]))
            # parse longitude
            parsed_data["longitude"] = int(raw_data["longitude"][:3]) + float(raw_data["longitude"][3:])/60                 # DDDMM.MMMM (The first three characters are the degrees)
            # parse latitude direction
            parsed_data["direction_lng"] = raw_data["direction_lng"]
            # add sign to longitude
            parsed_data["longitude"] = float(ultimateGPS.direction_to_sign(parsed_data["direction_lng"]) + str(parsed_data["longitude"]))
            # parse speed
            parsed_data["speed"] = float(raw_data["speed"])/1.852                                                           # str to float (knots -> kph)
            # parse date
            utc_date = raw_data["date"]                                                                                     # get the date string YYMMDD
            utc_date = utc_date[:len(utc_date)-2] + str(2000+int(utc_date[len(utc_date)-2:]))                               # convert to YYYYMMDD for datetime.date object
            utc_date = datetime.strptime(utc_date, '%d%m%Y').date()                                                         # convert the six numbers to a datetime.date object
            # parse time
            utc_time = raw_data["time"][:6]                                                                                 # get the first 6 numbers HHMMSS (skip the float part of the seconds)
            utc_time = datetime.strptime(utc_time, '%H%M%S').time()                                                         # convert the six numbers to a datetime.time object
            # create a datetime object
            parsed_data["datetime"] = datetime.strptime(str(utc_date) + str(utc_time), '%Y-%m-%d%H:%M:%S')
        except Exception as ex:
            print(str(ex))
            parsed_data["valid"] = 0
            parsed_data["fix"] = 0

        # return the dictionary of parsed data
        return parsed_data

    def get_current_location(self):
        parsed_data = self.get_parsed_gps_data()
        return (float(ultimateGPS.direction_to_sign(parsed_data["direction_lat"]) + str(parsed_data["latitude"]))), (float(ultimateGPS.direction_to_sign(parsed_data["direction_lng"]) + str(parsed_data["longitude"])))

    @staticmethod
    def check_validity(validation):                                                                                     # Returns a boolean instead of A / V
        valid = False
        if validation.lower() == "a":                                                                                   # A -> GPS Active :) else :(
            valid = True
        return valid

    @staticmethod
    def direction_to_sign(direction):                                                                                   # Returns a - or + instead of N / E / S / W
        sign = "-"                                                                                                      # S (South) = - | W (West)  = -
        if direction.lower() == "n" or direction.lower() == "e":                                                        # N (North) = + | E (East)  = +
            sign = "+"
        return sign