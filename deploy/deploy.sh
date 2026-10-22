#!/usr/bin/env bash
# Run ON THE VPS from the app directory (e.g. /opt/parcel-tracking) as root or with sudo.
# Creates the venv, installs deps, writes + enables the systemd unit, and prints the
# nginx block and certbot command for you to apply.
set -euo pipefail

# ---------------------------------------------------------------- config
DOMAIN="globaltransiting.com"
ALT_DOMAIN="www.globaltransiting.com"
PORT=8013  # 8006 and 8010 are used by other apps on the VPS
SERVICE="parcel-tracking"
APP_USER="www-data"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> App dir: $APP_DIR"

# ---------------------------------------------------------------- sanity checks
[ -f "$APP_DIR/backend/main.py" ] || { echo "backend/main.py not found in $APP_DIR"; exit 1; }
[ -f "$APP_DIR/.env" ] || { echo ".env missing — cp .env.example .env and fill it in first"; exit 1; }
if grep -qE '^SECRET_KEY=change-this' "$APP_DIR/.env"; then
  echo "SECRET_KEY is still the default. Generate one with:"
  echo "  python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
  exit 1
fi
if grep -qE '^ADMIN_PASSWORD=changeme123' "$APP_DIR/.env"; then
  echo "ADMIN_PASSWORD is still the default — change it in .env"; exit 1
fi
if ss -ltn 2>/dev/null | grep -q ":${PORT} " && ! systemctl is-active --quiet "$SERVICE"; then
  echo "Port $PORT is already in use by another process."; exit 1
fi

# ---------------------------------------------------------------- venv
echo "==> Creating virtualenv + installing requirements"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ---------------------------------------------------------------- systemd
UNIT="/etc/systemd/system/${SERVICE}.service"
echo "==> Writing $UNIT"
cat > "$UNIT" <<EOF
[Unit]
Description=Parcel tracking website (FastAPI / Uvicorn)
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=APP_ENV=production
ExecStart=${APP_DIR}/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port ${PORT} --workers 2 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$SERVICE"
sleep 2
systemctl --no-pager --lines=5 status "$SERVICE" || true
curl -fsS "http://127.0.0.1:${PORT}/healthz" && echo "  <- health check OK"

# ---------------------------------------------------------------- nginx + TLS
cat <<EOF

==> Next: nginx. Save this as /etc/nginx/sites-available/${SERVICE}
-------------------------------------------------------------------
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN} ${ALT_DOMAIN};
    client_max_body_size 10M;

    location /static/ {
        alias ${APP_DIR}/static/;
        expires 7d;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
-------------------------------------------------------------------
  sudo ln -s /etc/nginx/sites-available/${SERVICE} /etc/nginx/sites-enabled/
  sudo nginx -t && sudo systemctl reload nginx
  sudo certbot --nginx -d ${DOMAIN} -d ${ALT_DOMAIN}

Then set PUBLIC_BASE_URL=https://${DOMAIN} in .env and: sudo systemctl restart ${SERVICE}
EOF
