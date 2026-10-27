# Home Assistant MQTT integration — 2026-10-28

Validated on the owner's Home Assistant OS VM, with the Bluetooth bridge running
as a user-systemd service on the Linux host and the existing local MQTT broker.
Home Assistant automatically created one device with13 buttons and a connectivity
sensor. The integration was confirmed in the actual Home Assistant device UI.

An end-to-end UI test passed: Bluetooth Power from the Home Assistant button
slept the Box, the HID-only buttons became unavailable while Wake stayed
available, and pressing Wake resumed the Box and restored native HID controls
automatically. No Android profile-connect command was issued during that cycle.
Home DOWN/UP was captured on the laptop's native consumer device after a Home
Assistant Home button press, including after wake. ADB was read-only during
validation; all control and power commands used MQTT → Linux bridge → Bluetooth.
A one-time profile connect was used after installing/restarting the bridge before
starting the end-to-end sleep/wake cycle, as in the documented initial setup.

Seventeen unit tests pass, covering the Bluetooth protocol/lifecycle and MQTT
Discovery, availability, Last Will, birth/reconnect, private configuration and
retained/duplicate/invalid command rejection. Runtime configuration and broker
credentials are outside this repository and were not published.

---

# Automatic HID reconnection — 2026-10-28

Three consecutive cycles passed on the same hardware and bond, in one emulator
process using BlueZ-managed wake advertisements. After the initial connection,
there were no Android/ADB profile-connect calls, Bluetooth restarts, reparing,
manual accessory selection, or emulator restarts during these three cycles.

| Cycle | Sleep | Wake / automatic HID | Functional input evidence |
| --- | --- | --- | --- |
| 1 | Consumer Power over BT; target disconnected | Awake and native laptop HID present | Home DOWN and UP captured on laptop's native consumer input |
| 2 | Consumer Power over BT; target disconnected | Awake and native laptop HID present | The subsequent Power over BT successfully slept the Box for cycle3 |
| 3 | Consumer Power over BT; target disconnected | Awake and native laptop HID present | Home DOWN and UP captured on laptop's native consumer input |

ADB was used only for passive power/input reads in these cycles. All sleep,
wake and navigation actions used Bluetooth. The native HID identity was checked
against the laptop's Bluetooth address, not just an advertisement or subscription.
A15-second input-event collector in cycle2 exceeded its ADB read timeout; that
capture is not claimed as Home evidence. The subsequent BT Power action verified
that HID controls had resumed. This collector timeout did not trigger reconnection.

The new path leaves normal advertising and GATT registered, adds a temporary
connectable wake advertisement for8seconds, and lets BlueZ handle connection
loss/retry. The Box can still drop its first connection during resume, but the
subsequent connection recovered automatically in the tested cycles.

Ten automated protocol/lifecycle tests pass, including duplicate wakes,
registration failure, timer cancellation, late callbacks on shutdown, BlueZ
release, and unregister failure cleanup. Compatibility beyond the tested device
and adapter is unverified; three cycles do not establish long-term reliability.

---

# Earlier baseline validation — 2026-10-27

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
