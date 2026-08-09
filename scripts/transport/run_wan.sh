#!/usr/bin/env bash
# Self-contained real-WAN transport run. The remote VM kills background
# processes on logout and has no passwordless sudo, so we hold the echo
# server alive inside a live ssh session that is a child of THIS script,
# run the client locally over the real path, then clean up.
#
# Configure via environment variables (no defaults are shipped: point them
# at your own cloud VM, and copy wan_transport_bench.py to /tmp on the VM
# first):
#   WAN_KEY   path to the ssh private key for the VM
#   WAN_USER  ssh user on the VM
#   WAN_HOST  VM public IP or hostname
#   WAN_PORT  TCP port to use (default 47101)
set -u
KEY="${WAN_KEY:?set WAN_KEY to the ssh key path}"
SRV="${WAN_USER:?set WAN_USER}@${WAN_HOST:?set WAN_HOST}"
HOST="$WAN_HOST"; PORT="${WAN_PORT:-47101}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/wan_transport_results.csv"
ERR="$HERE/wan_err.log"

ssh -n -i "$KEY" -o BatchMode=yes -o ServerAliveInterval=20 -o ServerAliveCountMax=1000 \
    "$SRV" "exec python3 /tmp/wan_transport_bench.py server $PORT" </dev/null &
SSHPID=$!

# wait (up to 20 s) for the server to start accepting
python3 - "$HOST" "$PORT" <<'PY'
import socket, sys, time
host, port = sys.argv[1], int(sys.argv[2])
for _ in range(20):
    try:
        socket.create_connection((host, port), timeout=3).close()
        print("server reachable"); sys.exit(0)
    except Exception:
        time.sleep(1)
print("server NOT reachable")
PY

# 30 trials per scheme over the real WAN
python3 "$HERE/wan_transport_bench.py" client "$HOST" "$PORT" 30 >"$OUT" 2>"$ERR"

kill "$SSHPID" 2>/dev/null
ssh -n -i "$KEY" -o BatchMode=yes "$SRV" 'pkill -f wan_transport_bench 2>/dev/null' </dev/null 2>/dev/null

echo "WAN DONE: $(($(wc -l <"$OUT") - 1)) data rows; $(wc -l <"$ERR") error lines"
