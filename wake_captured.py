#!/usr/bin/env python3
"""Replay the Xiaomi RC wake advertisement captured locally on 2026-10-27.
Run with administrator privileges after stopping the GATT emulator advertising.
Keeps the laptop's Bluetooth address and existing pairing keys.
"""
import argparse
import re
import socket
import struct
import time

def build_payload(target):
    if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', target):
        raise ValueError('Expected Bluetooth MAC address AA:BB:CC:DD:EE:FF')
    suffix = bytes.fromhex(target.replace(':', ''))[-3:][::-1]
    return bytes.fromhex('02010503ff000106084d4920524303021218040d040500020a0004fe') + suffix

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, help='Mi Box Bluetooth MAC, not its IP or Wi-Fi MAC')
    args = parser.parse_args()
    try:
        payload = build_payload(args.target)
    except ValueError as error:
        parser.error(str(error))
    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_RAW, socket.BTPROTO_HCI)
    s.bind((0,))
    # Accept HCI Command Complete and Command Status events only.
    s.setsockopt(socket.SOL_HCI, socket.HCI_FILTER, struct.pack('<IIIH2x', 1 << 4, (1 << 14) | (1 << 15), 0, 0))
    s.settimeout(3)
    def command(opcode, params):
        s.send(bytes([1]) + struct.pack('<HB', opcode, len(params)) + params)
        while True:
            event = s.recv(260)
            if len(event) >= 7 and event[1] == 14 and struct.unpack_from('<H', event, 4)[0] == opcode:
                status = event[6]
                if status: raise RuntimeError(f'HCI {opcode:04x}: status {status:02x}')
                return
            if len(event) >= 7 and event[1] == 15 and struct.unpack_from('<H', event, 5)[0] == opcode and event[3]:
                raise RuntimeError(f'HCI {opcode:04x}: status {event[3]:02x}')
    try:
        command(0x2039, bytes.fromhex('0000'))
        # Extended HCI API with legacy ADV_IND on the air; public laptop address.
        params = bytes.fromhex('001300300000300000070000') + bytes(6) + bytes.fromhex('007f0100010000')
        command(0x2036, params)
        command(0x2037, bytes([0, 3, 1, len(payload)]) + payload)
        command(0x2039, bytes.fromhex('010100000000'))
        print('Xiaomi RC wake advertisement:', payload.hex(), flush=True)
        time.sleep(8)
    finally:
        try:
            command(0x2039, bytes.fromhex('000100000000'))
            command(0x203c, b'\x00')
        finally: s.close()

if __name__ == '__main__': main()
