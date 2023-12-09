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
NETATMO_BASE_URL = 'https://api.netatmo.com/api'
NETATMO_HOMESDATA_URL = NETATMO_BASE_URL + '/homesdata'
NETATMO_HOMESTATUS_URL = NETATMO_BASE_URL + '/homestatus'
NETATMO_OAUTH_URL = 'https://api.netatmo.com/oauth2/token'
NETATMO_GETMEASURE_URL = NETATMO_BASE_URL + '/getmeasure'

def debug(msg):
  if verbose:
    print (msg + "\n")

def environ_or_required(key):
  if os.environ.get(key):
      return {'default': os.environ.get(key)}
  else:
      return {'required': True}

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
      return (False, {"time": tstamp, "message": "NetAtmo error while refreshing access token"}, '')
    return (True, data['access_token'], data['refresh_token'])
  except requests.exceptions.RequestException as e:
    return (False, {"time": tstamp, "message": "NetAtmo not available : " + str(e)}, '')

def getNetAtmoThermostatMeasure(oldTimestamp, newTimestamp, accessToken, deviceId, moduleId, tstamp):
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
    if len(data['body']) == 0:
      return (True, temperatureList, setpointList)
    for measure in data['body']:
      temperatureList.append({'time': measure['beg_time'], 'temp': measure['value'][0][0]})
      setpointList.append({'time': measure['beg_time'], 'temp': measure['value'][0][1]})
    return (True, temperatureList, setpointList)
  except requests.exceptions.RequestException as e:
    return (False, {"time": tstamp, "message": "NetAtmo not available : " + str(e)}, {})


def getNetAtmoThermostat(oldTimestamp, naClientId, naClientSecret, naRefreshToken):
  tstamp = int(time.time())
  status, accessToken, refreshToken = getNetAtmoAccessToken(naClientId, naClientSecret, naRefreshToken)
  if not status:
      return (False, refreshToken, {"time": tstamp, "message": "Unable to get access token from NetAtmo" },  {})
  headers = {"Authorization":"Bearer " + accessToken}
  try:
    r = requests.get(NETATMO_HOMESDATA_URL, headers=headers)
    data = r.json()
    if r.status_code != 200 or not 'homes' in data['body'] or not 'modules' in data['body']['homes'][0]:
      debug ("NetAtmo error while reading thermostat response {0}".format(json.dumps(data)))
      return (False, refreshToken, {"time": tstamp, "message": "Netatmo data not well formed"}, {})
    status, temperatureList, setpointList = getNetAtmoThermostatMeasure(oldTimestamp, tstamp, accessToken,
      data['body']['homes'][0]['modules'][0]['id'], data['body']['homes'][0]['modules'][1]['id'], tstamp)
    return (status, refreshToken, temperatureList, setpointList)
  except requests.exceptions.RequestException as e:
    return (False, refreshToken, {"time": tstamp, "message": "NetAtmo not available : " + str(e)}, {})


parser = argparse.ArgumentParser(description='Read current temperature and setpoint from NetAtmo API and send them to a MQTT broker.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-a', '--client-secret', dest='naClientSecret', action="store", help='NetAtmo Client Secret / Can also be read from NETATMO_CLIENT_SECRET env var.',
                   **environ_or_required('NETATMO_CLIENT_SECRET'))
parser.add_argument('-c', '--client-id', dest='naClientId', action="store", help='NetAtmo Client ID / Can also be read from NETATMO_CLIENT_ID en var.',
                   **environ_or_required('NETATMO_CLIENT_ID'))
parser.add_argument('-r', '--refresh-token', dest='naRefreshToken', action="store", help='NetAtmo Refresh Token / Can also be read from NETATMO_REFRESH_TOKEN en var.',
                   **environ_or_required('NETATMO_REFRESH_TOKEN'))
parser.add_argument('-l', '--latest', dest='latestReadingUrl', action="store", help='Url with latest reading timestamp already stored.',
                   **environ_or_required('TIMESTAMP_URL'))
parser.add_argument('-x', '--regex', dest='latestReadingRegex', action="store", help='Regular expression to get latest reading time from url.',
                   **environ_or_required('TIMESTAMP_REGEX'))
parser.add_argument('-m', '--mqtt-host', dest='host', action="store", default="127.0.0.1",
                   help='Specify the MQTT host to connect to.')
parser.add_argument('-n', '--dry-run', dest='dryRun', action="store_true", default=False,
                   help='No data will be sent to the MQTT broker.')
parser.add_argument('-o', '--last-time', dest='previousFilename', action="store", default="/tmp/netatmo_last",
                   help='The file where the last timestamp coming from NetAtmo API will be saved')
parser.add_argument('-u', '--updated-refresh', dest='updatedRefreshFilename', action="store", default="/tmp/netatmo_last_refresh",
                   help='The file where the last refresh token coming from NetAtmo API will be saved')
parser.add_argument('-s', '--topic-setpoint', dest='topicSetpoint', action="store", default="sensor/setpoint", metavar="TOPIC",
                   help='The MQTT topic on which to publish the message with the current setpoint temperature (if it was a success)')
parser.add_argument('-t', '--topic', dest='topic', action="store", default="sensor/mainroom",
                   help='The MQTT topic on which to publish the message (if it was a success).')
parser.add_argument('-T', '--topic-error', dest='topicError', action="store", default="error/sensor/mainroom", metavar="TOPIC",
                   help='The MQTT topic on which to publish the message (if it wasn\'t a success).')
parser.add_argument('-v', '--verbose', dest='verbose', action="store_true", default=False,
                   help='Enable debug messages.')


args = parser.parse_args()
verbose = args.verbose

oldTimestamp = 0
if os.path.isfile(args.previousFilename):
  with open(args.previousFilename, 'r') as f:
    oldTimestamp = int(f.read(10))
  debug("Found last reading from file <{0}>".format(oldTimestamp))
else:
  if args.latestReadingUrl:
    r = requests.get(args.latestReadingUrl)
    if args.latestReadingRegex:
      m = re.search(args.latestReadingRegex, r.text)
      if m:
        oldTimestamp = int(m.group(1))
        debug("Found last reading from url with regex <{0}>".format(oldTimestamp))
    else:
      oldTimestamp = int(r.text)
      debug("Found last reading from url <{0}>".format(oldTimestamp))
      
if oldTimestamp == 0:
  print("No old timestamp given exiting")
  exit(0)

if os.path.isfile(args.updatedRefreshFilename):
  with open(args.updatedRefreshFilename, 'r') as f:
    args.naRefreshToken = f.read()

status, updatedRefreshToken, dataArray, dataSetpointArray = getNetAtmoThermostat(oldTimestamp, args.naClientId, args.naClientSecret, args.naRefreshToken)

if updatedRefreshToken:
  with open(args.updatedRefreshFilename, 'w') as f:
      f.write(updatedRefreshToken)

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
    time.sleep(0.5)
else:
  jsonString = json.dumps(dataArray)
  debug("Failure with message <{0}>".format(jsonString))
  if not args.dryRun:
    publish.single(args.topicError, jsonString, hostname=args.host)

