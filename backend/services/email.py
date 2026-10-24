"""Transactional email: inline-styled HTML templates sent via SMTP (STARTTLS)."""
import html
import logging
import os
import re
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Optional

import aiosmtplib

from ..config import BUSINESS, PUBLIC_BASE_URL, _env, whatsapp_digits
from ..utils import as_utc

log = logging.getLogger("tracking.email")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = _env("SMTP_USER")
# Address emails are sent FROM. Defaults to SMTP_USER. Set it when your provider's login isn't
# an email address (Brevo, Mailgun, Amazon SES) — it must be on a domain you've verified there.
SMTP_FROM = _env("SMTP_FROM") or SMTP_USER
# Gmail app passwords are displayed as "abcd efgh ijkl mnop"; spaces must go.
SMTP_PASSWORD = (os.getenv("SMTP_PASSWORD") or "").replace(" ", "").strip()

BRAND = "#0f766e"
BRAND_DEEP = "#062925"
ACCENT = "#b5ec3b"


def e(value) -> str:
    return html.escape("" if value is None else str(value))


def track_url(tn: str) -> str:
    return f"{PUBLIC_BASE_URL}/track/{tn}"


def _fmt_time(dt: Optional[datetime]) -> str:
    dt = as_utc(dt)
    return dt.strftime("%b %d, %Y %H:%M UTC") if dt else "—"


def _html_to_text(markup: str) -> str:
    text = re.sub(r"<(br|/p|/tr|/h\d|/div)[^>]*>", "\n", markup, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _button(label: str, url: str) -> str:
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0">'
        f'<tr><td style="border-radius:999px;background:{BRAND}">'
        f'<a href="{e(url)}" style="display:inline-block;padding:13px 28px;font-family:Arial,sans-serif;'
        f'font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:999px">{e(label)}</a>'
        f"</td></tr></table>"
    )


def _base_html(title: str, body: str) -> str:
    name = e(BUSINESS["name"])
    contact = []
    if BUSINESS["phone"]:
        contact.append(
            f'Phone (calls &amp; texts): <a href="tel:{e(BUSINESS["phone_tel"])}" style="color:{BRAND}">{e(BUSINESS["phone"])}</a>'
        )
    if BUSINESS["whatsapp"]:
        contact.append(
            f'WhatsApp: <a href="https://wa.me/{whatsapp_digits()}" style="color:{BRAND}">{e(BUSINESS["whatsapp"])}</a>'
        )
    if BUSINESS["email"]:
        contact.append(f'Email: <a href="mailto:{e(BUSINESS["email"])}" style="color:{BRAND}">{e(BUSINESS["email"])}</a>')
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{e(title)}</title></head>
<body style="margin:0;padding:0;background:#eef2f8">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f8;padding:28px 12px">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;color:#0d1b2e">
  <tr><td style="background:{BRAND_DEEP};padding:24px 28px">
    <div style="font-size:20px;font-weight:800;color:#ffffff;letter-spacing:.2px">{name}</div>
    <div style="font-size:12px;color:#a7cfc9;margin-top:4px">24/7 Tracking · Worldwide &amp; Domestic Delivery</div>
  </td></tr>
  <tr><td style="height:4px;background:{ACCENT}"></td></tr>
  <tr><td style="padding:28px;font-size:15px;line-height:1.6">
    <h1 style="font-size:21px;margin:0 0 14px;color:#0d1b2e">{e(title)}</h1>
    {body}
  </td></tr>
  <tr><td style="background:#f5f8fc;padding:20px 28px;font-size:12px;color:#5c6b80;line-height:1.6">
    {"<br>".join(contact)}
    <div style="margin-top:10px">You are receiving this because a shipment lists your email for updates.</div>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def _detail_table(rows) -> str:
    cells = "".join(
        f'<tr><td style="padding:9px 12px;border-bottom:1px solid #e2e8f2;color:#5c6b80;width:40%">{e(k)}</td>'
        f'<td style="padding:9px 12px;border-bottom:1px solid #e2e8f2;font-weight:600">{e(v)}</td></tr>'
        for k, v in rows
    )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border:1px solid #e2e8f2;border-radius:10px;border-collapse:separate;font-size:14px">{cells}</table>'
    )


def build_message(to: str, subject: str, html_body: str) -> EmailMessage:
    """Standards-complete message: spam filters penalise missing Date/Message-ID or HTML-only mail."""
    from_domain = SMTP_FROM.rsplit("@", 1)[-1] if "@" in SMTP_FROM else None
    reply_to = BUSINESS["email"] or SMTP_FROM
    msg = EmailMessage()
    msg["From"] = formataddr((BUSINESS["name"], SMTP_FROM))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(usegmt=True)
    msg["Message-ID"] = make_msgid(domain=from_domain)
    if reply_to:
        msg["Reply-To"] = reply_to
        msg["List-Unsubscribe"] = f"<mailto:{reply_to}?subject=unsubscribe>"
    msg.set_content(_html_to_text(html_body))  # plain-text part
    msg.add_alternative(html_body, subtype="html")
    return msg


async def _send(to: str, subject: str, html_body: str) -> None:
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[email] SMTP not configured; skipping '{subject}' to {to}")
        return
    try:
        msg = build_message(to, subject, html_body)
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            use_tls=SMTP_PORT == 465,  # implicit TLS on 465, STARTTLS otherwise
            start_tls=SMTP_PORT != 465,
            timeout=20,
        )
        log.info("email sent: %s -> %s", subject, to)
    except Exception as exc:
        log.error("email send failed (%s -> %s): %s", subject, to, exc)
        print(f"[email] send failed: {exc}")


