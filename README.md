# Xiaomi Mi Box Bluetooth remote for Linux

Experimental Python/BlueZ remote with a captured Xiaomi RC GATT profile and a
Bluetooth advertising wake mechanism. The laptop keeps its own Bluetooth address
and pairing keys. This is an independent project, unaffiliated with Xiaomi.

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
advertising commands. This version uses `hci0`; use a dedicated adapter with no
other advertising applications. Raw wake transmission requires administrator
privileges and temporarily disables controller advertising.

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
| `wake` | Send the captured advertising wake packet after disconnection |
| `quit` | Stop the emulator |

For sleep, type `power` once, wait until the Box disconnects, then type `wake`.
Keep the emulator running across cycles: wake temporarily unregisters its
advertisement but preserves GATT and bonded subscription state. `wake` invokes
`pkexec` for the short raw-HCI transmitter and then restores normal advertising.
A successful transmitter exit means the controller accepted the commands;
verify the TV screen to confirm wake.

Standalone wake, with the emulator stopped:

```sh
sudo python3 wake_captured.py --target AA:BB:CC:DD:EE:FF
```

The wake packet was captured from the owner's original remote after the Box
had disconnected Bluetooth. It contains the last three bytes of the Box's
Bluetooth MAC in reverse order. See [protocol notes](PROTOCOL.md).
No ADB is required by the application. Hardware validation used ADB only to
read status and reconnect a stalled HID profile; power commands were sent via BT.

## Troubleshooting

- `status` is a local readiness indication, not an acknowledgement that Android
  consumed a key. A native HID device may take longer to become available.
- Recreating the GATT application across wakes can trigger Android service
  rediscovery and slow or failed HID reconnection. Keep one process running.
- If necessary, select/connect the saved accessory on the Box. In diagnostics,
  a stuck HID Host state required restarting Bluetooth and reconnecting.
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
