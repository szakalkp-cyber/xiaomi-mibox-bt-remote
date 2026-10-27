#!/usr/bin/env python3
"""Mirror the owner's captured Xiaomi RC GATT identity and HID profile.

Microphone/OTA are not implemented. --wake starts the HID server and its
BlueZ-managed wake advertisement. Address and bond keys are not copied.
"""
import json
import sys
from pathlib import Path
import dbus
import dbus.service
import pilot as base

PROFILE = json.loads(Path(__file__).with_name('xiaomi-rc-profile.json').read_text())
SETUP_MODE = False
SUFFIX = '-0000-1000-8000-00805f9b34fb'


def short(uuid):
    return uuid[4:8] if uuid.startswith('0000') and uuid.endswith(SUFFIX) else uuid


def flags(properties, uuid):
    value = []
    if properties & 2:
        value.append('encrypt-read' if short(uuid) == '2a4d' else 'read')
    for bit, name in [(4, 'write-without-response'), (8, 'write'), (16, 'notify'), (32, 'indicate')]:
        if properties & bit:
            value.append(name)
    return value


class SnapshotValue(base.Value):
    def __init__(self, bus, path, parent, service_uuid, entry):
        self.entry = entry
        self.service_uuid = short(service_uuid)
        self.known = 'value' in entry or not (entry['properties'] & 2)
        super().__init__(bus, path, entry['uuid'], parent,
                         bytes.fromhex(entry.get('value', '')),
                         flags(entry['properties'], entry['uuid']))
        self.report_reference = next((bytes.fromhex(d['value']) for d in entry['descriptors']
                                      if short(d['uuid']) == '2908' and 'value' in d), None)

    def read(self, options):
        if not self.known:
            raise dbus.exceptions.DBusException('Original value could not be read', name='org.bluez.Error.NotSupported')
        return super().read(options)

    @dbus.service.method(base.CHAR, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        if not any('write' in flag for flag in self.properties['Flags']):
            raise dbus.exceptions.DBusException('Read only', name='org.bluez.Error.NotPermitted')
        uuid = short(self.entry['uuid'])
        safe = (uuid in ('2a4c', '2a4e', '2a32')
                or self.report_reference == bytes([2, 2])
                or self.service_uuid == 'a00a')
        if not safe:
            print('Niezaimplementowane polecenie Xiaomi/voice/OTA:', uuid, 'bytes:', len(value), flush=True)
            raise dbus.exceptions.DBusException('Proprietary command not implemented', name='org.bluez.Error.NotSupported')
        self.value = bytes(value)
        print('Zapis sterujący:', uuid, self.value.hex(), flush=True)


class SnapshotApp(base.App):
    def __init__(self, bus):
        dbus.service.Object.__init__(self, bus, base.ROOT)
        self.nodes = []
        self.consumer = None
        for si, service in enumerate(PROFILE['services']):
            # GAP/GATT are owned by BlueZ. Alias + advertisement reproduce
            # the readable identity; manager-owned handles are not copied.
            if short(service['uuid']) in ('1800', '1801'):
                continue
            path = base.ROOT + '/s' + str(si)
            self.nodes.append(base.Node(bus, path, base.SERVICE, {
                'UUID': service['uuid'], 'Primary': dbus.Boolean(service['type'] == 0)}))
            for entry in service['characteristics']:
                cp = path + '/c' + str(entry['instance'])
                characteristic = SnapshotValue(bus, cp, path, service['uuid'], entry)
                self.nodes.append(characteristic)
                if short(service['uuid']) == '1812' and characteristic.report_reference == bytes([1, 1]):
                    self.consumer = characteristic
                for di, descriptor in enumerate(entry['descriptors']):
                    # BlueZ owns CCCDs and subscription state.
                    if short(descriptor['uuid']) == '2902':
                        continue
                    if 'value' not in descriptor:
                        raise ValueError('Missing original descriptor: ' + cp)
                    self.nodes.append(base.Descriptor(bus, cp + '/d' + str(di), descriptor['uuid'], cp,
                                      bytes.fromhex(descriptor['value']), ['read'], descriptor=True))
        if self.consumer is None:
            raise ValueError('Consumer input report 1 not found')


class SnapshotAdvertisement(base.Node):
    def __init__(self, bus):
        super().__init__(bus, base.ROOT + '_advert', base.AD, {
            'Type': 'peripheral',
            'ServiceUUIDs': dbus.Array(['1812'], signature='s'),
            'LocalName': 'MiBox Pilot PC' if SETUP_MODE else 'Xiaomi RC',
            'Appearance': dbus.UInt16(0x0180 if SETUP_MODE else 0),
            'Discoverable': dbus.Boolean(True)})

    @dbus.service.method(base.AD)
    def Release(self):
        print('Rozgłaszanie zakończone.', flush=True)


def main():
    global SETUP_MODE
    wake_on_start = '--wake' in sys.argv
    if wake_on_start:
        sys.argv.remove('--wake')
    if '--setup' in sys.argv:
        SETUP_MODE = True
        sys.argv.remove('--setup')
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    base.App = SnapshotApp
    base.Advertisement = SnapshotAdvertisement
    base.DEVICE_NAME = 'MiBox Pilot PC' if SETUP_MODE else 'Xiaomi RC'
    bus = dbus.SystemBus()
    properties = dbus.Interface(bus.get_object('org.bluez', '/org/bluez/hci0'), base.PROPS)
    old_alias = properties.Get('org.bluez.Adapter1', 'Alias')
    try:
        properties.Set('org.bluez.Adapter1', 'Alias', dbus.String(base.DEVICE_NAME))
        print('Profil odczytanego Xiaomi RC; adres laptopa pozostaje adresem adaptera.', flush=True)
        print('Wybudzanie po rozłączeniu: wpisz wake. Osobny nadajnik: xiaomi_rc.py --wake --target ADRES_BT. Głos i OTA nie są obsługiwane.', flush=True)
        base.main(wake_on_start=wake_on_start)
    finally:
        properties.Set('org.bluez.Adapter1', 'Alias', old_alias)


if __name__ == '__main__':
    main()
