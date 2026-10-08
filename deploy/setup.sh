#!/usr/bin/env bash
# One-time setup on an Ubuntu server (e.g. Oracle Cloud Always Free).
# Run from inside the project folder:  bash deploy/setup.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(whoami)"

sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo
  echo ">>> Fill in your keys first:  nano $APP_DIR/.env"
  echo ">>> Then run this script again."
  exit 0
fi

# Run the bot as a background service that starts on boot and restarts if it crashes.
sudo tee /etc/systemd/system/guidancecast.service > /dev/null <<UNIT
[Unit]
Description=GuidanceCast Telegram trend bot
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now guidancecast
sudo systemctl restart guidancecast
echo
echo "✅ Bot is running. Useful commands:"
echo "   sudo systemctl status guidancecast     # is it running?"
echo "   journalctl -u guidancecast -f          # live logs (Ctrl+C to exit)"
echo "   sudo systemctl restart guidancecast    # restart after changing .env or code"
