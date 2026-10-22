# Parcel Tracking Platform

A full-stack courier **parcel-tracking** website: public tracking pages with a route map, step progress and checkpoint history; customer accounts; and an admin console for creating shipments, adding checkpoints and running a scheduled "live journey" animation. Tracking only — no products, cart, checkout or payments.

All branding (name, abbreviation, contact details, disclaimer) comes from `.env`.

## Features

- **Tracking page** `/track/{number}`: status banner, horizontal step indicator (Picked Up → In Transit → Out for Delivery → Delivered), checkpoint timeline, Leaflet map with an animated courier marker, CODE128 barcode, print view, shipper/receiver cards, shipment info, packages and history tables. Refreshes itself every 30 s.
- **Homepage**: rotating 3-slide hero with a large track box, count-up stats, a live tracking preview built from clearly labelled *sample* data, services, testimonials and a newsletter form.
- **Customer accounts**: register/login (signed cookie). Shipments addressed to your email are linked automatically. Follow or unfollow other shipments, and turn email updates on or off per shipment.
- **Admin console** `/admin`: stats; shipment create, search, edit and delete; checkpoints with server-side geocoding; route building (OSM + OSRM); journey start, pause, resume and arrive; customer list with password reset; subscriber list.
- **Email** (SMTP/Gmail): shipment created, status update, journey moving/held/final, welcome, new subscriber. If SMTP isn't configured, emails are skipped and logged.
- Responsive down to 360 px. Motion respects `prefers-reduced-motion`.

## Stack

Python 3.12 (3.10+ works) · FastAPI · Uvicorn · SQLAlchemy + SQLite · Jinja2 · passlib/bcrypt · itsdangerous · aiosmtplib · httpx
Frontend: vanilla JS · Leaflet 1.9.4 + OpenStreetMap tiles · Lucide icons · JsBarcode · Inter + Plus Jakarta Sans