# ---------------------------------------------------------------- templates
async def send_shipment_created(shipment) -> None:
    if not shipment.notify_email or not shipment.receiver_email:
        return
    tn = shipment.tracking_number
    body = (
        f"<p>Hello {e(shipment.receiver_name)},</p>"
        f"<p>A shipment from <strong>{e(shipment.sender_name)}</strong> has been registered for you. "
        "You can follow every checkpoint with the tracking number below.</p>"
        f'<p style="font-size:24px;font-weight:800;letter-spacing:1px;color:{BRAND};margin:18px 0">{e(tn)}</p>'
        + _detail_table(
            [
                ("From", shipment.origin or "—"),
                ("To", shipment.destination or "—"),
                ("Service", shipment.service_type or "—"),
                ("Estimated delivery", shipment.estimated_delivery or "To be confirmed"),
            ]
        )
        + _button("Track your shipment", track_url(tn))
    )
    await _send(shipment.receiver_email, f"{BUSINESS['name']} — Shipment {tn} created", _base_html("Your shipment is registered", body))


async def send_status_update(shipment, event) -> None:
    if not shipment.notify_email or not shipment.receiver_email:
        return
    tn = shipment.tracking_number
    body = (
        f"<p>Hello {e(shipment.receiver_name)},</p>"
        f"<p>There is a new update on shipment <strong>{e(tn)}</strong>.</p>"
        + _detail_table(
            [
                ("Status", event.status),
                ("Location", event.location_name or "—"),
                ("Time", _fmt_time(event.timestamp)),
                ("Estimated delivery", shipment.estimated_delivery or "To be confirmed"),
            ]
            + ([("Remarks", event.notes)] if event.notes else [])
        )
        + _button("View full tracking history", track_url(tn))
    )
    await _send(
        shipment.receiver_email,
        f"{BUSINESS['name']} Update — {tn}: {event.status}",
        _base_html(f"Status: {event.status}", body),
    )


_JOURNEY_COPY = {
    "moving": ("Your shipment is on the move", "Your parcel has departed and is moving along its scheduled route."),
    "held": (
        "Your shipment is temporarily on hold",
        "Movement of your parcel has been paused by our team. We'll let you know as soon as it continues — "
        "the estimated delivery will be adjusted automatically.",
    ),
    "final": ("Out for final delivery", "Your parcel has reached the final leg and is out for delivery."),
}


async def send_journey_update(shipment, kind: str) -> None:
    if not shipment.notify_email or not shipment.receiver_email or kind not in _JOURNEY_COPY:
        return
    title, text = _JOURNEY_COPY[kind]
    tn = shipment.tracking_number
    eta = as_utc(shipment.journey_end)
    rows = [("Tracking number", tn), ("Status", shipment.current_status)]
    if eta and kind != "final":
        rows.append(("Scheduled arrival", _fmt_time(eta)))
    body = (
        f"<p>Hello {e(shipment.receiver_name)},</p><p>{e(text)}</p>"
        + _detail_table(rows)
        + _button("Watch it on the map", track_url(tn))
    )
    await _send(shipment.receiver_email, f"{BUSINESS['name']} — {tn}: {title}", _base_html(title, body))


async def send_welcome(customer) -> None:
    body = (
        f"<p>Hi {e(customer.first_name)},</p>"
        f"<p>Welcome to {e(BUSINESS['name'])}! Your account is ready. Shipments addressed to "
        f"<strong>{e(customer.email)}</strong> appear in your dashboard automatically, and you can follow "
        "any other parcel with its tracking number.</p>"
        + _button("Open my dashboard", f"{PUBLIC_BASE_URL}/dashboard")
    )
    await _send(customer.email, f"Welcome to {BUSINESS['name']}", _base_html("Your account is ready", body))


async def send_new_subscriber(email: str) -> None:
    if not BUSINESS["email"]:
        return
    body = f"<p>A new visitor subscribed to updates:</p><p><strong>{e(email)}</strong></p>"
    await _send(BUSINESS["email"], f"{BUSINESS['name']} — new subscriber", _base_html("New newsletter subscriber", body))


# ---------------------------------------------------------------- manual test
# Usage:  .venv/bin/python -m backend.services.email you@example.com
# Sends a sample "shipment created" email so you can check delivery (try it with mail-tester.com).
if __name__ == "__main__":
    import asyncio
    import sys
    from types import SimpleNamespace

    if len(sys.argv) != 2:
        sys.exit("usage: python -m backend.services.email <to-address>")
    if not SMTP_USER or not SMTP_PASSWORD:
        sys.exit("SMTP_USER / SMTP_PASSWORD are not set in .env")
    sample = SimpleNamespace(
        tracking_number=BUSINESS.get("tracking_example", BUSINESS["tracking_prefix"] + "0000000042"), receiver_name="Test Receiver",
        receiver_email=sys.argv[1], sender_name=BUSINESS["name"], origin="London, UK", destination="Berlin, Germany",
        service_type="Standard", estimated_delivery="To be confirmed", notify_email=1,
    )
    print(f"Sending test email from {SMTP_FROM} via {SMTP_HOST}:{SMTP_PORT} to {sys.argv[1]} ...")
    asyncio.run(send_shipment_created(sample))
