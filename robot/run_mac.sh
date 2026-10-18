#!/bin/sh
# Everything on the Mac: BLE33 follow + iPhone camera (go-to-person, fall rescue, return trip)
# + iPhone heading check + dashboard. The UNO Q must be plugged in by USB; the Mac drives its MCU.
#
#   ./run_mac.sh            start (Ctrl+C to stop)
#
# While this runs, follow mode on the UNO Q itself is stopped (only one thing can drive the robot
# and hold the BLE33). Unplug the UNO Q and power it on its own to go back to board-only follow.
cd "$(dirname "$0")"
ADB="$HOME/Library/Application Support/arduino_applab_workspace/arduino15/data/packages/arduino/tools/adb/32.0.0/adb"

"$ADB" wait-for-device
echo "UNO Q connected"
# Stop the board's own follow mode (it would grab the BLE33 and the motors)
"$ADB" shell 'for p in $(pgrep -f "python3 -u follow_bridge.py"); do kill $p; done' || true
# The UNO Q's MCU router, reachable from here as localhost:5006
"$ADB" forward tcp:5006 localfilesystem:/var/run/arduino-router.sock
open -a "Google Chrome" ../frontend/index.html 2>/dev/null || open ../frontend/index.html

exec python3 -u follow_bridge.py --robot-router localhost:5006 --seek "$@"
