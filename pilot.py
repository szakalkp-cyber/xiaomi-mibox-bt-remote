#!/usr/bin/env python3
"""Experimental BLE HID remote for the owner's Mi Box; no Xiaomi identity spoofing."""
import argparse
import os
import signal
import sys
import threading
import subprocess
from pathlib import Path
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

PROPS = 'org.freedesktop.DBus.Properties'
OM = 'org.freedesktop.DBus.ObjectManager'
SERVICE = 'org.bluez.GattService1'
CHAR = 'org.bluez.GattCharacteristic1'
DESC = 'org.bluez.GattDescriptor1'
AD = 'org.bluez.LEAdvertisement1'
ROOT = '/pl/mibox/pilot'
TARGET = os.environ.get('MIBOX_BT_ADDRESS', '')
DEVICE_NAME = 'MiBox Pilot PC'

# Xiaomi RC capture: consumer report ID 1, three 16-bit usages (6 bytes).
# Consumer Control only: no keyboard collection or keyboard appearance.
REPORT_MAP = bytes.fromhex('''
05 0c 09 01 a1 01 85 01 15 00 26 ff 03 19 00 2a ff 03
75 10 95 03 81 00 c0
''')
MEDIA = {'up': 0x42, 'down': 0x43, 'left': 0x44, 'right': 0x45,
         'ok': 0x41, 'back': 0x224,
         'home': 0x223, 'power': 0x30, 'vol+': 0xe9,
         'vol-': 0xea, 'mute': 0xe2, 'play': 0xcd}


def byte_array(value):
    return dbus.Array(value, signature='y')


