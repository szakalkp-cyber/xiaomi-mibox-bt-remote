# Home Assistant integration

This project can expose the Bluetooth remote as a device through Home Assistant's
built-in MQTT integration. It uses MQTT Discovery: no Home Assistant Core files,
custom integration or HACS installation is needed.

## Where the bridge runs

Run the bridge on the **Linux host that owns the Bluetooth adapter**. When Home
Assistant OS runs in a virtual machine on that host, the bridge stays outside
the VM and communicates with Home Assistant's MQTT broker. This avoids moving
the host's Bluetooth adapter into the VM. Use an adapter within range of the Box.

The existing Linux/BlueZ hardware requirements still apply. Home Assistant needs
its MQTT integration configured with a reachable broker. The bridge is not an
Android ADB integration and does not use ADB to send power commands.

## Install and pair

1. Follow the main README's BlueZ PnP configuration and pair the emulator with
   the Box once. If the accessory is already paired, do not remove its bond.
2. Install the project on the Bluetooth host, for example in
   `~/.local/share/mibox-bt-remote`.
3. Create a Python environment with distribution D-Bus/GLib modules available:

```sh
cd ~/.local/share/mibox-bt-remote
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements-mqtt.txt
```

4. Copy `mqtt-config.example.json` to
   `~/.config/mibox-bt-remote/config.json`. Enter the Box's Bluetooth MAC and
   broker connection settings in that private file. Set directory mode700 and
   file mode600. Keep the real config outside the repository.
5. Stop any other emulator process using the same adapter, then run:

```sh
.venv/bin/python xiaomi_rc.py --mqtt-config ~/.config/mibox-bt-remote/config.json
```

This is a long-running process, independent of terminal stdin. It publishes
retained discovery documents and current availability, and reconnects to the
broker after a network interruption. Credentials are read from the private
file, not command-line arguments or discovery payloads. Use broker TLS for
untrusted networks; `mqtt.tls: true` uses the default CA validation.

## Device and controls

Home Assistant → Settings → Devices & services → MQTT → **Mi Box Bluetooth**.
The device provides13 buttons and a connectivity sensor:

- **Wybudź**: advertise the Bluetooth wake fields; remains available when HID
  is disconnected, as long as the bridge is online.
- **Zasilanie (przełącz)**: send the original Bluetooth Power toggle. This is a
  toggle, not an inferred `turn_off` action. Available only while HID is ready.
- Navigation, OK, Home, Back, media and volume buttons: available while HID is ready.
- **Połączenie pilota**: whether the bridge has an active target link and report
  notifications. This is a connectivity sensor, not the Box's power state.

You can add these entities to a dashboard or call `button.press` in automations.
With the default device ID, the wake entity is `button.mibox_bt_remote_wake`.
Initial selection of the saved accessory may be needed after first pairing or
recreating the entire GATT process. Subsequent sleep/wake uses the managed
Bluetooth reconnection mechanism described in the main README.

## Run automatically

`mibox-bt-remote.service.example` is a user-systemd template for the installation
paths above. Copy it to `~/.config/systemd/user/mibox-bt-remote.service`, then:

```sh
systemctl --user daemon-reload
systemctl --user enable --now mibox-bt-remote.service
journalctl --user -u mibox-bt-remote.service -f
```

The user manager must remain running for the bridge to run. Configure its normal
login/startup policy to match the host's Home Assistant VM. Service restarts
must not launch a second emulator on the same adapter.

## Reliability and privacy

The bridge ignores retained commands, duplicate deliveries, unknown commands and
unrelated topics. Button command messages use QoS0 and are not retained, so a
broker/bridge restart does not replay an old Power toggle. Discovery and state
are retained, and Home Assistant birth messages trigger rediscovery.

The broker receives only the device name, stable configured device ID, generic
control definitions and connection state. Neither the target Bluetooth MAC nor
broker credentials are included in discovery. On an unexpected bridge failure,
its retained Last Will marks all entities unavailable; on clean shutdown the
bridge publishes offline explicitly.

A Home Assistant OS app/add-on running inside a VM cannot use an adapter owned
only by the outside Linux host. This companion bridge is designed for that setup;
it is not presented as a HACS custom integration.

References: [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)
and [MQTT button entities](https://www.home-assistant.io/integrations/button.mqtt/).
