#!/usr/bin/env python3
#
#  netatmo2MQTT.py
#
#  Copyright 2017 Sébastien Lucas <sebastien@slucas.fr>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#


import os, re, time, json, argparse
import requests                     # pip install requests
import paho.mqtt.publish as publish # pip install paho-mqtt

verbose = False
NETATMO_GETTHERMOSTATDATA_URL = 'https://api.netatmo.com/api/getthermostatsdata?access_token={0}'
NETATMO_OAUTH_URL = 'https://api.netatmo.com/oauth2/token';
NETATMO_GETMEASURE_URL = 'https://api.netatmo.com/api/getmeasure';

def debug(msg):
  if verbose:
    print (msg + "\n")

def getNetAtmoAccessToken(naClientId, naClientSecret, naRefreshToken):
  tstamp = int(time.time())
  payload = {
    'grant_type': 'refresh_token',
    'refresh_token': naRefreshToken,
    'client_id': naClientId,
    'client_secret': naClientSecret
  }
  headers = {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
  try:
    r = requests.post(NETATMO_OAUTH_URL, data=payload, headers=headers)
    data = r.json()
    if r.status_code != 200 or not 'access_token' in data:
      debug ("NetAtmo error while refreshing access token {0}".format(json.dumps(data)))
      return (False, {"time": tstamp, "message": "NetAtmo error while refreshing access token"})
    return (True, data['access_token'])
  except requests.exceptions.RequestException as e:
    return (False, {"time": tstamp, "message": "NetAtmo not available : " + str(e)})

def getNetAtmoThermostatMeasure(oldTimestamp, newTimestamp, accessToken, deviceId, moduleId):
  params = {
    'access_token': accessToken,
    'device_id'   : deviceId,
    'module_id'   : moduleId,
    'scale'       : 'max',
    'type'        : 'temperature,sp_temperature,boileron',
    'date_begin'  : oldTimestamp + 1,
    'date_end'    : newTimestamp
  }
  try:
    r = requests.get(NETATMO_GETMEASURE_URL, params=params)
    data = r.json()
    if r.status_code != 200:
      return (False, {"time": tstamp, "message": "NetAtmo error while getting all measures"})
    temperatureList = []
    setpointList = []
    for measure in data['body']:
      temperatureList.append({'time': measure['beg_time'], 'temp': measure['value'][0][0]})
      setpointList.append({'time': measure['beg_time'], 'temp': measure['value'][0][1]})
    return (True, temperatureList, setpointList)
  except requests.exceptions.RequestException as e:
    return (False, {"time": tstamp, "message": "NetAtmo not available : " + str(e)}, {})


def getNetAtmoThermostat(oldTimestamp, naClientId, naClientSecret, naRefreshToken):
  tstamp = int(time.time())
  status, accessToken = getNetAtmoAccessToken(naClientId, naClientSecret, naRefreshToken)
  if not status:
      return (False, accessToken, {})
  naUrl = NETATMO_GETTHERMOSTATDATA_URL.format(accessToken)
  debug ("Trying to get data from {0}".format(naUrl))
  try:
    r = requests.get(naUrl)
    data = r.json()
    if r.status_code != 200 or not 'devices' in data['body'] or not 'modules' in data['body']['devices'][0]:
      debug ("NetAtmo error while reading thermostat response {0}".format(json.dumps(data)))
      return (False, {"time": tstamp, "message": "OpenWeatherMap data not well formed"}, {})
    latestTime = int(data['body']['devices'][0]['modules'][0]['measured']['time'])
    newObject = [{"time": latestTime,
                 "temp": data['body']['devices'][0]['modules'][0]['measured']['temperature']}]
    setpointObject = [{"time": latestTime,
                 "temp": data['body']['devices'][0]['modules'][0]['measured']['setpoint_temp']}]
    if oldTimestamp > 0 and oldTimestamp < latestTime:
      status, temperatureList, setpointList = getNetAtmoThermostatMeasure(oldTimestamp, latestTime, accessToken,
        data['body']['devices'][0]['_id'], data['body']['devices'][0]['modules'][0]['_id'])
      if status:
        return (True, temperatureList, setpointList)
    return (True, newObject, setpointObject)
  except requests.exceptions.RequestException as e:
    return (False, {"time": tstamp, "message": "NetAtmo not available : " + str(e)}, {})


parser = argparse.ArgumentParser(description='Read current temperature and setpoint from NetAtmo API and send them to a MQTT broker.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-a', '--client-secret', dest='naClientSecret', action="store", required=True,
                   help='NetAtmo Client Secret.')
parser.add_argument('-c', '--client-id', dest='naClientId', action="store", required=True,
                   help='NetAtmo Client ID.')
parser.add_argument('-r', '--refresh-token', dest='naRefreshToken', action="store", required=True,
                   help='NetAtmo Refresh Token.')
parser.add_argument('-m', '--mqtt-host', dest='host', action="store", default="127.0.0.1",
                   help='Specify the MQTT host to connect to.')
parser.add_argument('-n', '--dry-run', dest='dryRun', action="store_true", default=False,
                   help='No data will be sent to the MQTT broker.')
parser.add_argument('-o', '--last-time', dest='previousFilename', action="store", default="/tmp/netatmo_last",
                   help='The file where the last timestamp coming from NetAtmo API will be saved')
parser.add_argument('-s', '--topic-setpoint', dest='topicSetpoint', action="store", default="sensor/setpoint", metavar="TOPIC",
                   help='The MQTT topic on which to publish the message with the current setpoint temperature (if it was a success)')
parser.add_argument('-t', '--topic', dest='topic', action="store", default="sensor/mainroom",
                   help='The MQTT topic on which to publish the message (if it was a success).')
parser.add_argument('-T', '--topic-error', dest='topicError', action="store", default="error/sensor/mainroom", metavar="TOPIC",
                   help='The MQTT topic on which to publish the message (if it wasn\'t a success).')
parser.add_argument('-v', '--verbose', dest='verbose', action="store_true", default=False,
                   help='Enable debug messages.')


args = parser.parse_args()
verbose = args.verbose;

oldTimestamp = 0
if os.path.isfile(args.previousFilename):
  oldTimestamp = int(open(args.previousFilename).read(10));


status, dataArray, dataSetpointArray = getNetAtmoThermostat(oldTimestamp, args.naClientId, args.naClientSecret, args.naRefreshToken)

if status:
  for data, dataSetpoint in zip(dataArray, dataSetpointArray):
    jsonString = json.dumps(data)
    jsonStringSetpoint = json.dumps(dataSetpoint)
    debug("Success with message (for current temperature) <{0}>".format(jsonString))
    debug("Success with message (for setpoint temperature) <{0}>".format(jsonStringSetpoint))

    if oldTimestamp >= data["time"]:
      print ("No new data found")
      exit(0)

    # save the last timestamp in a file
    with open(args.previousFilename, 'w') as f:
      f.write(str(data["time"]))
    if not args.dryRun:
      publish.single(args.topic, jsonString, hostname=args.host)
      publish.single(args.topicSetpoint, jsonStringSetpoint, hostname=args.host)
    time.sleep(1)
else:
  jsonString = json.dumps(dataArray)
  debug("Failure with message <{0}>".format(jsonString))
  if not args.dryRun:
    publish.single(args.topicError, jsonString, hostname=args.host)

