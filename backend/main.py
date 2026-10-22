from dotenv import load_dotenv

load_dotenv()  # must run before modules that read env at import time

import json  # noqa: E402
import logging  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from pathlib import Path  # noqa: E402

from fastapi import BackgroundTasks, Depends, FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from .auth import ADMIN_PASSWORD, SECRET_KEY, get_current_customer  # noqa: E402
from .config import APP_ENV, BUSINESS, SEED_DEMO, SMARTSUPP_KEY, whatsapp_digits  # noqa: E402
from .database import Base, engine, ensure_columns, get_db  # noqa: E402
from .models import STATUS_VALUES, Subscriber  # noqa: E402
from .routes import admin, customer, tracking  # noqa: E402
from .schemas import SubscribeIn  # noqa: E402
from .seed import DEMO_EMAIL, DEMO_RECEIVERS, seed_if_empty  # noqa: E402
from .models import Shipment  # noqa: E402
from .services.email import send_new_subscriber  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tracking")

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"
FRONTEND_DIR = ROOT / "frontend"
STATIC_DIR = ROOT / "static"

# ---------------------------------------------------------------- production guard
if APP_ENV == "production":
    problems = []
    if SECRET_KEY in ("", "change-this-long-random-string") or len(SECRET_KEY) < 32:
        problems.append("SECRET_KEY is missing, default or too short")
    if ADMIN_PASSWORD in ("", "changeme123"):
        problems.append("ADMIN_PASSWORD is still the default")
    if problems:
        sys.exit("Refusing to start in production: " + "; ".join(problems))
elif SECRET_KEY == "change-this-long-random-string" or ADMIN_PASSWORD == "changeme123":
    log.warning("Using default SECRET_KEY / ADMIN_PASSWORD — fine for local dev, change before deploying.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    for step, fn in (
        ("create_all", lambda: Base.metadata.create_all(bind=engine)),
        ("ensure_columns", ensure_columns),
        ("seed", seed_if_empty),
    ):
        try:
            fn()
        except Exception:
            log.exception("startup step %s failed; continuing", step)
    yield


app = FastAPI(title=f"{BUSINESS['name']} Tracking", lifespan=lifespan, docs_url=None, redoc_url=None)

_cors = [o.strip() for o in (os.getenv("CORS_ORIGINS") or "").split(",") if o.strip()]
if _cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# cache_size=0 avoids a stale-template bug seen with Python 3.12 + Jinja's LRU cache
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    cache_size=0,
)
_env.globals.update(
    business=BUSINESS,
    asset_version=str(int(time.time())),
    whatsapp_digits=whatsapp_digits(),
    smartsupp_key=SMARTSUPP_KEY,
    current_year=time.gmtime().tm_year,
    seed_demo=SEED_DEMO,
    status_values=STATUS_VALUES,
)
templates = Jinja2Templates(env=_env)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(tracking.router)
app.include_router(customer.router)
app.include_router(admin.router)


def _ctx(request: Request, db: Session, **extra) -> dict:
    return {"business": BUSINESS, "current_customer": get_current_customer(request, db), **extra}


def _is_demo_shipment(shipment) -> bool:
    return SEED_DEMO and (shipment.receiver_email or "").lower() in DEMO_RECEIVERS


def _demo_shipments(db: Session) -> list:
    """The seeded demo shipments, each with a plain-language note on what it demonstrates."""
    if not SEED_DEMO:
        return []
    rows = db.query(Shipment).filter(Shipment.receiver_email.in_(DEMO_RECEIVERS)).order_by(Shipment.id).all()
    out = []
    for s in rows:
        if s.journey_state in ("moving", "paused"):
            kind, icon, note = "Live moving map", "navigation", "A courier marker moves along a road route in real time, with a countdown to arrival."
        elif s.current_status == "Delivered":
            kind, icon, note = "Delivered", "package-check", "A finished delivery: every step ticked off and the full scan history."
        else:
            kind, icon, note = "Checkpoints only", "map-pin", "Updated by adding checkpoints (status + location). No moving marker."
        out.append({"tn": s.tracking_number, "kind": kind, "icon": icon, "note": note,
                    "route": f"{s.origin or '—'} → {s.destination or '—'}", "status": s.current_status})
    order = {"Live moving map": 0, "Checkpoints only": 1, "Delivered": 2}
    return sorted(out, key=lambda d: order[d["kind"]])


