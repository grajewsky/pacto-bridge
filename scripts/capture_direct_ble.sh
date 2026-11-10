#!/usr/bin/env bash
# Run from the user's ordinary WSL terminal; Codex's sandbox cannot access HCI.
# sudo is used only for btmon, never for the Python application.
set -euo pipefail
pacto_project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$pacto_project_dir"
for pacto_command in sudo timeout btmon; do
    if ! command -v "$pacto_command" >/dev/null; then
        echo "Missing required command: $pacto_command" >&2
        exit 1
    fi
done
if [[ ! -x .venv/bin/python ]]; then
    echo 'Expected the existing WSL environment at .venv/bin/python.' >&2
    exit 1
fi
if [[ ! -d /sys/class/bluetooth/hci0 ]]; then
    echo 'Bluetooth controller hci0 is unavailable in this WSL session.' >&2
    exit 1
fi
sudo -v
mkdir -p captures
pacto_output_dir="$(mktemp -d "$pacto_project_dir/captures/direct-$(date -u +%Y%m%dT%H%M%S)-XXXXXX")"
pacto_trace="$pacto_output_dir/hci.btsnoop"
# Pre-create as the current user so the resulting artifact remains user-owned.
: > "$pacto_trace"
echo "Saving diagnostic files in: $pacto_output_dir"
echo 'Capturing HCI for up to 105 seconds. The treadmill can remain stopped.'
sudo -n timeout --signal=INT --kill-after=3s 105s \
    btmon --index 0 --date --no-pager --write "$pacto_trace" \
    > "$pacto_output_dir/btmon.txt" 2>&1 &
pacto_monitor_pid=$!
pacto_cleanup() {
    if sudo -n kill -0 "$pacto_monitor_pid" 2>/dev/null; then
        sudo -n kill -INT "$pacto_monitor_pid" 2>/dev/null || true
    fi
    wait "$pacto_monitor_pid" 2>/dev/null || true
}
trap pacto_cleanup EXIT
sleep 1
if ! sudo -n kill -0 "$pacto_monitor_pid" 2>/dev/null; then
    cat "$pacto_output_dir/btmon.txt" >&2
    echo 'Bluetooth monitor failed to start; capture was not attempted.' >&2
    exit 1
fi
pacto_app_status=0
.venv/bin/python -m pactobridge --log "$pacto_output_dir/app.jsonl" capture \
    --decoder pacto --polling pacto-status --duration 90 \
    --output "$pacto_output_dir/capture.jsonl" || pacto_app_status=$?
echo 'Finishing the Bluetooth trace…'
pacto_monitor_status=0
wait "$pacto_monitor_pid" || pacto_monitor_status=$?
trap - EXIT
# GNU timeout returns 124 after the intentional capture window.
if [[ "$pacto_monitor_status" != 0 && "$pacto_monitor_status" != 124 ]]; then
    echo "Bluetooth monitor exited with status $pacto_monitor_status. See btmon.txt." >&2
    exit 1
fi
if [[ ! -s "$pacto_trace" ]]; then
    echo 'No Bluetooth trace was saved. See btmon.txt.' >&2
    exit 1
fi
echo "Saved HCI, decoded btmon text and application capture: $pacto_output_dir"
exit "$pacto_app_status"
