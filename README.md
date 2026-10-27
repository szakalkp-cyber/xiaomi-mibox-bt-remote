# Xiaomi Mi Box Bluetooth remote for Linux

Experimental Python/BlueZ remote with a captured Xiaomi RC GATT profile and a
Bluetooth advertising wake mechanism. The laptop keeps its own Bluetooth address
and pairing keys. This is an independent project, unaffiliated with Xiaomi.

## Home Assistant

Use the [Home Assistant MQTT integration](HOME_ASSISTANT.md) to expose wake,
Bluetooth Power, navigation/media buttons and connection status. The bridge
runs on the Linux Bluetooth host, including when Home Assistant is in a VM.
Real credentials and the Box address stay in a private local config file.

## Tested hardware

Ubuntu laptop with Intel Bluetooth, BlueZ 5.85 and Python 3.14; Android 14
Mi Box identified as MiTV-AFMU0, Amlogic s7d; original Xiaomi RC 2717:32b9.
Compatibility with other Xiaomi boxes, firmware or Bluetooth adapters is unknown.
See [hardware test notes](HARDWARE_TESTS.md) for results and limitations.

## Install

On Ubuntu/Debian:

```sh
sudo apt install bluez python3 python3-dbus python3-gi policykit-1
```

Use the system Python so the distribution's D-Bus and GLib modules are available.
The adapter must support BLE peripheral/GATT server mode and extended HCI
advertising support with at least two simultaneous advertising instances. This
version uses `hci0`. Normal control and interactive wake use BlueZ D-Bus; they
do not require raw-HCI privileges or disable other advertising applications.

## PnP ID configuration

BlueZ can expose its own Device Information service in addition to the emulated
one. On the tested Box this hid the correct vendor/product identity. Preview the
configuration change, then apply it if needed:

```sh
python3 fix_bluez_pnp.py
sudo python3 fix_bluez_pnp.py --apply
```

This sets `DeviceID = false` in `/etc/bluetooth/main.conf`, backs up the original
file and restarts Bluetooth, interrupting current Bluetooth connections.
Restore with `sudo python3 fix_bluez_pnp.py --restore`.

## Pair

Find the Box's **Bluetooth** MAC address; its Wi-Fi MAC and IP are different.
Use that MAC in place of `AA:BB:CC:DD:EE:FF`:

```sh
python3 xiaomi_rc.py --setup --target AA:BB:CC:DD:EE:FF
```

On the awake Box, open Settings → Remotes & accessories → Add accessory.
Select **MiBox Pilot PC**. After pairing, enter `quit`, then start normal mode:

```sh
python3 xiaomi_rc.py --target AA:BB:CC:DD:EE:FF
```

You can also set `MIBOX_BT_ADDRESS` instead of passing `--target` each time.
Pairing uses a temporary default NoInputNoOutput agent restricted to the target
MAC; the laptop alias is restored on normal exit. Voice and firmware updates are
not implemented. The supplied profile mirrors readable original GATT data;
attribute handles and original security permissions cannot be cloned exactly.

## Control, sleep and wake

Wait for the Box to connect and enable report notifications. Terminal commands:

| Command | Action |
| --- | --- |
| `up`, `down`, `left`, `right`, `ok` | Navigation |
| `home`, `back` | Android TV navigation |
| `vol+`, `vol-`, `mute`, `play` | Media control |
| `power` | Send the original Consumer Power usage over Bluetooth; toggles power |
| `status` | Connection and HID subscription readiness |
| `wake` | Advertise the observed wake fields through BlueZ after disconnection |
| `quit` | Stop the emulator |

For sleep, type `power` once, wait until the Box disconnects, then type `wake`.
Keep the emulator running across cycles: `wake` adds a temporary, connectable
BlueZ advertisement for 8 seconds while the normal advertisement, GATT and
bonded subscriptions stay available. BlueZ handles the incoming connection and
restarts advertising after early connection loss; no Android connect command
is issued.
Successful advertisement registration is not an acknowledgement from the Box;
verify the TV screen or the resumed HID controls to confirm wake.

To start the emulator and wake the Box in one command:

```sh
python3 xiaomi_rc.py --wake --target AA:BB:CC:DD:EE:FF
```

The process stays running to serve HID after wake. `wake_captured.py` remains
an administrator-only diagnostic raw-packet replay tool; it does not provide
a HID server and is not used by normal wake.

The wake packet was captured from the owner's original remote after the Box
had disconnected Bluetooth. It contains the last three bytes of the Box's
Bluetooth MAC in reverse order. See [protocol notes](PROTOCOL.md).
No ADB is required by the application. Current automatic-reconnection validation
used ADB only to read status and input events during the cycles; power and navigation were sent via BT. Earlier
baseline tests needed a profile-connect helper, as documented in the test notes.

## Troubleshooting

- `status` is a local readiness indication, not an acknowledgement that Android
  consumed a key. A native HID device may take longer to become available.
- Keep one GATT process running across cycles. Recreating the application can
  trigger Android service rediscovery; the managed wake path avoids that.
- If the adapter has no free advertising instance, wake reports a registration
  error while the normal advertisement and HID server remain available.
- Automatic recovery is validated only on the hardware listed above. Earlier
  raw-HCI baseline tests had HID stalls; see the dated validation notes.
- A fully powered-off/unplugged Box cannot receive Bluetooth wake packets.
- Microphone, voice search and OTA are intentionally unimplemented.
- Wake compatibility is device/firmware specific; these tests do not establish
  universal Xiaomi support or long-term reliability.

## Development

```sh
python3 -m unittest discover -v
python3 -m compileall -q .
```

No ADB keys, bond keys, HCI logs, bugreports, device-specific MAC addresses or
vendor binaries are included. Tests use synthetic addresses and require no radio.
