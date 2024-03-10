from datetime import datetime, timedelta, timezone
from flask import Flask
from .. import iss_tracker as it
import math
import pytest
import random
from unittest.mock import patch, Mock

def gen_random_formatted_data_entry(timestamp: datetime | None = None):
  # Next four lines generate a random UTC timezone within two weeks of now
  # This is a similar date to what we'll be getting back from the API
  # Which is why it's used for testing purposes
  if timestamp is None:
    now = datetime.utcnow()
    two_weeks_ago = now - timedelta(days = 14)
    two_weeks_ahead = now + timedelta(days = 14)
    timestamp = datetime.fromtimestamp(random.uniform(two_weeks_ago.timestamp(), two_weeks_ahead.timestamp()), timezone.utc)
  return {
    'timestamp': timestamp,
    'x': random.uniform(-10000.0, 10000.0),
    'y': random.uniform(-10000.0, 10000.0),
    'z': random.uniform(-10000.0, 10000.0),
    'dx': random.uniform(-10000.0, 10000.0),
    'dy': random.uniform(-10000.0, 10000.0),
    'dz': random.uniform(-10000.0, 10000.0),
  }

def gen_random_lla_coords():
  return (random.uniform(-90.0, 90.0), random.uniform(-180.0, 180.0), random.uniform(400, 500))

