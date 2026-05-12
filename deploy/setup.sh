#!/bin/bash
# One-time bootstrap for a fresh Ubuntu EC2 instance.
# Run as the ubuntu user: bash deploy/setup.sh
set -euo pipefail

REPO="https://github.com/dexmcmillan/2026-personal-policescout.git"
APP_DIR="/opt/policescout"
LOG_DIR="/var/log/policescout"

echo "==> Installing system packages"
sudo apt-get update -q
sudo apt-get install -y nginx git curl

echo "==> Installing uv"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

echo "==> Cloning repo to $APP_DIR"
sudo git clone "$REPO" "$APP_DIR"
sudo chown -R ubuntu:ubuntu "$APP_DIR"

echo "==> Installing Python and dependencies"
cd "$APP_DIR"
uv python install
uv sync

echo "==> Creating log directory"
sudo mkdir -p "$LOG_DIR"
sudo chown ubuntu:ubuntu "$LOG_DIR"

echo "==> Configuring nginx"
sudo cp "$APP_DIR/deploy/nginx-policescout.conf" /etc/nginx/sites-available/policescout
sudo ln -sf /etc/nginx/sites-available/policescout /etc/nginx/sites-enabled/policescout
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl reload nginx

echo "==> Writing .env file"
if [ -z "${DATABASE_URL:-}" ]; then
  echo ""
  echo "WARNING: DATABASE_URL is not set in your shell."
  echo "You must create $APP_DIR/.env manually before the scripts will work:"
  echo "  echo 'export DATABASE_URL=postgresql://user:pass@host:5432/dbname' > $APP_DIR/.env"
  echo "  chmod 600 $APP_DIR/.env"
else
  echo "export DATABASE_URL=$DATABASE_URL" > "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "  Written $APP_DIR/.env"
fi

echo "==> Installing crontab"
crontab "$APP_DIR/deploy/crontab"

echo ""
echo "Setup complete. The site will be live at http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)"
echo "First scan runs weekdays at 12:00 UTC (7 AM ET). To trigger manually:"
echo "  cd $APP_DIR && uv run python scan.py"
