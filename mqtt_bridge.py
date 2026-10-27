"""Home Assistant MQTT Discovery bridge. Credentials stay in a private config file."""
import json
import re
from pathlib import Path
from wake_captured import build_payload

VERSION = '0.3.0'
COMMANDS = {
    'wake': ('Wybudź', 'mdi:power-on'),
    'power': ('Zasilanie (przełącz)', 'mdi:power'),
    'up': ('Góra', 'mdi:arrow-up'), 'down': ('Dół', 'mdi:arrow-down'),
    'left': ('Lewo', 'mdi:arrow-left'), 'right': ('Prawo', 'mdi:arrow-right'),
    'ok': ('OK', 'mdi:checkbox-marked-circle-outline'),
    'home': ('Ekran główny', 'mdi:home'), 'back': ('Wstecz', 'mdi:arrow-u-left-top'),
    'vol+': ('Głośniej', 'mdi:volume-plus'), 'vol-': ('Ciszej', 'mdi:volume-minus'),
    'mute': ('Wycisz', 'mdi:volume-mute'), 'play': ('Odtwórz / pauza', 'mdi:play-pause'),
}


def load_config(filename):
    path = Path(filename)
    if path.stat().st_mode & 0o077:
        raise ValueError('MQTT config must have owner-only permissions (chmod 600).')
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError('MQTT config must be a JSON object.')
    if not isinstance(data.get('target'), str):
        raise ValueError('target must be a Bluetooth MAC string.')
    build_payload(data['target'])
    device_id = data.get('device_id', 'mibox_bt_remote')
    if not isinstance(device_id, str) or not re.fullmatch(r'[a-z0-9_]{1,48}', device_id):
        raise ValueError('device_id must contain 1–48 lowercase letters, numbers or underscores.')
    name = data.get('name', 'Mi Box Bluetooth')
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError('name must be a non-empty string of at most 100 characters.')
    broker = data.get('mqtt')
    if not isinstance(broker, dict) or not isinstance(broker.get('host'), str) or not broker['host']:
        raise ValueError('mqtt.host is required.')
    port = broker.get('port', 1883)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('mqtt.port must be an integer from 1 to 65535.')
    for field in ('username', 'password'):
        if broker.get(field) is not None and not isinstance(broker[field], str):
            raise ValueError('mqtt credential fields must be strings.')
    if broker.get('password') is not None and not broker.get('username'):
        raise ValueError('mqtt.username is required when a password is configured.')
    if type(broker.get('tls', False)) is not bool:
        raise ValueError('mqtt.tls must be true or false.')
    return {'target': data['target'], 'device_id': device_id, 'name': name,
            'mqtt': {**broker, 'port': port}}


def discovery_messages(device_id, name):
    """Return retained discovery documents; never include broker credentials or MACs."""
    topic = 'mibox_bt/' + device_id
    device = {'identifiers': ['mibox_bt_' + device_id], 'name': name,
              'manufacturer': 'Independent community project',
              'model': 'Xiaomi RC Bluetooth bridge', 'sw_version': VERSION}
    origin = {'name': 'Mi Box Bluetooth remote', 'sw_version': VERSION}
    base = {'device': device, 'origin': origin}
    docs = {}
    for command, (label, icon) in COMMANDS.items():
        key = {'vol+': 'volume_up', 'vol-': 'volume_down'}.get(command, command)
        availability = [{'topic': topic + '/availability'}]
        if command != 'wake':
            availability.append({'topic': topic + '/hid_ready',
                                 'payload_available': 'ON', 'payload_not_available': 'OFF'})
        docs[f'homeassistant/button/{device_id}/{key}/config'] = {
            **base, 'unique_id': device_id + '_' + key,
            'default_entity_id': 'button.' + device_id + '_' + key,
            'name': label, 'icon': icon, 'command_topic': topic + '/command',
            'payload_press': command, 'qos': 0, 'retain': False,
            'availability': availability, 'availability_mode': 'all'}
    docs[f'homeassistant/binary_sensor/{device_id}/hid_ready/config'] = {
        **base, 'unique_id': device_id + '_hid_ready',
        'default_entity_id': 'binary_sensor.' + device_id + '_hid_ready',
        'name': 'Połączenie pilota', 'device_class': 'connectivity',
        'state_topic': topic + '/hid_ready', 'payload_on': 'ON', 'payload_off': 'OFF',
        'availability_topic': topic + '/availability'}
    return docs


