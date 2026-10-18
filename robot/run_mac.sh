#!/bin/sh
# Everything on the Mac: BLE33 follow + iPhone camera (go-to-person, fall rescue, return trip)
# + dashboard data (port 5001, replaces robot/server.py) + robot controls (5002) + the
# iron-heart-web dashboard (http://localhost:5173), and an ngrok link to it for phones. The UNO Q must be plugged in by USB; the Mac drives its MCU.
#
#   ./run_mac.sh            start (Ctrl+C to stop)
#
# While this runs, follow mode on the UNO Q itself is stopped (only one thing can drive the robot
# and hold the BLE33). Unplug the UNO Q and power it on its own to go back to board-only follow.
cd "$(dirname "$0")"
ADB="$HOME/Library/Application Support/arduino_applab_workspace/arduino15/data/packages/arduino/tools/adb/32.0.0/adb"

"$ADB" wait-for-device
echo "UNO Q connected"
# Stop the board's own follow mode (it would grab the BLE33 and the motors), and keep it from
# restarting on its own if the board reboots (start_robot.sh checks this marker)
"$ADB" shell 'touch ~/robot/mac_in_control; for p in $(pgrep -f "python3 -u follow_bridge.py"); do kill $p; done' || true
# Hand control back to the board (and close the phone link) when this script stops
trap '"$ADB" shell "rm -f ~/robot/mac_in_control" 2>/dev/null; [ -n "$NGROK_PID" ] && kill $NGROK_PID 2>/dev/null' EXIT INT TERM
# The UNO Q's MCU router, reachable from here as localhost:5006
"$ADB" forward tcp:5006 localfilesystem:/var/run/arduino-router.sock
# The dashboard (iron-heart-web, see README): start it if it isn't already running, then open it
if ! curl -s -o /dev/null http://localhost:5173; then
    (cd ../iron-heart-web && nohup npx vite --port 5173 > /tmp/ironheart-vite.log 2>&1 &)
    sleep 4
fi
open -a "Google Chrome" http://localhost:5173 2>/dev/null || open http://localhost:5173
# Phone access: an ngrok tunnel to the dashboard (Vite proxies the APIs, so one tunnel does it all).
# Skipped if ngrok isn't installed or signed in (ngrok config add-authtoken <token>).
if command -v ngrok > /dev/null && ngrok config check > /dev/null 2>&1; then
    ngrok http 5173 --host-header=localhost:5173 --log=stdout > /tmp/ironheart-ngrok.log 2>&1 &
    NGROK_PID=$!
    sleep 3
    URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "import json,sys; print(next((t['public_url'] for t in json.load(sys.stdin)['tunnels'] if t['public_url'].startswith('https')), ''))" 2>/dev/null)
    echo "Phone dashboard: ${URL:-ngrok failed, see /tmp/ironheart-ngrok.log}"
else
    echo "Phone dashboard: off (install ngrok and run: ngrok config add-authtoken <token>)"
fi

python3 -u follow_bridge.py --robot-router localhost:5006 --seek "$@"
