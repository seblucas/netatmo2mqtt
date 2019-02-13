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
COMMAND_LINE_KEYS = {
  'temp': { 'mqttKey': 'temp', 'netatmoKey': 'therm_measured_temperature' },
  'setpoint': { 'mqttKey': 'temp', 'netatmoKey': 'therm_setpoint_temperature' },
  'boiler': { 'mqttKey': 'boiler', 'netatmoKey': '' },
  'battery': { 'mqttKey': 'battery', 'netatmoKey': '' }
}


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
      return (False, {"time": tstamp, "message": "NetAtmo error while refreshing access token"})
    return (True, data['access_token'])
  except requests.exceptions.RequestException as e:
    return (False, {"time": tstamp, "message": "NetAtmo not available : " + str(e)})

def getNetAtmoThermostat(naClientId, naClientSecret, naRefreshToken):
  tstamp = int(time.time())
  status, accessToken = getNetAtmoAccessToken(naClientId, naClientSecret, naRefreshToken)
  if not status:
      return (False, accessToken, {})
  headers = {"Authorization":"Bearer " + accessToken}
  try:
    r = requests.get(NETATMO_HOMESDATA_URL, headers=headers)
    data = r.json()
    if r.status_code != 200 or not 'homes' in data['body'] or not 'modules' in data['body']['homes'][0]:
      debug ("NetAtmo error while reading homesdata response {0}".format(json.dumps(data)))
      return (False, {"time": tstamp, "message": "Netatmo data not well formed"})
    res = requests.get(NETATMO_HOMESTATUS_URL, headers=headers, params={ 'home_id': data['body']['homes'][0]['id'] })
    homeData = res.json()
    if res.status_code != 200 or not 'home' in homeData['body'] or not 'rooms' in homeData['body']['home']:
      debug ("NetAtmo error while reading homestatus response {0}".format(json.dumps(data)))
      return (False, {"time": tstamp, "message": "Netatmo data not well formed"})
    result = {}
    for topicParam in args.topics:
      key = topicParam.split(';')[0]
      topic = topicParam.split(';')[1]
      if not (topic in result):
        result[topic] = { "time": tstamp }
      if key in COMMAND_LINE_KEYS:
        dataKey = COMMAND_LINE_KEYS[key]['mqttKey']
        result[topic][dataKey] = homeData['body']['home']['rooms'][0][COMMAND_LINE_KEYS[key]['netatmoKey']]

    return (status, result)
  except requests.exceptions.RequestException as e:
    return (False, {"time": tstamp, "message": "NetAtmo not available : " + str(e)})


parser = argparse.ArgumentParser(description='Read current temperature and setpoint from NetAtmo API and send them to a MQTT broker.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('-a', '--client-secret', dest='naClientSecret', action="store", help='NetAtmo Client Secret / Can also be read from NETATMO_CLIENT_SECRET env var.',
                   **environ_or_required('NETATMO_CLIENT_SECRET'))
parser.add_argument('-c', '--client-id', dest='naClientId', action="store", help='NetAtmo Client ID / Can also be read from NETATMO_CLIENT_ID en var.',
                   **environ_or_required('NETATMO_CLIENT_ID'))
parser.add_argument('-r', '--refresh-token', dest='naRefreshToken', action="store", help='NetAtmo Refresh Token / Can also be read from NETATMO_REFRESH_TOKEN en var.',
                   **environ_or_required('NETATMO_REFRESH_TOKEN'))
parser.add_argument('-m', '--mqtt-host', dest='host', action="store", default="127.0.0.1",
                   help='Specify the MQTT host to connect to.')
parser.add_argument('-n', '--dry-run', dest='dryRun', action="store_true", default=False,
                   help='No data will be sent to the MQTT broker.')
parser.add_argument('-s', '--topic-setpoint', dest='topicSetpoint', action="store", default="sensor/setpoint", metavar="TOPIC",
                   help='The MQTT topic on which to publish the message with the current setpoint temperature (if it was a success)')
parser.add_argument('-t', '--topic', dest='topics', action="append",
                   help='The information to send and the MQTT topic on which to publish the message (if it was a success) separated by a ;. Can be call many time')
parser.add_argument('-T', '--topic-error', dest='topicError', action="store", default="error/sensor/mainroom", metavar="TOPIC",
                   help='The MQTT topic on which to publish the message (if it wasn\'t a success).')
parser.add_argument('-v', '--verbose', dest='verbose', action="store_true", default=False,
                   help='Enable debug messages.')


args = parser.parse_args()
verbose = args.verbose

status, result = getNetAtmoThermostat(args.naClientId, args.naClientSecret, args.naRefreshToken)

if status:
  for mqttTopic in result.keys():
    mqttMessage = result[mqttTopic]
    jsonString = json.dumps(mqttMessage)
    debug("Success with message (for {0}) <{1}>".format(mqttTopic, jsonString))

    if not args.dryRun:
      publish.single(mqttTopic, jsonString, hostname=args.host)
else:
  jsonString = json.dumps(result)
  debug("Failure with message <{0}>".format(jsonString))
  if not args.dryRun:
    publish.single(args.topicError, jsonString, hostname=args.host)

