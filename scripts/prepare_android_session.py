"""Drive the app's stopped-operator UI, then verify READY in its native journal.

Requires explicit operator flags. Never clicks a motor START confirmation.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

PACKAGE = 'pl.pactobridge.pacto_bridge'
DIRECTORY = f'/sdcard/Android/data/{PACKAGE}/files/sessions'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', required=True)
    parser.add_argument('--address', required=True)
    parser.add_argument('--stopped', action='store_true')
    parser.add_argument('--operator-present', action='store_true')
    args = parser.parse_args()
    if not args.stopped or not args.operator_present:
        parser.error('Operator must confirm stopped belt and presence at physical STOP')
    adb = Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk/platform-tools/adb.exe'

    def shell(*command):
        return subprocess.check_output([str(adb), '-s', args.serial, 'shell', *command],
                                       text=True, encoding='utf-8')

    def display():
        current = None
        for line in shell('dumpsys', 'activity', 'activities').splitlines():
            match = re.search(r'Display #(\d+)', line)
            if match:
                current = match[1]
            if 'topResumedActivity' in line and PACKAGE+'/.MainActivity' in line:
                return current
        raise RuntimeError('PactoBridge is not foreground on any display')

    def find(prefix):
        shell('uiautomator', 'dump', '/sdcard/pactobridge-ui.xml')
        root = ET.fromstring(shell('cat', '/sdcard/pactobridge-ui.xml'))
        return [n for n in root.iter('node') if n.get('package') == PACKAGE
                and n.get('content-desc', '').startswith(prefix)]

    def tap(prefix):
        nodes = find(prefix)
        for _ in range(3):
            if nodes:
                break
            shell('input', '-d', display(), 'swipe', '540', '2000', '540', '1100', '400')
            nodes = find(prefix)
        if len(nodes) != 1 or nodes[0].get('enabled') != 'true':
            raise RuntimeError(f'Expected one enabled app control: {prefix}')
        x1, y1, x2, y2 = map(int, re.findall(r'\d+', nodes[0].get('bounds')))
        shell('input', '-d', display(), 'tap', str((x1+x2)//2), str((y1+y2)//2))
        print(json.dumps({'ui_action': prefix}), flush=True)

    for _ in range(4):
        if find('Szukaj'):
            break
        shell('input', '-d', display(), 'swipe', '540', '2000', '540', '950', '500')
    tap('Szukaj')
    for _ in range(5):
        nodes = find('iConsole+0106')
        if nodes:
            break
    if len(nodes) != 1 or args.address.upper() not in nodes[0].get('content-desc', '').upper():
        raise RuntimeError('Known treadmill was not uniquely detected')
    tap('iConsole+0106')
    for prefix in ('Pas stoi', 'Jestem przy'):
        nodes = find(prefix)
        for _ in range(3):
            if nodes:
                break
            shell('input', '-d', display(), 'swipe', '540', '2000', '540', '1100', '400')
            nodes = find(prefix)
        if len(nodes) != 1:
            raise RuntimeError('Operator confirmation not visible')
        if nodes[0].get('checked') != 'true':
            tap(prefix)
        if find(prefix)[0].get('checked') != 'true':
            raise RuntimeError('Operator confirmation was not selected')
    previous = set(shell('ls', DIRECTORY).splitlines())
    tap('Przygotuj')
    deadline = time.monotonic()+30
    seen_states = set()
    while time.monotonic() < deadline:
        files = [n for n in shell('ls', '-t', DIRECTORY).splitlines()
                 if re.fullmatch(r'pacto-\d+-[a-f0-9]+\.jsonl', n) and n not in previous]
        if files:
            path = DIRECTORY+'/'+files[0]
            latest_state = None
            for line in shell('cat', path).splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                state = row.get('state') if row.get('kind') == 'session_state' else None
                if state:
                    latest_state = state
                if state and state not in seen_states:
                    print(json.dumps({'state': state, 'elapsed_ms': row['elapsed_ms']}), flush=True)
                    seen_states.add(state)
                if state in ('FAILED', 'INACTIVE'):
                    raise RuntimeError(row.get('message', 'Session stopped'))
            if latest_state == 'READY':
                print(json.dumps({'ready': True, 'journal': path, 'motor_start_clicked': False}), flush=True)
                return
        time.sleep(0.3)
    raise TimeoutError('Stopped session did not reach READY')


if __name__ == '__main__':
    main()