## Local setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # then edit BUSINESS_NAME, contact details, SECRET_KEY …
./run.sh                      # http://localhost:8006   (./run.sh --reload for dev)
./stop.sh                     # frees port 8006
```

On first boot with `SEED_DEMO=1`, three demo shipments are created and their tracking numbers are printed as `[seed] …`. One of them is a London → Berlin road journey that is already moving.

| Demo | |
|---|---|
| Customer login | `demo@example.com` / `demo1234` |
| Admin login (`/admin`) | `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env` (default `admin` / `changeme123`) |

To start over, delete `tracking.db` and restart.

## Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs customer session cookies. **Must** be changed. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `BUSINESS_NAME` | Brand name used everywhere. Pick a name that does not resemble any existing carrier or postal service. |
| `BUSINESS_ABBR` | Short mark for the logo fallback (defaults to the initials, max 4 letters) |
| `OWNER_EMAIL` | Shown publicly; receives new-subscriber notices; used in the geocoder User-Agent |
| `OWNER_PHONE`, `WHATSAPP` | Shown in the header, footer, tracking page and emails |
| `DISCLAIMER` | Optional override of the footer non-affiliation disclaimer |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | Outgoing mail (STARTTLS). Leave the user/password blank to disable email. |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | HTTP Basic credentials for `/admin` and `/api/admin/*` |
| `TRACKING_PREFIX` | Tracking-number prefix (default `CX` → `CX` + 10 digits) |
| `PUBLIC_BASE_URL` | Used for links in emails. When it starts with `https://`, the session cookie is marked `Secure`. |
| `DATABASE_URL` | Default `sqlite:///./tracking.db` |
| `SEED_DEMO` | `1` seeds demo data into an empty DB and shows the demo-login hint |
| `APP_ENV` | `production` makes the app refuse to start with the default `SECRET_KEY`/`ADMIN_PASSWORD` |
| `CORS_ORIGINS` | Optional comma-separated extra origins. Leave empty for same-origin only (the normal setup). |

### Gmail app password

1. Turn on 2-Step Verification for the Google account.
2. Go to <https://myaccount.google.com/apppasswords> and create an app password for "Mail".
3. Put the account address in `SMTP_USER` and the 16-character password in `SMTP_PASSWORD`. Spaces are stripped automatically, so `abcd efgh ijkl mnop` works as pasted.

## How it works

```
 Admin (/admin, HTTP Basic)                    Public / customers
 ──────────────────────────                    ──────────────────
 create shipment ──► POST /api/admin/shipments     GET /track/{tn}  (Jinja inlines JSON + server_now)
   geocode origin ─► Nominatim (cached in DB)        │
   initial "Pending" event, email receiver           ▼
 add checkpoint ───► POST …/events                 map.js: fraction = (serverNow − start)/(end − start)
   geocode, update current status, email             draws rider on the cached route, every frame
 build route ──────► POST …/route                    │
   geocode stops ─► OSRM road route (cached)         ▼ every 30 s
 start/pause/resume/arrive ► POST …/journey/*      GET /api/track/{tn} → tmap.update(), toast on change
   stores only start/end/state/paused_frac
```

The server never pushes positions. It stores the journey's start, end (ETA), state and pause fraction. Every browser computes the same position from the server's clock (each page receives `server_now` and corrects for local clock skew), so two viewers see the parcel in the same place.

### Everyday admin tasks

- **New shipment**: Shipments tab → *New shipment* → fill the form → *Create*. Copy the tracking number or open the public page from the green box.
- **Add a checkpoint**: open a shipment → *Add checkpoint*. Choose a status, type a location ("City, Country" works best), add remarks. The receiver is emailed if updates are on.
- **Fix a mistake**: delete the checkpoint with its 🗑 button. The current status and location are recomputed from the latest remaining checkpoint.
- **Customer forgot password**: Customers tab → *Reset password*. The temporary password is shown once, so share it securely.

### The live journey

1. In the shipment modal, set the origin, optional waypoints and destination → **Build route**. Stops are geocoded and a road route is fetched once from OSRM and cached on the shipment. If OSRM fails, straight lines between the stops are used instead.
2. Set departure and arrival (ETA) → **Start**. The marker moves along the route in proportion to elapsed time.
3. **Pause** freezes the marker and sets the status to *On Hold / Delayed*. **Resume** continues from the same spot, and the ETA is pushed back by the pause length.
4. **Arrived** snaps the marker to the destination and sets *Out for Delivery*. Add a *Delivered* checkpoint when it's handed over.

Each step emails the receiver if updates are on.

## Honesty and compliance

- The tracking page tells viewers that the moving marker is the **scheduled position** set by the courier team, **not a live GPS fix**, and that checkpoints are the source of truth.
- The footer shows a non-affiliation disclaimer. Choose a brand name, logo, colours and domain that don't resemble any national postal service or carrier.
- Shipments and checkpoints should describe real parcels the business handles.
- The platform has no payment collection and no "pay a fee to release your parcel" flow, and none should be added. Statuses such as *Held at Customs* are informational only.

## Third-party services — please be polite

- **Nominatim** (geocoding): max 1 request/second (enforced), descriptive User-Agent with your contact email (set from `.env`), and results cached permanently in the `geocode_cache` table. For heavy use, run your own instance or use a commercial geocoder. [Usage policy](https://operations.osmfoundation.org/policies/nominatim/)
- **OSRM demo server** (routing): for light use only. Routes are fetched once per *Build route* and cached.
- **OpenStreetMap tiles**: attribution is shown on every map. For high traffic, use a tile provider. [Tile policy](https://operations.osmfoundation.org/policies/tiles/)

## Deployment

See [deploy/DEPLOY.md](deploy/DEPLOY.md). In short: copy the app to `/opt/parcel-tracking`, create `.env`, run `sudo deploy/deploy.sh`, apply the printed nginx block, and run certbot.

## Security notes

- User content is HTML-escaped in templates, in all `innerHTML` writes (`esc()`), and in emails.
- Passwords are bcrypt-hashed. Sessions are signed, `HttpOnly`, `SameSite=Lax` cookies, plus `Secure` over HTTPS.
- In-memory, per-IP rate limits: customer login (10 failures / 15 min), registration (5 / hour), admin auth (10 failures / 15 min).
- Uvicorn binds to `127.0.0.1` behind nginx in production.
- Checkpoint statuses are validated against the fixed status list.
- Deleting a shipment also deletes its checkpoints and follower links.
