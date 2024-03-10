from astropy import coordinates as coord
from astropy import units as u
from astropy.time import Time
from datetime import datetime, timedelta, timezone
from flask import Flask, abort, request
from geopy.geocoders import Nominatim
import logging
import math
import re
import requests
import socket
from typing import Any, Optional, TypeVar
import xmltodict

ISS_TRAJECTORY_DATA_URL = 'https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml'
ISS_TRAJECTORY_DATA_DATETIME_FORMAT = '%Y-%jT%H:%M:%S.%fZ'
ISS_TRAJECTORY_DATA_DATETIME_REGEX = r"\d\d\d\d-\d\d\dT\d\d:\d\d:\d\d\.\d\d\dZ"

J2K_EPOCH = datetime(2000, 1, 1, 11, 58, 55, 816000, tzinfo=timezone.utc)
EARTH_ROTATION_RATE = 360.0 / ((23.0 * 60.0 * 60.0) + (56 * 60) + 4.0916) # deg/s

GEOCODER = Nominatim(user_agent='iss_tracker')

Header = dict[str, str|datetime]
Metadata = dict[str, str|datetime]
Comments = list[str]
Epoch = dict[str, Any]
"""
Epoch dict structure is as follows (float units are km or km/s).

timestamp: datetime
x: float
y: float
z: float
dx: float
dy: float
dz: float
"""
EpochList = list[Epoch]
T = TypeVar('T')
JsonResponse = dict[str, T]

class NASADataManager:
  datasource_url: str = ''
  header: Optional[Header] = None
  metadata: Optional[Metadata] = None
  comments: Optional[Comments] = None
  data: Optional[EpochList] = None
  data_timestamp: Optional[datetime] = None

  def __init__(self, url: str):
    """
    Initializes an instance of NASADataManager with the given data source URL
    """
    self.datasource_url = url

  def fetch_current_data(self) -> bool:
    """
    The exception-safe way to fetch current data
    Uses caching to maximize speed and minimize requests to NASA
    Returns False if the data is stale and unavailable
    Data is considered stale after 15 minutes.
    Otherwise returns True
    Data is stored in this object

    Returns:
      A boolean indicating if the data was fetched successfully
    """
    if self.data_timestamp is not None and self.data_timestamp > datetime.utcnow() - timedelta(minutes=15):
      return True
    try:
      self.header, self.metadata, self.comments, self.data = self._fetch_data()
      self.data_timestamp = datetime.utcnow()
      return True
    except Exception:
      self.header = None
      self.metadata = None
      self.comments = None
      self.data = None
      self.data_timestamp = None
      return False

  def _fetch_data(self) -> tuple[Header, Metadata, Comments, EpochList]:
    """
      Returns the formatted ISS tracker data

      Returns:
        result (tuple[Header, Metadata, Comments, EpochList]): A tuple of all data.
        See above for more information on specific data types.
      """
    response = requests.get(self.datasource_url)
    response.raise_for_status()
    data = xmltodict.parse(response.text)
    try:
      header: dict[str, str] = data['ndm']['oem']['header']
      metadata: dict[str, str] = data['ndm']['oem']['body']['segment']['metadata']
      # Below code converts timestamps to datetime objects when convenient
      for d in [header, metadata]:
        for k, v in d.items():
          if re.fullmatch(ISS_TRAJECTORY_DATA_DATETIME_REGEX, v):
            try:
              d[k] = datetime.strptime(v, ISS_TRAJECTORY_DATA_DATETIME_FORMAT)
            except Exception as e:
              logging.warning(e)

      comments = data['ndm']['oem']['body']['segment']['data']['COMMENT']
      state_vectors = data['ndm']['oem']['body']['segment']['data']['stateVector']
      formatted_epochs = [{
        'timestamp': datetime.strptime(s['EPOCH'], ISS_TRAJECTORY_DATA_DATETIME_FORMAT),
        'x': float(s['X']['#text']),
        'y': float(s['Y']['#text']),
        'z': float(s['Z']['#text']),
        'dx': float(s['X_DOT']['#text']),
        'dy': float(s['Y_DOT']['#text']),
        'dz': float(s['Z_DOT']['#text']),
      } for s in state_vectors]
      return (header, metadata, comments, formatted_epochs)
    except Exception as e:
      logging.error(e)
      raise ValueError('Invalid data format')

