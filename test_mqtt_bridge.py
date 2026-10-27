import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from mqtt_bridge import MqttBridge, discovery_messages, load_config


def config():
    return {'target': 'AA:BB:CC:11:22:33', 'device_id': 'test_box', 'name': 'Test Box',
            'mqtt': {'host': 'localhost', 'port': 1883, 'username': 'test', 'password': 'test-password'}}


class Client:
    def __init__(self):
        self.published = []
        self.events = []
    def username_pw_set(self, *args): self.auth = args
    def will_set(self, *args, **kwargs): self.will = (args, kwargs)
    def reconnect_delay_set(self, **kwargs): pass
    def connect_async(self, *args, **kwargs): self.connection = args
    def loop_start(self): self.events.append('start')
    def subscribe(self, topics): self.subscriptions = topics
    def publish(self, *args, **kwargs):
        self.published.append((args, kwargs))
        return SimpleNamespace(wait_for_publish=lambda **kwargs: None)
    def disconnect(self): self.events.append('disconnect')
    def loop_stop(self): self.events.append('stop')


class DiscoveryTests(unittest.TestCase):
    def test_wake_stays_available_when_hid_is_disconnected(self):
        docs = discovery_messages('test_box', 'Test Box')
        wake = docs['homeassistant/button/test_box/wake/config']
        power = docs['homeassistant/button/test_box/power/config']
        self.assertEqual(len(wake['availability']), 1)
        self.assertEqual(len(power['availability']), 2)
        self.assertEqual(power['availability_mode'], 'all')
        self.assertFalse(power['retain'])
        self.assertEqual(power['qos'], 0)

    def test_discovery_has_stable_unique_ids_and_no_connection_secrets(self):
        docs = discovery_messages('test_box', 'Test Box')
        ids = [doc['unique_id'] for doc in docs.values()]
        self.assertEqual(len(ids), len(set(ids)))
        data = json.dumps(docs)
        for secret in ('AA:BB:CC:11:22:33', 'test-password', 'username', 'password'):
            self.assertNotIn(secret, data)
        self.assertEqual(len({tuple(doc['device']['identifiers']) for doc in docs.values()}), 1)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        self.commands = []
        self.bridge = MqttBridge(config(), self.commands.append, lambda text: None,
                                 client_factory=lambda: self.client)
        self.bridge.start()
        self.bridge._on_connect(self.client, None, None, 0)

    def message(self, payload, retain=False, dup=False, topic=None):
        self.bridge._on_message(self.client, None, SimpleNamespace(
            topic=topic or self.bridge.topic+'/command', payload=payload, retain=retain, dup=dup))

    def test_retained_duplicate_invalid_and_unrelated_commands_are_ignored(self):
        self.message(b'power', retain=True)
        self.message(b'power', dup=True)
        self.message(b'quit')
        self.message(b'power', topic='other/command')
        self.message(b'x'*33)
        self.message(b'\xff')
        self.assertEqual(self.commands, [])
        self.message(b'wake')
        self.message(b'home')
        self.assertEqual(self.commands, ['wake', 'home'])

    def test_birth_and_reconnect_republish_discovery_and_cached_state(self):
        self.bridge.update_state(True, True, False)
        self.client.published.clear()
        self.message(b'online', topic='homeassistant/status', retain=True)
        self.assertTrue(any(args[0].startswith('homeassistant/button/') for args, _ in self.client.published))
        self.assertIn(((self.bridge.topic+'/hid_ready', 'ON'), {'qos': 1, 'retain': True}), self.client.published)
        self.bridge._on_disconnect(self.client, None, None, 1)
        self.bridge.update_state(False, False, False)
        self.client.published.clear()
        self.bridge._on_connect(self.client, None, None, 0)
        self.assertIn(((self.bridge.topic+'/hid_ready', 'OFF'), {'qos': 1, 'retain': True}), self.client.published)

    def test_unexpected_disconnect_has_retained_offline_last_will(self):
        args, kwargs = self.client.will
        self.assertEqual(args, (self.bridge.topic+'/availability', 'offline'))
        self.assertEqual(kwargs, {'qos': 1, 'retain': True})
        self.bridge._on_disconnect(self.client, None, None, 1)
        self.assertFalse(self.bridge.connected)

    def test_clean_stop_marks_offline_and_closes_network_loop(self):
        self.bridge.stop()
        self.assertEqual(self.client.events[-2:], ['disconnect', 'stop'])
        self.assertIn(((self.bridge.topic+'/availability', 'offline'), {'qos': 1, 'retain': True}), self.client.published)
        self.assertFalse(self.bridge.started)


class ConfigurationTests(unittest.TestCase):
    def test_private_config_is_required_and_validated_without_echoing_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            path.write_text(json.dumps(config()))
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, 'owner-only'):
                load_config(path)
            path.chmod(0o600)
            self.assertEqual(load_config(path)['device_id'], 'test_box')
            data = config()
            data['mqtt']['port'] = 'test-password'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError) as error:
                load_config(path)
            self.assertNotIn('test-password', str(error.exception))


if __name__ == '__main__':
    unittest.main()
