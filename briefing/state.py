from __future__ import annotations

import base64
import copy
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from .common import iso, parse_date
from .http import APIError, APIs


def empty_state() -> dict:
    return {"version": 1, "initialised": False, "seen": {}, "history": [], "budget": {}, "editions": {}}


def check_state(data: dict) -> dict:
    if data.get("version") != 1:
        raise RuntimeError("Unsupported state version; refusing to reset delivery or budget history")
    for field in ("seen", "history", "budget", "editions", "initialised"):
        if field not in data:
            raise RuntimeError("Incomplete state; refusing to reset delivery or budget history")
    return data


class LocalStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = check_state(json.loads(path.read_text())) if path.exists() else empty_state()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        temp.replace(self.path)


class MemoryStore:
    def __init__(self):
        self.data = empty_state()
        self.saved: list[dict] = []

    def save(self) -> None:
        self.saved.append(copy.deepcopy(self.data))


class GitHubStore:
    """Optimistic, durable state on a dedicated branch using the job's GITHUB_TOKEN."""
    def __init__(self, api: APIs, repository: str, token: str, base_sha: str, branch: str = "briefing-state"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise RuntimeError("Invalid GITHUB_REPOSITORY")
        if not token or not re.fullmatch(r"[a-fA-F0-9]{40,64}", base_sha):
            raise RuntimeError("Missing GitHub token or commit SHA")
        self.api, self.token, self.branch, self.base_sha = api, token, branch, base_sha
        self.root = f"https://api.github.com/repos/{repository}"
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        self.sha: str | None = None
        self.branch_ready = False
        try:
            record = self.api.call("GitHub", "GET", self.root + "/contents/state.json?ref=" + quote(branch, safe=""), token, extra=self.headers)
            self.sha = record["sha"]
            self.data = check_state(json.loads(base64.b64decode(record["content"], validate=False)))
            self.branch_ready = True
        except APIError as error:
            if error.status != 404:
                raise
            # A missing file on an EXISTING state branch is not a clean install.
            # Refuse to erase the delivery/spending ledger by silently starting over.
            try:
                self.api.call("GitHub", "GET", self.root + "/git/ref/heads/" + quote(branch, safe=""), token, extra=self.headers)
            except APIError as ref_error:
                if ref_error.status != 404:
                    raise
            else:
                raise RuntimeError("State branch exists but state.json is missing. Restore its history; automatic reset is disabled.")
            self.data = empty_state()
        except (KeyError, ValueError) as error:
            raise RuntimeError("State could not be decoded; refusing to replace it") from error

    def _ensure_branch(self) -> None:
        if self.branch_ready:
            return
        try:
            self.api.call("GitHub", "GET", self.root + "/git/ref/heads/" + quote(self.branch, safe=""), self.token, extra=self.headers)
        except APIError as error:
            if error.status != 404:
                raise
            self.api.call("GitHub", "POST", self.root + "/git/refs", self.token,
                          {"ref": "refs/heads/" + self.branch, "sha": self.base_sha}, self.headers)
        self.branch_ready = True

    def save(self) -> None:
        self._ensure_branch()
        encoded = json.dumps(self.data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > 900_000:
            raise RuntimeError("State exceeded its size limit; maintenance required before any more API calls")
        body = {"message": "Update briefing delivery and usage state [skip ci]", "branch": self.branch,
                "content": base64.b64encode(encoded).decode("ascii")}
        if self.sha:
            body["sha"] = self.sha
        result = self.api.call("GitHub", "PUT", self.root + "/contents/state.json", self.token, body, self.headers)
        self.sha = result["content"]["sha"]


def store_from_environment(api: APIs, local_path: Path | None = None):
    if local_path is not None:
        return LocalStore(local_path)
    if os.getenv("GITHUB_ACTIONS") == "true":
        return GitHubStore(api, os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_SHA", ""))
    return LocalStore(Path(".local/state.json"))


def prune(store, now: datetime) -> None:
    state = store.data
    limit = now - timedelta(days=45)
    entries = sorted(state["seen"].items(), key=lambda row: row[1].get("checked", ""), reverse=True)
    state["seen"] = {k: v for k, v in entries[:1200] if (parse_date(v.get("checked")) or now) >= limit}
    state["history"] = state["history"][-60:]
    for key, edition in list(state["editions"].items()):
        created = parse_date(edition.get("created")) or now
        if created < now - timedelta(days=45):
            del state["editions"][key]
        elif created < now - timedelta(days=4) and edition.get("status") in ("queued", "preview"):
            for field in ("payload", "briefing", "reviewed", "report"):
                edition.pop(field, None)
    # Retain recent budget entries; records are partitioned by calendar month.
    for key, value in list(state["budget"].items()):
        if (parse_date(value.get("created")) or now) < now - timedelta(days=100):
            del state["budget"][key]


class Budget:
    def __init__(self, store, cfg: dict, now: datetime):
        self.store, self.cfg, self.now = store, cfg, now

    @property
    def month(self) -> str:
        from zoneinfo import ZoneInfo
        return self.now.astimezone(ZoneInfo(self.cfg["timezone"])).strftime("%Y-%m")

    def used(self) -> float:
        return sum(row.get("cost_usd", row["reserved_usd"]) for row in self.store.data["budget"].values() if row["month"] == self.month)

    def reserve(self, request_id: str, payload: dict) -> tuple[bool, str]:
        records = self.store.data["budget"]
        if request_id in records:
            return False, "A model request was already attempted for this edition; it is not repeated automatically."
        pricing = self.cfg["model_pricing"]
        # UTF-8 bytes are deliberately more conservative than normal token counts.
        # Additional overhead covers message framing and schema processing. This is
        # an application guard using configured prices, not an account-wide guarantee.
        input_allowance = len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 8192
        reservation = (input_allowance * pricing["input_per_million"] +
                       payload["max_output_tokens"] * pricing["output_per_million"]) / 1_000_000
        reservation = round(reservation * 1.15, 6)
        if self.used() + reservation > self.cfg["monthly_budget_usd"]:
            return False, "Monthly model-spending guard reached; links are provided without generated analysis."
        records[request_id] = {"month": self.month, "created": iso(self.now), "reserved_usd": reservation}
        self.store.save()  # Must succeed BEFORE the potentially billable request.
        return True, ""

    def settle(self, request_id: str, usage: dict) -> None:
        if not isinstance(usage.get("input_tokens"), int) or not isinstance(usage.get("output_tokens"), int):
            return  # Keep the full reservation if usage is unavailable.
        pricing = self.cfg["model_pricing"]
        cost = (usage["input_tokens"] * pricing["input_per_million"] + usage["output_tokens"] * pricing["output_per_million"]) / 1_000_000
        # Cached input is charged at the uncached price here, conservatively.
        self.store.data["budget"][request_id]["cost_usd"] = round(cost, 6)
        self.store.save()
