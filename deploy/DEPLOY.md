# Deploying to a VPS (Ubuntu/Debian)

## 1. Server prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx
```

Point your domain's DNS A/AAAA records at the server.

## 2. Upload the app

```bash
sudo mkdir -p /opt/parcel-tracking
sudo rsync -a --exclude .venv --exclude '*.db' --exclude .env ./ /opt/parcel-tracking/
cd /opt/parcel-tracking
sudo cp .env.example .env && sudo nano .env
```

In `.env`, set at least:

- `SECRET_KEY` — generate with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
- `ADMIN_PASSWORD` — a strong password
- `BUSINESS_*`, `OWNER_*`, `WHATSAPP`, and the SMTP settings
- `PUBLIC_BASE_URL=https://your-domain`
- `SEED_DEMO=0` (unless you want the demo data)

## 3. Install and start the service

Edit `DOMAIN` / `ALT_DOMAIN` at the top of `deploy/deploy.sh`, then run:

```bash
sudo bash deploy/deploy.sh
```

The script:

1. checks that `backend/main.py` and `.env` exist, that the defaults have been changed, and that port 8006 is free;
2. creates `.venv` and installs the requirements;
3. writes and enables `/etc/systemd/system/parcel-tracking.service` (Uvicorn on `127.0.0.1:8006`, 2 workers, `APP_ENV=production`);
4. prints the nginx server block and the certbot command.

## 4. nginx + HTTPS

Save the printed block (or `deploy/nginx.conf`, with your domain and paths filled in) as `/etc/nginx/sites-available/parcel-tracking`, then:

```bash
sudo ln -s /etc/nginx/sites-available/parcel-tracking /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d example.com -d www.example.com
sudo systemctl restart parcel-tracking
```

## Operations

```bash
sudo systemctl status parcel-tracking
sudo journalctl -u parcel-tracking -f         # logs (emails, geocoding warnings, seed output)
sudo systemctl restart parcel-tracking        # after updating code or .env
```

**Backups:** the whole state is the `tracking.db` file. Copy it regularly, for example with a nightly `sqlite3 tracking.db ".backup '/var/backups/tracking-$(date +%F).db'"`.

**Workers and SQLite:** with `--workers 2`, the in-memory geocode cache, its lock and the rate-limit counters are per process. That's fine: the geocode cache table is shared through the database, and the per-IP limits are simply per worker.
