# Observed wake advertisement

A local HCI capture of the original remote showed public-address, connectable
legacy `ADV_IND` advertisements on LE 1M. The short name was `MI RC`.

```text
02 01 05                 Flags: limited discoverable, BR/EDR unsupported
03 FF 00 01              Manufacturer AD field (literal captured bytes)
06 08 4D 49 20 52 43     Short name: MI RC
03 02 12 18              Partial service UUID list: HID 1812
04 0D 04 05 00           Class of Device: 000504
02 0A 00                 TX power: 0 dBm
04 FE ZZ YY XX           Observed vendor field: reverse target MAC suffix
```

For a synthetic target `AA:BB:CC:11:22:33`, the final field is
`04 FE 33 22 11`. Total advertising data is 31 bytes. The remote's ordinary
reconnection packet omitted this final field and used `03 FF 00 00`.
The suffix interpretation comes from the capture and local testing, not a
published Xiaomi specification. Whether other firmware requires additional
identity/bond filtering is unknown.

The legacy diagnostic transmitter uses extended HCI commands with **legacy** PDUs on air:
LE Set Extended Advertising Enable (2039), Parameters (2036), Data (2037),
and Remove Advertising Set (203C). Handle 0, public laptop address, all three
advertising channels, 30 ms interval, 8 seconds. It does not impersonate the
original remote's MAC or copy its link keys. The initial command disables all
advertising sets; use this version on an adapter dedicated to the emulator.

The consumer power report uses usage 0030, little-endian plus four zero bytes,
then an all-zero release after 120 ms. That HID report requires a live link;
the advertising packet is used after the sleeping Box disconnects.

## Managed wake and HID reconnection

Normal `wake` now uses an additional `org.bluez.LEAdvertisement1` registration,
not the raw transmitter. The existing normal advertisement and GATT application
remain registered throughout. This keeps connection ownership in BlueZ and lets
it handle the early connection timeout observed during the Box's resume.

The managed advertisement uses peripheral/connectable mode, service1812,
local name `MI RC`, limited discovery for8seconds,30ms advertising intervals,
manufacturer ID0100 with one zero byte, and custom AD typeFE containing the
reversed target MAC suffix. BlueZ controls AD order and puts the name in scan
response; this is not a byte-for-byte replay. The captured manufacturer prefix
`00 01` is preserved. A padding byte is necessary because BlueZ5.85's D-Bus
parser rejects empty manufacturer arrays. Class of Device and TX-power fields
from the raw capture are not required by the managed wake tested here.

The temporary advertisement alone is unregistered after8seconds. No default
advertisement removal, controller-wide disable, GATT recreation, raw HCI,
`pkexec` or Android profile-connect operation occurs in this path. Startup
`xiaomi_rc.py --wake --target ...` runs the same server and managed wake path.

References: [BlueZ advertisement API](https://github.com/bluez/bluez/blob/5.85/doc/org.bluez.LEAdvertisement.rst),
[BlueZ advertisement parser](https://github.com/bluez/bluez/blob/5.85/src/advertising.c).