class TestNASADatamanager:
  def test_init(self):
    instance = it.NASADataManager('fakeurl')
    assert instance.header == None
    assert instance.metadata == None
    assert instance.comments == None
    assert instance.data == None
    assert instance.data_timestamp == None
    assert instance.datasource_url == 'fakeurl'

  @patch.object(it.NASADataManager, '_fetch_data')
  def test_fetch_current_data_on_fresh_instance(self, mock_fetch_data):
    instance = it.NASADataManager('fakeurl')
    mock_fetch_data.return_value = ({}, {}, [], [])
    assert instance.fetch_current_data()
    mock_fetch_data.assert_called_once()
    assert instance.header == {}
    assert instance.metadata == {}
    assert instance.comments == []
    assert instance.data == []
    assert round(instance.data_timestamp.timestamp()) == round(datetime.utcnow().timestamp())

  @patch.object(it.NASADataManager, '_fetch_data', side_effect=Exception())
  def test_fetch_current_data_err_on_fresh_instance(self, mock_fetch_data):
    instance = it.NASADataManager('fakeurl')
    # Next 5 data properties are set just so we can properly test that they're set back to None later
    instance.header = {}
    instance.metadata = {}
    instance.comments = []
    instance.data = []
    instance.data_timestamp = datetime.utcnow() - timedelta(days=2)
    assert not instance.fetch_current_data()
    mock_fetch_data.assert_called_once()
    assert instance.header is None
    assert instance.metadata is None
    assert instance.comments is None
    assert instance.data is None
    assert instance.data_timestamp is None

  @patch.object(it.NASADataManager, '_fetch_data')
  def test_fetch_current_data_with_fresh_cached_data(self, mock_fetch_data):
    instance = it.NASADataManager('anyurl')
    instance.header = {}
    instance.metadata = {}
    instance.comments = []
    instance.data = []
    instance.data_timestamp = datetime.utcnow() - timedelta(minutes=1)
    assert instance.fetch_current_data()
    mock_fetch_data.assert_not_called()
    assert instance.header == {}
    assert instance.metadata == {}
    assert instance.comments == []
    assert instance.data == []
    assert round(instance.data_timestamp.timestamp()) == round((datetime.utcnow() - timedelta(minutes=1)).timestamp())

  @patch.object(it.NASADataManager, '_fetch_data')
  def test_fetch_current_data_with_stale_cached_data(self, mock_fetch_data):
    instance = it.NASADataManager('anyurl')
    mock_fetch_data.return_value = ({'header': ''}, {'metadata': ''}, ['comment'], [0])
    instance.header = {}
    instance.metadata = {}
    instance.comments = []
    instance.data = []
    instance.data_timestamp = datetime.utcnow() - timedelta(minutes = 15)
    assert instance.fetch_current_data()
    mock_fetch_data.assert_called_once()
    assert instance.header == {'header': ''}
    assert instance.metadata == {'metadata': ''}
    assert instance.comments == ['comment']
    assert instance.data == [0]
    assert round(instance.data_timestamp.timestamp()) == round(datetime.utcnow().timestamp())

  @patch('requests.get')
  def test_fetch_data_makes_request_to_given_url(self, mock_get):
    mock_response = Mock()
    mock_get.return_value = mock_response
    mockurl = 'anyurl'
    instance = it.NASADataManager('anyurl')
    try:
      instance._fetch_data()
    except Exception:
      pass
    mock_get.assert_called_once_with(mockurl)

  @patch('requests.get')
  def test_fetch_data_calls_raise_for_status(self, mock_get):
    mock_response = Mock()
    mock_get.return_value = mock_response
    instance = it.NASADataManager('anyurl')
    with pytest.raises(Exception):
      instance._fetch_data()
    mock_response.raise_for_status.assert_called_once()

  @patch('requests.get')
  def test_fetch_data_throws_on_bad_response_data(self, mock_get):
    mock_response = Mock()
    mock_response.text = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><ndm></ndm>'
    mock_get.return_value = mock_response
    instance = it.NASADataManager('anyurl')
    with pytest.raises(ValueError, match='Invalid data format'):
      instance._fetch_data()

  @patch('requests.get')
  def test_fetch_data_returns_formatted_data(self, mock_get):
    mock_response = Mock()
    mock_response.text = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><ndm><oem>\
      <header>\
        <CREATION_DATE>2024-064T19:05:34.727Z</CREATION_DATE>\
        <ORIGINATOR>JSC</ORIGINATOR>\
      </header>\
      <body><segment>\
      <metadata>\
        <OBJECT_NAME>ISS</OBJECT_NAME>\
        <OBJECT_ID>1998-067-A</OBJECT_ID>\
        <CENTER_NAME>EARTH</CENTER_NAME>\
        <REF_FRAME>EME2000</REF_FRAME>\
        <TIME_SYSTEM>UTC</TIME_SYSTEM>\
        <START_TIME>2024-064T12:00:00.000Z</START_TIME>\
        <STOP_TIME>2024-079T12:00:00.000Z</STOP_TIME>\
      </metadata>\
      <data>\
      <COMMENT>Units are in kg and m^2</COMMENT>\
      <COMMENT>MASS=459325.00</COMMENT>\
      <COMMENT>DRAG_AREA=1487.80</COMMENT>\
      <COMMENT>DRAG_COEFF=1.85</COMMENT>\
      <COMMENT>SOLAR_RAD_AREA=0.00</COMMENT>\
      <COMMENT>SOLAR_RAD_COEFF=0.00</COMMENT>\
      <COMMENT>Orbits start at the ascending node epoch </COMMENT>\
      <stateVector>\
        <EPOCH>2024-060T11:53:00.000Z</EPOCH>\
        <X units="km">5399.1704782229899</X>\
        <Y units="km">-1108.14023003495</Y>\
        <Z units="km">-3980.4555898630201</Z>\
        <X_DOT units="km/s">-1.6589832535062301</X_DOT>\
        <Y_DOT units="km/s">6.3102478214519504</Y_DOT>\
        <Z_DOT units="km/s">-4.0034893268315699</Z_DOT>\
      </stateVector>\
      <stateVector>\
          <EPOCH>2024-060T11:57:00.000Z</EPOCH>\
          <X units="km">4810.0613297217697</X>\
          <Y units="km">428.155064046794</Y>\
          <Z units="km">-4784.8762745587901</Z>\
          <X_DOT units="km/s">-3.22016304143997</X_DOT>\
          <Y_DOT units="km/s">6.41427044296627</Y_DOT>\
          <Z_DOT units="km/s">-2.6592811018523501</Z_DOT>\
      </stateVector>\
      <stateVector>\
          <EPOCH>2024-060T12:00:00.000Z</EPOCH>\
          <X units="km">4136.0805510027503</X>\
          <Y units="km">1566.0982121356899</Y>\
          <Z units="km">-5162.2032212831</Z>\
          <X_DOT units="km/s">-4.2428405608606701</X_DOT>\
          <Y_DOT units="km/s">6.1863115386258203</Y_DOT>\
          <Z_DOT units="km/s">-1.5189259191498701</Z_DOT>\
      </stateVector></data></segment></body></oem></ndm>'
    mock_get.return_value = mock_response
    instance = it.NASADataManager('anyurl')
    result = instance._fetch_data()
    assert result == (
      {
        'CREATION_DATE': datetime.strptime('2024-064T19:05:34.727Z', it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT),
        'ORIGINATOR': 'JSC'
      },
      {
        'OBJECT_NAME': 'ISS',
        'OBJECT_ID': '1998-067-A',
        'CENTER_NAME': 'EARTH',
        'REF_FRAME': 'EME2000',
        'TIME_SYSTEM': 'UTC',
        'START_TIME': datetime.strptime('2024-064T12:00:00.000Z', it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT),
        'STOP_TIME': datetime.strptime('2024-079T12:00:00.000Z', it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT),
      },
      [
        'Units are in kg and m^2',
        'MASS=459325.00',
        'DRAG_AREA=1487.80',
        'DRAG_COEFF=1.85',
        'SOLAR_RAD_AREA=0.00',
        'SOLAR_RAD_COEFF=0.00',
        'Orbits start at the ascending node epoch',
      ],
      [
        {
          'timestamp': datetime.strptime('2024-060T11:53:00.000Z', it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT),
          'x': 5399.1704782229899,
          'y': -1108.14023003495,
          'z': -3980.4555898630201,
          'dx': -1.6589832535062301,
          'dy': 6.3102478214519504,
          'dz': -4.0034893268315699,
        },
        {
          'timestamp': datetime.strptime('2024-060T11:57:00.000Z', it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT),
          'x': 4810.0613297217697,
          'y': 428.155064046794,
          'z': -4784.8762745587901,
          'dx': -3.22016304143997,
          'dy': 6.41427044296627,
          'dz': -2.6592811018523501,
        },
        {
          'timestamp': datetime.strptime('2024-060T12:00:00.000Z', it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT),
          'x': 4136.0805510027503,
          'y': 1566.0982121356899,
          'z': -5162.2032212831,
          'dx': -4.2428405608606701,
          'dy': 6.1863115386258203,
          'dz': -1.5189259191498701,
        },
      ],
    )

