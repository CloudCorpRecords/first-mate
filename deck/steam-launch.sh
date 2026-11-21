#!/usr/bin/env bash
# First Mate - Steam Gaming Mode launcher.
# Ensures the Deck server is running, then opens it fullscreen in Chrome.
cd "$HOME/first-mate-deck" || exit 1
export FIRST_MATE_PORT=8899
if ! curl -s -m 2 http://127.0.0.1:8899/health >/dev/null 2>&1; then
  nohup python3 deck.py >> server.log 2>&1 &
  for i in $(seq 1 30); do
    curl -s -m 2 http://127.0.0.1:8899/health >/dev/null 2>&1 && break
    sleep 0.5
  done
fi
exec flatpak run com.google.Chrome --kiosk --start-fullscreen --app=http://127.0.0.1:8899/
