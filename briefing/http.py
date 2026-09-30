from __future__ import annotations

import ipaddress
import json
import re
import socket
import threading
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from .common import canonical_url

UA = "DailyKomoticBriefing/0.1 (private comics industry digest)"


class FetchError(RuntimeError):
    """A public page could not be safely retrieved."""


class APIError(RuntimeError):
    def __init__(self, service: str, status: int = 0, code: str = "request_failed"):
        self.service, self.status, self.code = service, status, code
        super().__init__(f"{service}: HTTP {status or 'network'} ({code})")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class Page:
    url: str
    body: bytes
    content_type: str = "text/html"


def public_url(url: str) -> str:
    result = canonical_url(url)
    parts = urlsplit(result)
    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except OSError:
        raise FetchError("dns_failure") from None
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise FetchError("non_public_address")
    return result


class PublicClient:
    """No credentials, no JavaScript, no paywall bypass, and conservative robots handling."""
    def __init__(self, timeout: int = 15, max_bytes: int = 3_000_000):
        self.timeout, self.max_bytes = timeout, max_bytes
        self.opener = build_opener(NoRedirect())
        self.robots: dict[str, RobotFileParser | bool] = {}
        self.lock = threading.Lock()
        self.host_locks: dict[str, threading.Lock] = {}
        self.last_request: dict[str, float] = {}

    def _raw(self, url: str, redirects: int = 4, check_redirect_robots: bool = False) -> Page:
        for hop in range(redirects + 1):
            url = public_url(url)
            # Check before fetching a redirected article, not after receiving it.
            # robots.txt itself is fetched without this flag to avoid recursion.
            if hop and check_redirect_robots and not self.allowed(url):
                raise FetchError("redirect_robots_disallowed")
            host = urlsplit(url).hostname
            with self.lock:
                host_lock = self.host_locks.setdefault(host, threading.Lock())
            with host_lock:
                wait = 0.6 - (time.monotonic() - self.last_request.get(host, 0))
                if wait > 0:
                    time.sleep(wait)
                self.last_request[host] = time.monotonic()
                req = Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/atom+xml, text/html, text/xml, */*"})
                try:
                    with self.opener.open(req, timeout=self.timeout) as response:
                        data = response.read(self.max_bytes + 1)
                        if len(data) > self.max_bytes:
                            raise FetchError("response_too_large")
                        return Page(url, data, response.headers.get("Content-Type", ""))
                except HTTPError as error:
                    if error.code in (301, 302, 303, 307, 308) and error.headers.get("Location"):
                        url = urljoin(url, error.headers["Location"])
                        continue
                    raise FetchError(f"http_{error.code}") from None
                except (URLError, OSError, TimeoutError):
                    raise FetchError("network_failure") from None
        raise FetchError("too_many_redirects")

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        # A per-client cache avoids repeatedly requesting robots.txt.
        with self.lock:
            cached = self.robots.get(origin)
        if cached is None:
            try:
                page = self._raw(origin + "/robots.txt")
                if "html" in page.content_type.lower():
                    cached = False
                else:
                    parser = RobotFileParser()
                    parser.parse(page.body.decode("utf-8", errors="replace").splitlines())
                    cached = parser
            except FetchError as error:
                # Missing robots.txt permits crawling; denial/unavailability does not.
                cached = str(error) in ("http_404", "http_410")
            with self.lock:
                self.robots[origin] = cached
        return cached if isinstance(cached, bool) else cached.can_fetch("DailyKomoticBriefing", url)

    def get(self, url: str) -> Page:
        url = canonical_url(url)
        if not self.allowed(url):
            raise FetchError("robots_disallowed_or_unavailable")
        return self._raw(url, check_redirect_robots=True)


class APIs:
    """Fixed provider endpoints; never expose API bodies or credentials in error logs."""
    def __init__(self):
        self.opener = build_opener(NoRedirect())

    def call(self, service: str, method: str, url: str, key: str,
             payload: dict | None = None, extra: dict | None = None) -> dict:
        expected = {"OpenAI": "api.openai.com", "Resend": "api.resend.com", "GitHub": "api.github.com"}
        if urlsplit(url).scheme != "https" or urlsplit(url).hostname != expected.get(service):
            raise ValueError("Unexpected API endpoint")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": UA}
        headers.update(extra or {})
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=100 if service == "OpenAI" else 35) as response:
                raw = response.read(2_000_000)
                result = json.loads(raw) if raw else {}
        except HTTPError as error:
            code = "request_failed"
            try:
                value = json.loads(error.read(16_384))
                detail = value.get("error", value) if isinstance(value, dict) else {}
                if isinstance(detail, dict):
                    candidate = detail.get("code") or detail.get("name") or detail.get("type")
                    if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z0-9_]{1,80}", candidate):
                        code = candidate
            except (ValueError, OSError):
                pass
            raise APIError(service, error.code, code) from None
        except (URLError, OSError, TimeoutError):
            raise APIError(service, 0, "network_failure") from None
        except (ValueError, UnicodeError):
            raise APIError(service, 0, "invalid_json") from None
        if not isinstance(result, dict):
            raise APIError(service, 0, "unexpected_response")
        return result


def ping(url: str, success: bool = True) -> None:
    if not url:
        raise RuntimeError("Missing HEALTHCHECKS_PING_URL")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or not parts.path.strip("/"):
        raise RuntimeError("Invalid Healthchecks ping URL")
    target = url.rstrip("/") + ("" if success else "/fail")
    try:
        req = Request(target, data=b"", headers={"User-Agent": UA}, method="POST")
        with build_opener(NoRedirect()).open(req, timeout=15) as response:
            response.read(100)
    except (HTTPError, URLError, OSError):
        raise RuntimeError("Healthchecks ping failed; URL omitted from logs") from None