class Node(dbus.service.Object):
    def __init__(self, bus, path, iface, properties):
        super().__init__(bus, path)
        self.path, self.iface, self.properties = path, iface, properties

    @dbus.service.method(PROPS, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != self.iface:
            raise dbus.exceptions.DBusException('Nieznany interfejs')
        return self.properties

    @dbus.service.method(PROPS, in_signature='ss', out_signature='v')
    def Get(self, interface, name):
        return self.GetAll(interface)[name]

    @dbus.service.signal(PROPS, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class Value(Node):
    def __init__(self, bus, path, uuid, parent, data, flags, descriptor=False):
        self.value = bytes(data)
        iface = DESC if descriptor else CHAR
        props = {'UUID': uuid, 'Flags': dbus.Array(flags, signature='s'),
                 'Characteristic' if descriptor else 'Service': dbus.ObjectPath(parent)}
        if not descriptor:
            props['Notifying'] = dbus.Boolean(False)
        super().__init__(bus, path, iface, props)

    def read(self, options):
        print('Odczyt GATT:', self.path, 'przez', options.get('device', '?'), flush=True)
        return byte_array(self.value[int(options.get('offset', 0)):])

    @dbus.service.method(CHAR, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        return self.read(options)

    @dbus.service.method(CHAR, in_signature='aya{sv}')
    def WriteValue(self, value, options):
        print('Zapis GATT:', self.path, bytes(value).hex(), flush=True)
        if not any('write' in str(flag) for flag in self.properties['Flags']):
            raise dbus.exceptions.DBusException('Read only', name='org.bluez.Error.NotPermitted')
        self.value = bytes(value)

    @dbus.service.method(CHAR)
    def StartNotify(self):
        if 'notify' not in self.properties['Flags']:
            raise dbus.exceptions.DBusException('Not supported', name='org.bluez.Error.NotSupported')
        self.properties['Notifying'] = dbus.Boolean(True)
        self.PropertiesChanged(CHAR, {'Notifying': dbus.Boolean(True)}, [])
        print('Mi Box włączył odbieranie przycisków:', self.path, flush=True)

    @dbus.service.method(CHAR)
    def StopNotify(self):
        self.properties['Notifying'] = dbus.Boolean(False)
        self.PropertiesChanged(CHAR, {'Notifying': dbus.Boolean(False)}, [])

    def send(self, data):
        self.value = bytes(data)
        self.PropertiesChanged(CHAR, {'Value': byte_array(self.value)}, [])
        return False


class Descriptor(Value):
    @dbus.service.method(DESC, in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        return self.read(options)


class App(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, ROOT)
        self.nodes = []
        service_path = ROOT + '/hid'
        self.nodes.append(Node(bus, service_path, SERVICE,
                               {'UUID': '1812', 'Primary': dbus.Boolean(True)}))

        def characteristic(name, uuid, value, flags):
            obj = Value(bus, service_path + '/' + name, uuid, service_path, value, flags)
            self.nodes.append(obj)
            return obj

        # RemoteWake + NormallyConnectable. A wake signal still requires a
        # working link or a firmware-supported advertising wake mechanism.
        characteristic('info', '2a4a', [0x11, 0x01, 0, 0x03], ['read'])
        characteristic('map', '2a4b', REPORT_MAP, ['read'])
        characteristic('control', '2a4c', [0], ['write-without-response'])
        characteristic('protocol', '2a4e', [1], ['read', 'write-without-response'])
        self.consumer = characteristic('consumer', '2a4d', bytes(6), ['encrypt-read', 'notify'])
        for obj, report_id in [(self.consumer, 1)]:
            self.nodes.append(Descriptor(bus, obj.path + '/reference', '2908', obj.path,
                                         [report_id, 1], ['read'], descriptor=True))
        battery_path = ROOT + '/battery'
        self.nodes.append(Node(bus, battery_path, SERVICE,
                               {'UUID': '180f', 'Primary': dbus.Boolean(True)}))
        self.nodes.append(Value(bus, battery_path + '/level', '2a19', battery_path, [100], ['read']))
        info_path = ROOT + '/deviceinfo'
        self.nodes.append(Node(bus, info_path, SERVICE,
                               {'UUID': '180a', 'Primary': dbus.Boolean(True)}))
        self.nodes.append(Value(bus, info_path + '/manufacturer', '2a29', info_path,
                                b'Local experimental remote', ['read']))
        self.nodes.append(Value(bus, info_path + '/model', '2a24', info_path,
                                b'MiBox Pilot PC prototype', ['read']))

    @dbus.service.method(OM, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        return {dbus.ObjectPath(n.path): {n.iface: n.properties} for n in self.nodes}

    def press(self, key):
        if key in MEDIA:
            report, data = self.consumer, MEDIA[key].to_bytes(2, 'little') + bytes(4)
        else:
            print('Polecenia: ' + ', '.join(MEDIA) + ', status, quit', flush=True)
            return False
        if not self.target_connected or not report.properties['Notifying']:
            print('Przycisk niewysłany: brak subskrypcji HID. Najpierw sparuj i połącz Mi Box.', flush=True)
            return False
        report.send(data)
        GLib.timeout_add(120, report.send, bytes(len(data)))
        print('Wysłano:', key, '(odbiór przez Box niepotwierdzony)', flush=True)
        return False


class Advertisement(Node):
    def __init__(self, bus):
        super().__init__(bus, ROOT + '_advert', AD, {
            'Type': 'peripheral', 'ServiceUUIDs': dbus.Array(['1812'], signature='s'),
            'LocalName': DEVICE_NAME, 'Appearance': dbus.UInt16(0x0180),
            'Discoverable': dbus.Boolean(True)})

    @dbus.service.method(AD)
    def Release(self):
        print('Rozgłaszanie zakończone.', flush=True)


class Agent(dbus.service.Object):
    def check(self, device):
        print('Żądanie agenta parowania:', device, flush=True)
        if not str(device).endswith('/dev_' + TARGET.replace(':', '_')):
            print('Odrzucono: adres różni się od skonfigurowanego Mi Boxa.', flush=True)
            raise dbus.exceptions.DBusException('Tylko skonfigurowany Mi Box', name='org.bluez.Error.Rejected')

    @dbus.service.method('org.bluez.Agent1', in_signature='o')
    def RequestAuthorization(self, device):
        self.check(device)
        print('Autoryzuję parowanie Mi Boxa.', flush=True)

    @dbus.service.method('org.bluez.Agent1', in_signature='ou')
    def RequestConfirmation(self, device, passkey):
        self.check(device)
        print(f'Kod parowania Mi Boxa: {int(passkey):06d}', flush=True)

    @dbus.service.method('org.bluez.Agent1', in_signature='os')
    def AuthorizeService(self, device, uuid):
        self.check(device)

    @dbus.service.method('org.bluez.Agent1')
    def Cancel(self):
        print('Parowanie anulowane.', flush=True)

    @dbus.service.method('org.bluez.Agent1')
    def Release(self):
        pass


def main():
    global TARGET
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', default=TARGET, required=not TARGET)
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', args.target):
        parser.error('Niepoprawny adres MAC')
    TARGET = args.target.upper()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    objects = dbus.Interface(bus.get_object('org.bluez', '/'), OM).GetManagedObjects()
    adapter = next((p for p, v in objects.items() if 'org.bluez.GattManager1' in v
                    and 'org.bluez.LEAdvertisingManager1' in v), None)
    if adapter is None:
        sys.exit('Adapter nie udostępnia GATT i rozgłaszania BLE.')
    app, advert = App(bus), Advertisement(bus)
    app.target_connected = any(str(p).endswith('/dev_' + TARGET.replace(':', '_')) and bool(v.get('org.bluez.Device1', {}).get('Connected', False)) for p, v in objects.items())
    agent_path = ROOT + '_agent'
    agent = Agent(bus, agent_path)
    manager = dbus.Interface(bus.get_object('org.bluez', '/org/bluez'), 'org.bluez.AgentManager1')
    manager.RegisterAgent(agent_path, 'NoInputNoOutput')
    manager.RequestDefaultAgent(agent_path)
    proxy = bus.get_object('org.bluez', adapter)
    gatt = dbus.Interface(proxy, 'org.bluez.GattManager1')
    advertising = dbus.Interface(proxy, 'org.bluez.LEAdvertisingManager1')
    loop = GLib.MainLoop()
    state = {'gatt': False, 'advert': False, 'failed': False}

    def failed(error):
        print('BŁĄD BlueZ:', error, flush=True)
        state['failed'] = True
        loop.quit()

    def advertised():
        state['advert'] = True
        print(f'GOTOWE: wybierz „{DEVICE_NAME}” w Dodaj akcesorium na Mi Boxie.', flush=True)
        print('Polecenia: up down left right ok back home power vol+ vol- mute play wake status quit', flush=True)

    def registered():
        state['gatt'] = True
        advertising.RegisterAdvertisement(advert.path, {}, reply_handler=advertised, error_handler=failed)

    def command(line):
        if line == 'quit':
            loop.quit()
        elif line == 'wake':
            if state.get('waking'):
                print('Wybudzanie już trwa.', flush=True)
                return False
            if app.target_connected:
                print('Poczekaj na rozłączenie Bluetooth po uśpieniu.', flush=True)
                return False
            state['waking'] = True
            advertising.UnregisterAdvertisement(advert.path)
            state['advert'] = False
            def resume(result):
                state['waking'] = False
                print('Nadajnik wybudzania zakończony:', result, flush=True)
                advertising.RegisterAdvertisement(advert.path, {}, reply_handler=advertised, error_handler=failed)
                return False
            def wake_worker():
                try:
                    result = subprocess.call(['pkexec', '/usr/bin/python3', str(Path(__file__).with_name('wake_captured.py').resolve()), '--target', TARGET])
                except OSError as error:
                    result = str(error)
                GLib.idle_add(resume, result)
            threading.Thread(target=wake_worker, daemon=True).start()
        elif line == 'status':
            print('HID pilot:', bool(app.target_connected and app.consumer.properties['Notifying']), flush=True)
        else:
            app.press(line)
        return False

    def read_input():
        for line in sys.stdin:
            GLib.idle_add(command, line.strip().lower())
        GLib.idle_add(loop.quit)

    def changed(interface, values, invalidated, path=None):
        if interface == 'org.bluez.Device1':
            relevant = {str(k): v for k, v in values.items()
                        if str(k) in ('Connected', 'Paired', 'Bonded', 'ServicesResolved')}
            if relevant:
                print('Stan połączenia:', path, relevant, flush=True)
            if str(path).endswith(TARGET.replace(':', '_')) and 'Connected' in values:
                app.target_connected = bool(values['Connected'])
                if not app.target_connected:
                    print('Mi Box rozłączył Bluetooth. Wybudzanie: wake.', flush=True)

    def added(path, interfaces):
        device = interfaces.get('org.bluez.Device1')
        if device is not None:
            print('Urządzenie:', path, device.get('Name', ''),
                  'adres:', device.get('Address'), 'typ:', device.get('AddressType'), flush=True)

    bus.add_signal_receiver(changed, dbus_interface=PROPS, signal_name='PropertiesChanged', path_keyword='path')
    bus.add_signal_receiver(added, dbus_interface=OM, signal_name='InterfacesAdded')
    gatt.RegisterApplication(ROOT, {}, reply_handler=registered, error_handler=failed)
    threading.Thread(target=read_input, daemon=True).start()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: (loop.quit(), False)[1])
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: (loop.quit(), False)[1])
    try:
        loop.run()
    finally:
        for active, method, path in [(state['advert'], advertising.UnregisterAdvertisement, advert.path),
                                      (state['gatt'], gatt.UnregisterApplication, ROOT),
                                      (True, manager.UnregisterAgent, agent_path)]:
            if active:
                try:
                    method(path)
                except dbus.DBusException:
                    pass
    if state['failed']:
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except dbus.DBusException as error:
        sys.exit('Brak dostępu lub błąd BlueZ: ' + str(error))