def _json(value) -> str:
    # safe to embed inside <script>: neutralise "</script>" and friends
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# ---------------------------------------------------------------- pages
@app.get("/", include_in_schema=False)
def index(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "index.html", _ctx(request, db))


MAX_MULTI_TRACK = 10


@app.get("/track", include_in_schema=False)
def track_query(request: Request, tn: str = "", db: Session = Depends(get_db)):
    """?tn=A or ?tn=A,B,C — one number redirects, several render a summary list."""
    numbers = []
    for part in re.split(r"[\s,;]+", tn.upper()):
        part = re.sub(r"[^A-Z0-9-]", "", part)
        if part and part not in numbers:
            numbers.append(part)
    if not numbers:
        return RedirectResponse("/", status_code=303)
    if len(numbers) == 1:
        return RedirectResponse(f"/track/{numbers[0]}", status_code=303)
    rows = []
    for number in numbers[:MAX_MULTI_TRACK]:
        shipment = tracking.find_shipment(db, number)
        last = tracking.shipment_events(db, shipment.id)[-1] if shipment else None
        rows.append({"tn": number, "shipment": shipment, "last": last})
    return templates.TemplateResponse(
        request,
        "track_multi.html",
        _ctx(request, db, rows=rows, truncated=len(numbers) > MAX_MULTI_TRACK, found=sum(1 for r in rows if r["shipment"])),
    )


@app.get("/track/{tn}", include_in_schema=False)
def track_page(tn: str, request: Request, db: Session = Depends(get_db)):
    shipment = tracking.find_shipment(db, tn)
    if not shipment:
        return templates.TemplateResponse(
            request, "track.html", _ctx(request, db, shipment=None, tn=tn.strip().upper()), status_code=404
        )
    events = tracking.shipment_events(db, shipment.id)
    current = {"lat": shipment.current_lat, "lng": shipment.current_lng, "status": shipment.current_status}
    route = tracking.parse_route(shipment)
    return templates.TemplateResponse(
        request,
        "track.html",
        _ctx(
            request,
            db,
            shipment=shipment,
            tn=shipment.tracking_number,
            events=events,
            events_json=_json([tracking.event_dict(e) for e in events]),
            current_json=_json(current),
            route_path_json=_json(route) if route else "null",
            journey_json=_json(tracking.journey_payload(shipment)),
            server_now=tracking.server_now_iso(),
            is_demo=_is_demo_shipment(shipment),
        ),
    )


@app.get("/login", include_in_schema=False)
def login_page(request: Request, db: Session = Depends(get_db)):
    if get_current_customer(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", _ctx(request, db))


@app.get("/register", include_in_schema=False)
def register_page(request: Request, db: Session = Depends(get_db)):
    if get_current_customer(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "register.html", _ctx(request, db))


@app.get("/dashboard", include_in_schema=False)
def dashboard_page(request: Request, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if not customer:
        return RedirectResponse("/login", status_code=303)
    show_guide = SEED_DEMO and customer.email.lower() == DEMO_EMAIL
    return templates.TemplateResponse(
        request, "dashboard.html", _ctx(request, db, show_guide=show_guide, demo_shipments=_demo_shipments(db) if show_guide else [])
    )


@app.get("/about", include_in_schema=False)
def about_page():
    return FileResponse(FRONTEND_DIR / "about.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(FRONTEND_DIR / "admin.html", headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(STATIC_DIR / "img" / "favicon.png")


# ---------------------------------------------------------------- small APIs
@app.get("/api/config")
def api_config():
    return {**BUSINESS, "whatsapp_digits": whatsapp_digits(), "seed_demo": SEED_DEMO, "current_year": time.gmtime().tm_year, "smartsupp_key": SMARTSUPP_KEY}


@app.post("/api/subscribe")
def api_subscribe(payload: SubscribeIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if not db.query(Subscriber.id).filter(Subscriber.email == email).first():
        db.add(Subscriber(email=email))
        db.commit()
        background.add_task(send_new_subscriber, email)
    return {"ok": True}


@app.get("/healthz")
def healthz():
    return {"ok": True}