def test_get_most_current_epoch():
  mock_entries = [gen_random_formatted_data_entry() for _ in range(10)]
  rand_entry = random.choice(mock_entries)
  rand_entry['timestamp'] = datetime.utcnow()
  assert it.get_most_current_epoch(mock_entries) == rand_entry

def test_speed():
  entry = gen_random_formatted_data_entry()
  entry['dx'] = 0
  entry['dy'] = 0
  entry['dz'] = 0
  assert it.speed(entry) == 0
  entry = gen_random_formatted_data_entry()
  entry['dx'] = 1
  entry['dy'] = 1
  entry['dz'] = 1
  assert it.speed(entry) == math.sqrt(3)
  entry = gen_random_formatted_data_entry()
  assert it.speed(entry) == math.sqrt(entry['dx'] ** 2 + entry['dy'] ** 2 + entry['dz'] ** 2)

@patch.object(it.GEOCODER, 'reverse', side_effect=Exception)
def test_fetch_location_str_searches_correctly_and_handles_exception(mock_reverse):
  lla = gen_random_lla_coords()
  assert it.fetch_location_str(lla) == ''
  mock_reverse.assert_called_once_with(f'{lla[0]}, {lla[1]}', language='en', zoom=10)

@patch.object(it.GEOCODER, 'reverse')
def test_fetch_location_str_returns_empty_str_for_None_result(mock_reverse):
  mock_reverse.return_value = None
  assert it.fetch_location_str(gen_random_lla_coords()) == ''

@patch.object(it.GEOCODER, 'reverse')
def test_fetch_location_str_works_with_str_result(mock_reverse):
  mock_reverse.return_value = Mock(address='ohlookanaddress')
  assert it.fetch_location_str(gen_random_lla_coords()) == 'ohlookanaddress'

@patch.object(it.GEOCODER, 'reverse')
def test_fetch_location_str_works_with_object_result(mock_reverse):
  mockaddress = Mock(city='acity', municipality='astate', country='acountry')
  mock_reverse.return_value = Mock(address=mockaddress)
  assert it.fetch_location_str(gen_random_lla_coords()) == 'acity, astate, acountry'

@patch('coe332midterm.iss_tracker.astropy_lla_conversion')
@patch('coe332midterm.iss_tracker.fetch_location_str')
def test_location(mock_fetch_location_str, astropy_lla_conversion):
  entry = gen_random_formatted_data_entry()
  astropy_lla_conversion.return_value = (90, 90, 5)
  mock_fetch_location_str.return_value = 'afakelocationstr'
  assert it.location(entry) == (90, 90, 5, 'afakelocationstr')
  astropy_lla_conversion.assert_called_once_with(entry)
  mock_fetch_location_str.assert_called_once_with((90, 90, 5))

