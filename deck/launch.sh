#!/usr/bin/env bash
# First Mate — Deck Edition launcher. Plain bash, no deps.
set -u
cd "$(dirname "$0")"
PORT="${FIRST_MATE_PORT:-8899}"
export FIRST_MATE_PORT="$PORT"
echo "Starting First Mate — Deck Edition on port $PORT ..."
python3 deck.py &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null' EXIT INT TERM
# Wait for /health (up to ~15s)
for i in $(seq 1 30); do
  if python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:${PORT}/health', timeout=2)" 2>/dev/null; then
    echo "Server healthy."
    break
  fi
  sleep 0.5
done
URL="http://localhost:${PORT}"
echo "Opening $URL fullscreen in default browser..."
if command -v xdg-open >/dev/null 2>&1; then
  (xdg-open "$URL" >/dev/null 2>&1 &)
else
  echo "Open this URL in your browser: $URL"
fi
echo "Press Ctrl+C to stop. From another device on the same WiFi, open http://<deck-ip>:${PORT}/logs"
wait $SERVER_PID
