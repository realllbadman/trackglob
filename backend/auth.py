import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import get_db
from .models import Customer
from .utils import RateLimiter, client_ip

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-long-random-string")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8006")

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 14 * 24 * 3600
COOKIE_SECURE = PUBLIC_BASE_URL.lower().startswith("https://")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="customer-session")


def _truncate(password: str) -> str:
    # bcrypt only uses the first 72 bytes
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    return pwd_context.hash(_truncate(password))


def verify_password(password: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(_truncate(password), hashed)
    except Exception:
        return False


# ---------------------------------------------------------------- customer session
def set_session_cookie(response: Response, customer_id: int) -> None:
    token = _serializer.dumps({"cid": customer_id})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", samesite="lax", secure=COOKIE_SECURE, httponly=True)


def get_current_customer(request: Request, db: Session) -> Optional[Customer]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    cid = data.get("cid") if isinstance(data, dict) else None
    if not isinstance(cid, int):
        return None
    return db.get(Customer, cid)


def require_customer(request: Request, db: Session = Depends(get_db)) -> Customer:
    customer = get_current_customer(request, db)
    if not customer:
        raise HTTPException(status_code=401, detail="Not logged in")
    return customer


# ---------------------------------------------------------------- admin
security = HTTPBasic(auto_error=False)
admin_limiter = RateLimiter(max_hits=10, window_seconds=15 * 60)


def require_admin(request: Request, credentials: Optional[HTTPBasicCredentials] = Depends(security)) -> str:
    ip = client_ip(request)
    # The admin SPA sends X-Requested-With so we can skip the challenge header there;
    # otherwise the browser would pop its native Basic-auth dialog over our login form.
    from_spa = request.headers.get("x-requested-with") == "XMLHttpRequest"
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin credentials",
        headers=None if from_spa else {"WWW-Authenticate": "Basic"},
    )
    if admin_limiter.blocked(ip):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
    if credentials is None:
        raise unauthorized
    user_ok = secrets.compare_digest(credentials.username.encode(), ADMIN_USERNAME.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), ADMIN_PASSWORD.encode())
    if not (user_ok and pass_ok):
        admin_limiter.hit(ip)
        raise unauthorized
    return credentials.username
