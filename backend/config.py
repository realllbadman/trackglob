"""Branding/config read from .env, shared by pages, API and emails."""
import os
import re

from dotenv import load_dotenv

load_dotenv()  # so scripts like `python -m backend.services.email` see .env too


def _abbr(name: str) -> str:
    words = [w for w in re.split(r"[\s\-_]+", name) if w and w[0].isalnum()]
    return "".join(w[0] for w in words)[:4].upper() or "PT"


def _env(name: str, default: str = "") -> str:
    """Read an env var; unfilled template placeholders like "[PHONE]" count as unset."""
    value = (os.getenv(name) or "").strip()
    if re.fullmatch(r"\[[^\]]*\]", value):
        return default
    return value or default


BUSINESS_NAME = _env("BUSINESS_NAME", "Your Courier")
BUSINESS_ABBR = _env("BUSINESS_ABBR") or _abbr(BUSINESS_NAME)
DEFAULT_DISCLAIMER = (
    f"{BUSINESS_NAME} is an independent logistics and parcel-tracking platform and is "
    "not affiliated with any national postal service or government agency."
)

BUSINESS = {
    "name": BUSINESS_NAME,
    "abbr": BUSINESS_ABBR,
    "email": _env("OWNER_EMAIL"),
    "phone": _env("OWNER_PHONE"),
    "whatsapp": _env("WHATSAPP"),
    "disclaimer": _env("DISCLAIMER") or DEFAULT_DISCLAIMER,
    "tracking_prefix": (os.getenv("TRACKING_PREFIX") or "CX").strip().upper(),
    "founded": _env("FOUNDED_YEAR"),
}
# phone number in dialable form for tel:/sms: links, e.g. "+12132180651"
BUSINESS["phone_tel"] = ("+" if BUSINESS["phone"].startswith("+") else "") + re.sub(r"\D", "", BUSINESS["phone"])

PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "http://localhost:8006").rstrip("/")
SEED_DEMO = (os.getenv("SEED_DEMO") or "0").strip() in ("1", "true", "yes", "on")
APP_ENV = (os.getenv("APP_ENV") or "development").strip().lower()
# Smartsupp live chat widget key (public; it appears in page source anyway). Empty = no chat.
SMARTSUPP_KEY = re.sub(r"[^A-Za-z0-9]", "", _env("SMARTSUPP_KEY"))


def whatsapp_digits() -> str:
    return re.sub(r"\D", "", BUSINESS["whatsapp"])