def get_most_current_epoch(data: EpochList) -> Epoch:
  """
  Takes the dataset and returns the entry that is closest to the current time
  This does not assume a chronologically sorted dataset

  Args:
    data (EpochList): The dataset
  Returns:
    entry (Epoch): The entry nearest the current time
  """
  current_time = datetime.utcnow().timestamp()
  lowest_delta = math.inf
  d_with_lowest_delta = None
  for d in data:
    delta = abs(current_time - d['timestamp'].timestamp())
    if delta < lowest_delta:
      d_with_lowest_delta = d
      lowest_delta = delta
  return d_with_lowest_delta

def speed(epoch: Epoch) -> float:
  """
  Calculates the velocity of the ISS at the given state entry

  Args:
    epoch (Epoch): The entry to calculate the ISS speed from
  Returns:
    result (float): The speed at that entry (km/s)
  """
  return math.sqrt(epoch['dx'] ** 2 + epoch['dy'] ** 2 + epoch['dz'] ** 2)

def astropy_lla_conversion(epoch: Epoch) -> tuple[float, float, float]:
  """
  Uses astropy to convert the xyz epoch coordinates to lla coordinates

  Agrs:
    epoch (Epoch): The entry to calculate the lla coordinates from
  Returns:
    result (tuple[float, float, float]): The lat, lon, and altitude in degrees and km
  """
  now = Time(epoch['timestamp'].isoformat(), scale='utc')
  gcrs = coord.GCRS(coord.CartesianRepresentation(epoch['x'], epoch['y'], epoch['z'], unit=u.km), obstime = now)
  itrs = gcrs.transform_to(coord.ITRS(obstime = now))
  loc = coord.EarthLocation(*itrs.cartesian.xyz)
  return (loc.lat.to_value(), loc.lon.to_value(), loc.height.to_value())

def fetch_location_str(lla: tuple[float, float, float]) -> str:
  """
  Takes the LLA coordinates and attempts to convert them to a meaningful location string, like a city
  Returns an empty string if unable to do so and logs a warning if an exception is thrown

  Args:
    lla (tuple[float, float, float]): The LLA coordinate to find a location string for
  Returns:
    result (str): The location string, if any, or an empty string
  """
  search_str = f'{lla[0]}, {lla[1]}'
  locstr = ''
  try:
    geoloc = GEOCODER.reverse(search_str, language='en', zoom=10)
    if geoloc is not None:
      if isinstance(geoloc.address, str):
        locstr = geoloc.address
      else: locstr = f'{geoloc.address.city}, {geoloc.address.municipality}, {geoloc.address.country}'
  except Exception as e:
    logging.warning(e)
    locstr = ''
  return locstr

def location(epoch: Epoch) -> tuple[float, float, float, str]:
  """
  Converts the XYZ position of the ISS to LLA coordinates
  Also returns a string described the city nearest to the ISS, if possible
  If a city near the ISS could not be identified, the location string will be empty ('')

  Args:
    epoch (Epoch): The entry to find the ISS LLA coordinates and then nearest city from
  Returns:
    result (tuple[float, float, float, str]): The lat, lon, altitude in degrees and km, and the string name of the nearest city
  """
  lla = astropy_lla_conversion(epoch)
  return (*lla, fetch_location_str(lla))

