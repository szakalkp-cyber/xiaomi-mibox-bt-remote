#!/usr/bin/env python3
"""Disable BlueZ's built-in DIS so the emulator supplies the only PnP ID.

Run without arguments to preview. --apply requires administrator privileges.
The original configuration is backed up and can be restored with --restore.
"""
import argparse
import difflib
import os
from pathlib import Path
import re
import subprocess

CONFIG = Path('/etc/bluetooth/main.conf')
BACKUP = Path('/etc/bluetooth/main.conf.mibox-pnp-backup')
TEMP = Path('/etc/bluetooth/main.conf.mibox-pnp-tmp')


def configure(text):
    lines = text.splitlines(keepends=True)
    group = None
    result = []
    inserted = False
    for line in lines:
        section = re.match(r'^\s*\[([^]]+)\]', line)
        if section:
            group = section.group(1)
            result.append(line if line.endswith('\n') else line + '\n')
            if group == 'General' and not inserted:
                result.append('# Mi Box emulator supplies Device Information / PnP ID.\nDeviceID = false\n')
                inserted = True
            continue
        if group == 'General' and re.match(r'^\s*DeviceID\s*=', line):
            continue
        result.append(line)
    if not inserted:
        raise ValueError('Brak sekcji [General]; konfiguracja nie zostanie zmieniona.')
    # Keep a previously applied configuration byte-identical.
    candidate = ''.join(result)
    marker = '# Mi Box emulator supplies Device Information / PnP ID.\n'
    candidate = candidate.replace(marker + 'DeviceID = false\n' + marker, marker + 'DeviceID = false\n')
    return candidate


def install(data, mode):
    with TEMP.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    TEMP.chmod(mode)
    os.replace(TEMP, CONFIG)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    options = parser.add_mutually_exclusive_group()
    options.add_argument('--apply', action='store_true')
    options.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    original = CONFIG.read_bytes()
    updated = BACKUP.read_bytes() if args.restore else configure(original.decode()).encode()
    if not (args.apply or args.restore):
        print(''.join(difflib.unified_diff(original.decode().splitlines(True), updated.decode().splitlines(True),
                                         fromfile=str(CONFIG), tofile=str(CONFIG) + ' (proposed)')))
        return
    if original == updated:
        print('Konfiguracja jest już ustawiona; brak zmian.')
        return
    mode = CONFIG.stat().st_mode & 0o777
    if args.apply and not BACKUP.exists():
        with BACKUP.open('xb') as stream:
            stream.write(original)
        BACKUP.chmod(mode)
    install(updated, mode)
    try:
        subprocess.run(['systemctl', 'restart', 'bluetooth.service'], check=True)
    except (subprocess.CalledProcessError, OSError):
        install(original, mode)
        subprocess.run(['systemctl', 'restart', 'bluetooth.service'], check=False)
        raise RuntimeError('Restart nie powiódł się; przywrócono poprzednią konfigurację.')
    print('Przywrócono oryginalną konfigurację.' if args.restore else
          'Wyłączono automatyczny Device ID BlueZ. Emulator może teraz udostępniać jedyną usługę Device Information.')
    print('Kopia:', BACKUP)


if __name__ == '__main__':
    try:
        main()
    except PermissionError:
        raise SystemExit('Brak praw administratora do /etc/bluetooth. Uruchom ten skrypt przez sudo z --apply.')