class MqttBridge:
    def __init__(self, config, dispatch, report=print, client_factory=None):
        self.config = config
        self.dispatch = dispatch
        self.report = report
        self.client_factory = client_factory
        self.topic = 'mibox_bt/' + config['device_id']
        self.client = None
        self.connected = False
        self.started = False
        self.state = {'connected': False, 'hid_ready': False, 'waking': False}

    def start(self):
        if self.client_factory is None:
            import paho.mqtt.client as mqtt
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                      client_id='mibox_bt_' + self.config['device_id'])
        else:
            self.client = self.client_factory()
        broker = self.config['mqtt']
        if broker.get('username') is not None:
            self.client.username_pw_set(broker['username'], broker.get('password'))
        if broker.get('tls', False):
            self.client.tls_set()
        self.client.will_set(self.topic + '/availability', 'offline', qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)
        self.client.connect_async(broker['host'], broker['port'], keepalive=30)
        self.client.loop_start()
        self.started = True

    def _publish_discovery(self):
        for topic, document in discovery_messages(self.config['device_id'], self.config['name']).items():
            self.client.publish(topic, json.dumps(document, ensure_ascii=False), qos=1, retain=True)

    def _publish_state(self):
        self.client.publish(self.topic + '/hid_ready',
                            'ON' if self.state['hid_ready'] else 'OFF', qos=1, retain=True)
        self.client.publish(self.topic + '/state', json.dumps(self.state), qos=1, retain=True)

    def update_state(self, connected, hid_ready, waking):
        state = {'connected': bool(connected), 'hid_ready': bool(hid_ready), 'waking': bool(waking)}
        if state != self.state:
            self.state = state
            if self.connected:
                self._publish_state()

    def _on_connect(self, client, userdata, flags, reason, properties=None):
        self.connected = reason == 0
        if not self.connected:
            self.report('MQTT: broker odrzucił połączenie; sprawdź prywatną konfigurację.')
            return
        client.subscribe([(self.topic + '/command', 0), ('homeassistant/status', 0)])
        self._publish_discovery()
        self._publish_state()
        client.publish(self.topic + '/availability', 'online', qos=1, retain=True)
        self.report('MQTT: połączono; urządzenie Mi Box zgłoszone do Home Assistanta.')

    def _on_disconnect(self, client, userdata, flags, reason, properties=None):
        self.connected = False
        self.report('MQTT: rozłączono; klient spróbuje połączyć się ponownie.')

    def _on_message(self, client, userdata, message):
        if message.topic == 'homeassistant/status':
            if message.payload == b'online':
                self._publish_discovery()
                self._publish_state()
            return
        # Retained/duplicate Power messages must never toggle the device again.
        if message.topic != self.topic + '/command' or message.retain or message.dup:
            return
        if len(message.payload) > 32:
            return
        try:
            command = message.payload.decode('ascii')
        except UnicodeDecodeError:
            return
        if command in COMMANDS:
            self.dispatch(command)

    def stop(self):
        if not self.started:
            return
        try:
            if self.connected:
                self.client.publish(self.topic + '/availability', 'offline', qos=1,
                                    retain=True).wait_for_publish(timeout=2)
        except (RuntimeError, OSError, TimeoutError):
            self.report('MQTT: nie potwierdzono publikacji stanu offline podczas zamykania.')
        finally:
            self.client.disconnect()
            self.client.loop_stop()
            self.started = False
            self.connected = False
