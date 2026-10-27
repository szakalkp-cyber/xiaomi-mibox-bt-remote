# Hardware validation — 2026-10-27

Tested on Ubuntu, BlueZ 5.85, Python 3.14, Intel Bluetooth hci0; Android 14
MiTV-AFMU0 / Amlogic s7d, with a Xiaomi RC 2717:32b9 GATT snapshot.
The application kept the laptop's public Bluetooth address and existing bond.

## Final project version

| Cycle | Sleep | Sleep evidence | Wake | Result |
| --- | --- | --- | --- | --- |
| 1 | `power` over BLE HID | Bluetooth disconnected; status-read ADB connection timed out | Interactive `wake`, 8-second advertisement | ADB `mWakefulness=Awake`, `mWakefulnessChanging=false` |
| 2 | `power` over BLE HID | Bluetooth disconnected; status-read ADB connection timed out | Interactive `wake`, 8-second advertisement | ADB `mWakefulness=Awake`, `mWakefulnessChanging=false` |

These are two successful sleep/wake cycles, not a statistical reliability claim.
Sleep was inferred from BT disconnection and network loss after Power; the Box
slept too quickly for a direct `Asleep` reading in these two final cycles.
ADB sent no sleep or wake key events. It was used for read-only validation and
an explicit HID-profile connect between cycles after the first reconnect stalled.

Earlier in the session, two wake transmissions also returned Awake, but
recreating the emulator exposed slow/failed Android HID Host reconnection.
Diagnostics required a Bluetooth restart and HID reconnect. The final application
retains GATT across wake transmission and preserves BlueZ notification state
across a bonded disconnection. It tracks target connection state separately
to block disconnected keys.

## Limits

- Successful wake does not guarantee immediate restoration of HID controls.
  Android may need accessory reconnection and time to rebuild its input device.
- Native input was checked by the laptop's Bluetooth identity before each final
  sleep command; local `Notifying` alone is insufficient.
- No claim of automatic recovery from every HID Host stall is made.
- Target suffix parameterization was verified on the owner's Box only.
- Voice, microphone, firmware updates and other models were not tested.

## Automated checks

Protocol tests validate the 31-byte legacy advertising budget, AD field
boundaries, reversed target suffix, case handling and invalid address rejection.
They do not prove radio transmission or physical wake.
