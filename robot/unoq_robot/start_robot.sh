#!/bin/sh
# Start follow mode on the UNO Q (BLE33 over the board's own Bluetooth, motors via the MCU).
# Usage: ~/robot/start_robot.sh        (restarts it if already running)
cd "$(dirname "$0")"
# The Mac is running everything (run_mac.sh): don't start, or we'd grab the BLE33 from it
if [ -f mac_in_control ] && [ "$1" != "--force" ]; then
    echo "Mac is in control (mac_in_control), not starting. Delete it or use --force."
    exit 0
fi
for pid in $(pgrep -f "python3 -u follow_bridge.py"); do kill "$pid"; done
sleep 1
PYTHONPATH="$PWD/lib" setsid nohup python3 -u follow_bridge.py --robot-router \
    > bridge.log 2>&1 < /dev/null &
echo "follow mode started (log: $PWD/bridge.log)"