class App:
  app: Flask
  data_source: NASADataManager

  def __init__(self):
    self.app = Flask(__name__)
    self.data_source = NASADataManager(ISS_TRAJECTORY_DATA_URL)
    self.app.add_url_rule('/comment', view_func=self.comments)
    self.app.add_url_rule('/header', view_func=self.header)
    self.app.add_url_rule('/metadata', view_func=self.metadata)
    self.app.add_url_rule('/epochs', view_func=self.epochs)
    self.app.add_url_rule('/epochs/<epoch>', view_func=self.specific_epoch)
    self.app.add_url_rule('/epochs/<epoch>/speed', view_func=self.specific_epoch_speed)
    self.app.add_url_rule('/epochs/<epoch>/location', view_func=self.specific_epoch_location)
    self.app.add_url_rule('/now', view_func=self.now)

  def run(self):
    """
    Runs the flask app in debug mode on port 5173
    Args:
      None
    Returns:
      None
    """
    self.app.run(debug=True, host='0.0.0.0', port=5173)

  def get_data(self, data: str = 'epochs') -> Header|Metadata|Comments|EpochList:
    """
    Function for use in Flask route handlers that attempts to get current NASA data.
    Uses the data_source and throws an appropriate error if that is not possible.

    Args:
      data (str): Optional kwarg indiciating the request data. Defaults to 'epochs'.
        'epochs': result will be an EpochList
        'header': result will be a Header
        'metadata': result will be a Metadata
        'comments': result will be a Comments
        other: will raise a ValueError
    Returns:
      result (Header|Metadata|Comments|EpochList): The requested data, an EpochList by default.
    """
    if not self.data_source.fetch_current_data():
      abort(500, 'NASA data stale or unavilable. Please check the data source URL or try again later.')
    if data == 'epochs':
      return self.data_source.data
    elif data == 'header':
      return self.data_source.header
    elif data == 'metadata':
      return self.data_source.metadata
    elif data == 'comments':
      return self.data_source.comments
    raise ValueError("data keyword argument must be one of 'epochs', 'header', 'metadata', 'comments'")

  def comments(self) -> JsonResponse[Comments]:
    """
    Returns the list of comments from the NASA dataset.
    Error fetching or processing data results in a 500 Internal server error.

    Returns:
      result (JsonResponse[Comments]): {'comments': [the list of comments]}
    """
    comments = self.get_data(data='comments')
    return {'comments': comments}

  def header(self) -> JsonResponse[Header]:
    """
    Returns the header from the NASA dataset.
    Will format timestamp values to actual datetime objects, which will be transformed to human-readable strings in the JSON response
    Error fetching or processing data results in a 500 Internal server error.

    Returns:
      result (JsonResponse[Header]): {'header': the header}
    """
    header = self.get_data(data='header')
    return {'header': header}

  def metadata(self) -> JsonResponse[Metadata]:
    """
    Returns the metadata from the NASA dataset.
    Will format timestamp values to actual datetime objects, which will be transformed to human-readable strings in the JSON response
    Error fetching or processing data results in a 500 Internal server error.

    Returns:
      result (JsonResponse[Metadata]): {'metadata': the metadata}
    """
    metadata = self.get_data(data='metadata')
    return {'metadata': metadata}

  def epochs(self) -> JsonResponse[EpochList]:
    """
    Optional query params are 'limit' and 'offset'
    If provided, must be valid positive integers
    Offset defaults to zero
    Limit defaults to the entire set
    Invalid parameters result in a 400 Bad request.
    Error fetching or processing data results in a 500 Internal server error.

    Returns:
      result (JsonResponse[EpochList]): {'data': [the data entries as a list of dictionaries / JSON objects]}
    """
    limit = request.args.get('limit')
    offset = request.args.get('offset')
    if limit is not None and not limit.isnumeric():
      abort(400, 'Optional limit parameter must be a valid positive integer.')
    if offset is not None and not offset.isnumeric():
      abort(400, 'Optional offset parameter must be a valid nonnegative integer.')
    data = self.get_data()
    if offset is None:
      offset = 0
    else:
      offset = int(offset)
    if offset >= len(data):
      abort(400, 'Optional offset parameter must be less than the length of the dataset.')
    if limit is None:
      limit = len(data) - offset
    else:
      limit = int(limit)
    if limit == 0:
      abort(400, 'Optional limit parameter must be greater than zero.')
    offset_slice = data[offset:]
    limit_slice = offset_slice[0:limit]
    return {'data': limit_slice}

  def specific_epoch(self, epoch: str) -> JsonResponse[Optional[Epoch]]:
    """
    Returns the state vector for a specific epoch.
    Invalid parameters result in a 400 Bad request.
    Error fetching or processing data results in a 500 Internal server error.

    Args:
      epoch (str): A list index or timestamp matching an epoch in the dataset
    Returns:
      result (JsonResponse[Optional[Epoch]]): {'epoch': {the epoch dict / JSON object} or None}
    """
    data = self.get_data()
    if epoch.isnumeric():
      epoch = int(epoch)
      if epoch < len(data):
        return {'epoch': data[epoch]}
      else:
        abort(400, 'Enter an epoch index within the range of the dataset or an epoch timestamp included in the dataset.')
    else:
      timestamp = None
      try:
        timestamp = datetime.strptime(epoch, ISS_TRAJECTORY_DATA_DATETIME_FORMAT)
      except Exception:
        abort(400, 'Enter an epoch index within the range of the dataset or an epoch timestamp included in the dataset.')
      search_results = [e for e in data if e['timestamp'].timestamp() == timestamp.timestamp()]
      if len(search_results) == 0:
        return {'epoch': None}
      if len(search_results) == 1:
        return {'epoch': search_results[0]}
      abort(500, 'Multiple state vectors found for the specified timestamp.')

  def specific_epoch_speed(self, epoch) -> JsonResponse[float]:
    """
    Returns the speed of the specified epoch.
    Epoch specification details are as described in specific_epoch.
    Invalid parameters result in a 400 Bad request.
    Error fetching or processing data results in a 500 Internal server error.

    Args:
      epoch (str): A list index or timestamp matching an epoch in the dataset
    Returns:
      result (JsonResponse[float]): {'speed': the speed of the ISS at the specified epoch}
    """
    epoch = self.specific_epoch(epoch)
    if epoch['epoch'] is None:
      abort(400, 'Specified epoch does not exist.')
    return {'speed': speed(epoch['epoch'])}

  def specific_epoch_location(self, epoch) -> JsonResponse[float]:
    """
    Returns the location of the specified epoch.
    Epoch specification details are as described in specific_epoch.
    Invalid parameters result in a 400 Bad request.
    Error fetching or processing data results in a 500 Internal server error.

    Args:
      epoch (str): A list index or timestamp matching an epoch in the dataset
    Returns:
      result (JsonResponse[float]): {
        'lat': the geodetic latitude of the ISS in degrees,
        'lon': the geodetic longitude of the ISS in degrees,
        'altitude': the altitude of the ISS in km,
        'locstr': the city nearest the ISS (if identifiable, otherwise empty string),
      }
    """
    epoch = self.specific_epoch(epoch)
    if epoch['epoch'] is None:
      abort(400, 'Specified epoch does not exist.')
    loc = location(epoch['epoch'])
    return {'lat': loc[0], 'lon': loc[1], 'altitude': loc[2], 'locstr': loc[3]}

  def now(self) -> Epoch:
    """
    Returns the most current epoch of the ISS and its speed and location.
    Error fetching or processing data results in a 500 Internal server error.

    Returns:
      result (Epoch): {'epoch': the current epoch dict/JSON object, 'speed' (float): the current ISS speed, 'location': the current location of the ISS in LLA coordinates}
    """
    data = self.get_data()
    current = get_most_current_epoch(data)
    loc = location(current)
    return {
      'epoch': current,
      'speed': speed(current),
      'location': {
        'lat': loc[0],
        'lon': loc[1],
        'altitude': loc[2],
        'locstr': loc[3]
      },
    }

if __name__ == '__main__':
  logging.basicConfig(format=f'[%(asctime)s {socket.gethostname()}] %(filename)s:%(funcName)s:%(lineno)s - %(levelname)s: %(message)s')
  App().run()