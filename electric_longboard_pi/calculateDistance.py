import math
# test pi
def distanceBetweenCoordinates(point_a, point_b):
    lat_a, lon_a = point_a
    lat_b, lon_b = point_b
    earthRadius = 6371                                       # earth Radius km

    distance_lat = math.radians(lat_b-lat_a)
    distance_lon = math.radians(lon_b-lon_a)
    a = math.sin(distance_lat/2) * math.sin(distance_lat/2) + math.cos(math.radians(lat_a)) * math.cos(math.radians(lat_b)) * math.sin(distance_lon/2) * math.sin(distance_lon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    d = earthRadius * c
    return d

def totalDistance(list_coordinates):
    list_lat = []
    list_lng = []

    for coordinate in list_coordinates:
        list_lat.append(coordinate[0])
        list_lng.append(coordinate[1])

    total_distance = 0
    for i in range(len(list_coordinates)-1):
        distance = distanceBetweenCoordinates((list_lat[i], list_lng[i]), (list_lat[i+1], list_lng[i+1]))
        total_distance += distance

    return round(total_distance, 2)
