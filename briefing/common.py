from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def clean(text: str) -> str:
    return " ".join(str(text).split())


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = clean(value)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (ValueError, TypeError, OverflowError):
            result = None
            for fmt in ("%B %d, %Y", "%b %d, %Y", "%m.%d.%Y", "%Y.%m.%d", "%d/%m/%Y"):
                try:
                    result = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    pass
    if result is None:
        return None
    # Date-only publication stamps are interpreted as UTC; the email labels dates,
    # not fabricated publication times.
    return (result.replace(tzinfo=UTC) if result.tzinfo is None else result).astimezone(UTC)


def canonical_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Unsupported or credential-bearing URL")
    if parts.port not in (None, 80, 443):
        raise ValueError("Non-standard web port")
    tracking = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref_src", "ref_url", "source", "srsltid"}
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in tracking]
    # WEBTOON notice pagination is not part of an individual notice's identity.
    if "notice/detail" in parts.path:
        query = [(k, v) for k, v in query if k != "page"]
    host = parts.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    return urlunsplit((parts.scheme.lower(), host, parts.path or "/", urlencode(sorted(query)), ""))


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def settings() -> dict:
    result = load_json(ROOT / "config/settings.json")
    result["timezone"] = os.getenv("NEWSLETTER_TIMEZONE", "").strip() or result["timezone"]
    result["send_time"] = os.getenv("NEWSLETTER_SEND_TIME", "").strip() or result["send_time"]
    result["email_from"] = os.getenv("EMAIL_FROM", "").strip() or result["email_from"]
    result["email_to"] = os.getenv("EMAIL_TO", "").strip() or result["email_to"]
    result["enabled"] = os.getenv("NEWSLETTER_ENABLED", "false").lower() == "true"
    ZoneInfo(result["timezone"])
    datetime.strptime(result["send_time"], "%H:%M")
    for key in ("email_from", "email_to"):
        if "\n" in result[key] or "\r" in result[key] or "@" not in parseaddr(result[key])[1]:
            raise ValueError(f"Invalid {key}")
    if not 0 < result["monthly_budget_usd"] <= 2:
        raise ValueError("monthly_budget_usd must be greater than zero and at most 2")
    return result