class TestApp:
  def test_init(self):
    app = it.App()
    assert isinstance(app.app, Flask)
    assert isinstance(app.data_source, it.NASADataManager)
    app_paths = [r.rule for r in app.app.url_map.iter_rules()]
    for path in ['/comment', '/header', '/metadata', '/epochs', '/epochs/<epoch>', '/epochs/<epoch>/speed', '/epochs/<epoch>/location', '/now']:
      assert path in app_paths

  @patch('flask.Flask.run')
  def test_run(self, mock_run):
    app = it.App()
    app.run()
    mock_run.assert_called_once_with(debug=True, host='0.0.0.0', port=5173)

  @patch('coe332midterm.iss_tracker.abort')
  @patch('coe332midterm.iss_tracker.NASADataManager.fetch_current_data')
  def test_get_data_failure(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = False
    data = app.get_data()
    mock_get_data.assert_called_once()
    mock_abort.assert_called_once_with(500, 'NASA data stale or unavilable. Please check the data source URL or try again later.')
    assert data is None

  @patch('coe332midterm.iss_tracker.abort')
  @patch('coe332midterm.iss_tracker.NASADataManager.fetch_current_data')
  def test_get_data_success_default(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = True
    app.data_source.data = []
    data = app.get_data()
    mock_get_data.assert_called_once()
    mock_abort.assert_not_called()
    assert data == []

  @patch('coe332midterm.iss_tracker.abort')
  @patch('coe332midterm.iss_tracker.NASADataManager.fetch_current_data')
  def test_get_data_success_header(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = True
    app.data_source.header = {'header': ''}
    data = app.get_data('header')
    mock_get_data.assert_called_once()
    mock_abort.assert_not_called()
    assert data == {'header': ''}

  @patch('coe332midterm.iss_tracker.abort')
  @patch('coe332midterm.iss_tracker.NASADataManager.fetch_current_data')
  def test_get_data_success_metadata(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = True
    app.data_source.metadata = {'metadata': ''}
    data = app.get_data('metadata')
    mock_get_data.assert_called_once()
    mock_abort.assert_not_called()
    assert data == {'metadata': ''}

  @patch('coe332midterm.iss_tracker.abort')
  @patch('coe332midterm.iss_tracker.NASADataManager.fetch_current_data')
  def test_get_data_success_metadata(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = True
    app.data_source.comments = ['comment']
    data = app.get_data('comments')
    mock_get_data.assert_called_once()
    mock_abort.assert_not_called()
    assert data == ['comment']

  @patch('coe332midterm.iss_tracker.abort')
  @patch('coe332midterm.iss_tracker.NASADataManager.fetch_current_data')
  def test_get_data_failure_invalid_args(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = True
    with pytest.raises(ValueError, match="data keyword argument must be one of 'epochs', 'header', 'metadata', 'comments'"):
      app.get_data('notreal')
    mock_get_data.assert_called_once()
    mock_abort.assert_not_called()

  @patch.object(it.App, 'get_data')
  def test_comments(self, mock_get_data):
    app = it.App()
    mock_get_data.return_value = ['comment']
    assert app.comments() == {'comments': ['comment']}

  @patch.object(it.App, 'get_data')
  def test_header(self, mock_get_data):
    app = it.App()
    mock_get_data.return_value = {'header': 'abc'}
    assert app.header() == {'header': {'header': 'abc'}}

  @patch.object(it.App, 'get_data')
  def test_metadata(self, mock_get_data):
    app = it.App()
    mock_get_data.return_value = {'metadata': 'abc'}
    assert app.metadata() == {'metadata': {'metadata': 'abc'}}

  @patch.object(it.App, 'get_data')
  def test_epochs_returns_all_epochs_by_default(self, mock_get_data):
    app = it.App()
    mock_get_data.return_value = [0, 1, 2]
    with app.app.test_request_context():
      response = app.epochs()
      mock_get_data.assert_called_once()
      assert response == {'data': [0, 1, 2]}

  @patch('coe332midterm.iss_tracker.abort', side_effect=Exception)
  @patch.object(it.App, 'get_data')
  def test_epochs_rejects_invalid_limit_char(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = [0, 1, 2]
    with app.app.test_request_context('?limit=a'):
      with pytest.raises(Exception):
        app.epochs()
      mock_get_data.assert_not_called()
      mock_abort.assert_called_once_with(400, 'Optional limit parameter must be a valid positive integer.')

  @patch('coe332midterm.iss_tracker.abort', side_effect=Exception)
  @patch.object(it.App, 'get_data')
  def test_epochs_rejects_invalid_limit_dig(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = [0, 1, 2]
    with app.app.test_request_context('?limit=0'):
      with pytest.raises(Exception):
        app.epochs()
      mock_get_data.assert_called_once()
      mock_abort.assert_called_once_with(400, 'Optional limit parameter must be greater than zero.')

  @patch('coe332midterm.iss_tracker.abort', side_effect=Exception)
  @patch.object(it.App, 'get_data')
  def test_epochs_rejects_invalid_offset_char(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = [0, 1, 2]
    with app.app.test_request_context('?offset=a'):
      with pytest.raises(Exception):
        app.epochs()
      mock_get_data.assert_not_called()
      mock_abort.assert_called_once_with(400, 'Optional offset parameter must be a valid nonnegative integer.')

  @patch('coe332midterm.iss_tracker.abort', side_effect=Exception)
  @patch.object(it.App, 'get_data')
  def test_epochs_rejects_invalid_offset_dig(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = [0, 1, 2]
    with app.app.test_request_context('?offset=4'):
      with pytest.raises(Exception):
        app.epochs()
      mock_get_data.assert_called_once()
      mock_abort.assert_called_once_with(400, 'Optional offset parameter must be less than the length of the dataset.')

  @patch.object(it.App, 'get_data')
  def test_epochs_returns_selected_epcohs(self, mock_get_data):
    app = it.App()
    mock_get_data.return_value = [0, 1, 2, 3, 4]
    test_table = {
      '?limit=1': [0],
      '?offset=0': [0, 1, 2, 3, 4],
      '?offset=1': [1, 2, 3, 4],
      '?limit=50': [0, 1, 2, 3, 4],
      '?offset=2&limit=2': [2, 3],
      '?offset=2&limit=50': [2, 3, 4],
    }
    for test_env, result in test_table.items():
      with app.app.test_request_context(test_env):
        assert app.epochs() == {'data': result}
        mock_get_data.assert_called_once()
        mock_get_data.reset_mock()

  @patch.object(it.App, 'get_data', side_effect=Exception)
  def test_specific_epoch_gets_data(self, mock_get_data):
    with pytest.raises(Exception):
      it.App().specific_epoch('')
      mock_get_data.assert_called_once()

  @patch('coe332midterm.iss_tracker.abort', side_effect=Exception)
  @patch.object(it.App, 'get_data')
  def test_specific_epoch_rejects_out_of_range_epoch(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = [0, 1, 2]
    with pytest.raises(Exception):
      app.specific_epoch('5')
    mock_abort.assert_called_once_with(400, 'Enter an epoch index within the range of the dataset or an epoch timestamp included in the dataset.')

  @patch.object(it.App, 'get_data')
  def test_specific_epoch_returns_in_range_epoch(self, mock_get_data):
    app = it.App()
    mock_get_data.return_value = [0, 1, 2]
    assert app.specific_epoch('2') == {'epoch': 2}

  @patch('coe332midterm.iss_tracker.abort', side_effect=Exception)
  @patch.object(it.App, 'get_data')
  def test_specific_epoch_rejects_invalid_timestamp(self, mock_get_data, mock_abort):
    app = it.App()
    mock_get_data.return_value = [0, 1, 2]
    with pytest.raises(Exception):
      app.specific_epoch('somegibberish')
    mock_abort.assert_called_once_with(400, 'Enter an epoch index within the range of the dataset or an epoch timestamp included in the dataset.')

  @patch.object(it.App, 'get_data')
  def test_specific_epoch_returns_null_for_valid_timestamp_not_present(self, mock_get_data):
    app = it.App()
    mock_get_data.return_value = [
      gen_random_formatted_data_entry(),
      gen_random_formatted_data_entry(),
      gen_random_formatted_data_entry(),
    ]
    assert app.specific_epoch('2024-052T12:00:00.000Z') == {'epoch': None}

  @patch.object(it.App, 'get_data')
  def test_specific_epoch_returns_data_for_valid_present_timestamp(self, mock_get_data):
    app = it.App()
    now = datetime.utcnow()
    # Next line is due to some precision loss because of microsecond differences and such
    # We need to generate timestamps from the same string
    now = datetime.strptime(now.strftime(it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT), it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT)
    selected_epoch = gen_random_formatted_data_entry(timestamp=now)
    mock_get_data.return_value = [
      gen_random_formatted_data_entry(),
      selected_epoch,
      gen_random_formatted_data_entry(),
    ]
    assert app.specific_epoch(now.strftime(it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT)) == {'epoch': selected_epoch}

  # The following test should be redundant because there shouldn't be duplicate timestamps in the data
  # But it is possible in code for that to happen
  # So we test anyway to handle it just in case
  @patch('coe332midterm.iss_tracker.abort', side_effect=Exception)
  @patch.object(it.App, 'get_data')
  def test_specific_epoch_returns_error_on_duplicate_timestamps(self, mock_get_data, mock_abort):
    app = it.App()
    now = datetime.utcnow()
    now = datetime.strptime(now.strftime(it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT), it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT)
    mock_get_data.return_value = [
      gen_random_formatted_data_entry(),
      gen_random_formatted_data_entry(timestamp=now),
      gen_random_formatted_data_entry(timestamp=now),
    ]
    with pytest.raises(Exception):
      app.specific_epoch(now.strftime(it.ISS_TRAJECTORY_DATA_DATETIME_FORMAT))
    mock_abort.assert_called_once_with(500, 'Multiple state vectors found for the specified timestamp.')

  @patch.object(it.App, '__init__')
  @patch.object(it.App, 'specific_epoch')
  def test_specific_epoch_speed_returns_speed_for_valid_epoch(self, mock_specific_epoch, mock_init):
    mock_init.return_value = None
    app = it.App()
    epoch = gen_random_formatted_data_entry()
    speed = it.speed(epoch)
    mock_specific_epoch.return_value = {'epoch': epoch}
    assert app.specific_epoch_speed('anythingsincewefakespecificepoch') == {'speed': speed}

  @patch('coe332midterm.iss_tracker.abort', side_effect=Exception)
  @patch.object(it.App, '__init__')
  @patch.object(it.App, 'specific_epoch')
  def test_specific_epoch_speed_aborts_on_invalid_epoch(self, mock_specific_epoch, mock_init, mock_abort):
    mock_init.return_value = None
    app = it.App()
    mock_specific_epoch.return_value = {'epoch': None}
    with pytest.raises(Exception):
      app.specific_epoch_speed('anythingsincewefakespecificepoch')
    mock_abort.assert_called_once_with(400, 'Specified epoch does not exist.')

  @patch.object(it.App, '__init__')
  @patch.object(it.App, 'specific_epoch')
  @patch('coe332midterm.iss_tracker.location')
  def test_specific_epoch_location_returns_location_for_valid_epoch(self, mock_location, mock_specific_epoch, mock_init):
    mock_init.return_value = None
    app = it.App()
    epoch = gen_random_formatted_data_entry()
    mock_specific_epoch.return_value = {'epoch': epoch}
    location = {
      'altitude': 400,
      'lat': -40.0,
      'locstr': 'locstr',
      'lon': 60.0,
    }
    mock_location.return_value = (location['lat'], location['lon'], location['altitude'], location['locstr'])
    assert app.specific_epoch_location('anythingsincewefakespecificepoch') == location

  @patch('coe332midterm.iss_tracker.abort', side_effect=Exception)
  @patch.object(it.App, '__init__')
  @patch.object(it.App, 'specific_epoch')
  def test_specific_epoch_location_aborts_on_invalid_epoch(self, mock_specific_epoch, mock_init, mock_abort):
    mock_init.return_value = None
    app = it.App()
    mock_specific_epoch.return_value = {'epoch': None}
    with pytest.raises(Exception):
      app.specific_epoch_location('anythingsincewefakespecificepoch')
    mock_abort.assert_called_once_with(400, 'Specified epoch does not exist.')

  @patch('coe332midterm.iss_tracker.location')
  @patch.object(it.App, 'get_data')
  def test_now(self, mock_get_data, mock_location):
    app = it.App()
    now = datetime.utcnow()
    epoch = gen_random_formatted_data_entry(timestamp=now)
    location = {
      'altitude': 400,
      'lat': -40.0,
      'locstr': 'locstr',
      'lon': 60.0,
    }
    mock_location.return_value = (location['lat'], location['lon'], location['altitude'], location['locstr'])
    mock_get_data.return_value = [
      gen_random_formatted_data_entry(),
      epoch,
      gen_random_formatted_data_entry(),
    ]
    assert app.now() == {
      'epoch': epoch,
      'speed': it.speed(epoch),
      'location': location,
    }