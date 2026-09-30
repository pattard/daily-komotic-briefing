from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .common import ROOT, iso, load_json, parse_date, settings, utcnow
from .editor import analysis_record, edit
from .http import APIError, APIs, PublicClient, ping
from .render import render, write_outputs
from .sources import collect
from .state import Budget, prune, store_from_environment


def target_time(now: datetime, cfg: dict) -> datetime:
    local = now.astimezone(ZoneInfo(cfg["timezone"]))
    hour, minute = map(int, cfg["send_time"].split(":"))
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0)


def production_mode(mode: str) -> bool:
    return mode in ("scheduled", "send-edition")


def clean_briefing(briefing: dict) -> dict:
    result = copy.deepcopy(briefing)
    for source in result.get("links", []):
        source.pop("excerpt", None)
    for item in result["items"]:
        for source in item["sources"]:
            source.pop("excerpt", None)
    return result


def apply_coverage(state: dict, edition: dict) -> None:
    if edition["briefing"]["status"] == "collection_failure":
        return
    state["initialised"] = True
    for key, value in edition["reviewed"].items():
        state["seen"][key] = value
    for item in edition["briefing"]["items"]:
        state["history"].append({"event_key": item["event_key"], "headline": item["headline"],
                                  "summary": item["summary"], "date": edition["created"][:10]})
    state["history"] = state["history"][-60:]


def deliver(store, key: str, api, resend_key: str, clock=utcnow) -> str:
    edition = store.data["editions"][key]
    if edition["status"] == "queued":
        return edition["email_id"]
    now = clock()
    first = parse_date(edition.get("first_attempt"))
    if first and now - first >= timedelta(hours=23):
        raise RuntimeError("An unresolved send is older than 23 hours. Check Resend before changing state; automatic retry is disabled.")
    scheduled = parse_date(edition["payload"].get("scheduled_at"))
    if scheduled and now >= scheduled:
        raise RuntimeError("A saved scheduled-send payload is now in the past. Check Resend before reconciliation; it will not be silently changed or duplicated.")
    if edition.get("send_attempts", 0) >= 3:
        raise RuntimeError("Three send attempts already recorded. Check Resend before any further retry.")
    if not resend_key:
        raise RuntimeError("Missing RESEND_API_KEY")
    edition.setdefault("first_attempt", iso(now))
    edition["send_attempts"] = edition.get("send_attempts", 0) + 1
    store.save()  # Durable intent before the external side effect.
    response = api.call("Resend", "POST", "https://api.resend.com/emails", resend_key,
                        edition["payload"], {"Idempotency-Key": edition["idempotency_key"]})
    if not isinstance(response.get("id"), str) or not response["id"]:
        raise RuntimeError("Resend returned no email ID. Check its dashboard before retrying.")
    edition["email_id"], edition["status"], edition["accepted_at"] = response["id"], "queued", iso(clock())
    if edition["production"]:
        apply_coverage(store.data, edition)
    # If this save fails, recovery reuses the SAME saved payload and idempotency key.
    store.save()
    return response["id"]


def run(mode: str, cfg: dict, store, api, client, keys: dict, output: Path,
        run_id: str, clock=utcnow, collector=collect, pinger=ping) -> str:
    if mode not in {"preview", "send-test", "scheduled", "send-edition", "arm-monitor"}:
        raise ValueError("Use check_sources() for a collection-only check; run() only accepts newsletter modes.")
    now = clock()
    production = production_mode(mode)
    if mode == "arm-monitor":
        if not cfg["enabled"]:
            raise RuntimeError("Enable NEWSLETTER_ENABLED before arming monitoring.")
        good_tests = [value for name, value in store.data["editions"].items()
                      if name.startswith("send-test-") and value.get("status") == "queued"
                      and value.get("health_ok") and value.get("briefing", {}).get("status") in {"briefing", "quiet"}
                      and (parse_date(value.get("created")) or now - timedelta(days=2)) >= now - timedelta(days=1)]
        if not good_tests:
            raise RuntimeError("Monitoring requires a successful full send-test from the last 24 hours, with a non-fallback newsletter and adequate source coverage.")
        # This is an explicit setup heartbeat, not a claim that a scheduled run occurred.
        pinger(keys.get("healthchecks", ""), True)
        store.data["monitor_armed_at"] = iso(now)
        store.save()
        print("Monitoring armed after a successful test. No news email sent or production history advanced.")
        return "monitor_armed"
    if production:
        if not cfg["enabled"]:
            print("Automatic delivery disabled. Set NEWSLETTER_ENABLED=true only after a successful preview/test.")
            return "disabled"
        local = now.astimezone(ZoneInfo(cfg["timezone"]))
        if local.weekday() >= 5:
            print("No production edition on weekends.")
            return "weekend"
        if local.hour >= cfg["scheduled_latest_hour"]:
            raise RuntimeError("Production preparation started after the noon safety cutoff. No stale edition was sent.")
        if local.hour < 6:
            raise RuntimeError("Production runs must start between 06:00 and noon in the configured timezone.")
    key = now.astimezone(ZoneInfo(cfg["timezone"])).strftime("%Y-%m-%d") if production else f"{mode}-{run_id}"
    prune(store, now)
    previous = store.data["editions"].get(key)
    if previous and previous.get("status") == "queued":
        if previous.get("payload"):
            write_outputs(output, previous["payload"], previous["briefing"], previous["report"], Budget(store, cfg, now).used())
        if production:
            pinger(keys.get("healthchecks", ""), previous.get("health_ok", True))
        print("Edition was already accepted by Resend; no duplicate email requested.")
        return "already_queued"
    if previous is None:
        sources = load_json(ROOT / "config/sources.json")
        watchlist = load_json(ROOT / "config/watchlist.json")
        aliases = [alias for row in watchlist["entities"] for alias in row["aliases"]]
        articles, report = collector(client, sources, aliases, store.data["seen"], now, cfg, store.data["initialised"])
        report["run_mode"] = mode
        report["diagnostics_version"] = 2
        report["collection_status"] = collection_status(report)
        briefing = edit(articles, report, cfg, store, now, key, api, keys.get("openai", ""))
        prepared_at = clock()
        delayed = production and prepared_at >= target_time(prepared_at, cfg)
        if production and prepared_at.astimezone(ZoneInfo(cfg["timezone"])).hour >= cfg["scheduled_latest_hour"]:
            raise RuntimeError("Preparation passed the noon cutoff. No production email was queued.")
        payload = render(briefing, report, cfg, prepared_at, test=(mode == "send-test"), delayed=delayed)
        target = target_time(prepared_at, cfg)
        if production and target > prepared_at + timedelta(seconds=45):
            payload["scheduled_at"] = iso(target)
        ids = set(briefing["assessed_ids"])
        reviewed = {a.id: {"fingerprint": a.fingerprint,
                           "feed_fingerprint": report.get("feed_fingerprints", {}).get(a.id, ""),
                           "checked": iso(prepared_at)} for a in articles if a.id in ids}
        report = {k: v for k, v in report.items() if k != "feed_fingerprints"}
        edition = {"created": iso(prepared_at), "production": production,
                   "status": "preview" if mode == "preview" else "prepared",
                   "payload": payload, "briefing": clean_briefing(briefing), "report": report,
                   "reviewed": reviewed, "idempotency_key": f"daily-komotic-briefing/{key}",
                   "health_ok": briefing["status"] != "collection_failure"}
        store.data["editions"][key] = edition
        store.save()
    edition = store.data["editions"][key]
    write_outputs(output, edition["payload"], edition["briefing"], edition["report"], Budget(store, cfg, now).used())
    if mode == "preview":
        print("Preview saved. No email sent, no production coverage advanced, and no Healthchecks signal sent.")
        return "preview"
    deliver(store, key, api, keys.get("resend", ""), clock)
    if production:
        pinger(keys.get("healthchecks", ""), edition["health_ok"])
    print("Resend accepted the email. Acceptance is not confirmation of inbox delivery.")
    return "queued"



def collection_status(report: dict) -> str:
    if report.get("fatal_collection"):
        return "failed"
    return "ok" if report.get("healthy_sources", 0) == report.get("total_sources", 0) else "partial"


def check_sources(cfg: dict, client, output: Path, clock=utcnow, collector=collect) -> dict:
    """Collect diagnostics only. Never create a newsletter or access API credentials/state."""
    watch = load_json(ROOT / "config/watchlist.json")
    aliases = [name for entity in watch["entities"] for name in entity["aliases"]]
    _, report = collector(client, load_json(ROOT / "config/sources.json"), aliases, {}, clock(), cfg, False)
    report.pop("feed_fingerprints", None)
    report.update({"run_mode": "check-sources", "diagnostics_version": 2,
                   "collection_status": collection_status(report), "edition_status": "not_generated",
                   "analysis": analysis_record("not_requested")})
    output.mkdir(parents=True, exist_ok=True)
    # A reused local output directory must not attach a stale preview newsletter.
    for name in ("newsletter.html", "newsletter.txt"):
        (output / name).unlink(missing_ok=True)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def write_run_summary(mode: str, result: str, output: Path) -> None:
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    report_path = output / "report.json"
    report = load_json(report_path) if report_path.exists() else {}
    with open(summary, "a", encoding="utf-8") as handle:
        handle.write(f"## Daily Komotic Briefing\n\nMode: `{mode}`. Execution result: `{result}`.\n\n")
        if mode == "check-sources":
            handle.write(f"Collection: `{report.get('collection_status', 'unknown')}`. No newsletter generated and no model request made.\n\n")
            handle.write("Download `report.json`. This mode does not test newsletter generation.\n")
        elif mode == "arm-monitor":
            handle.write("Monitoring setup heartbeat only; no newsletter generated.\n")
        elif report:
            analysis = report.get("analysis", {})
            handle.write(f"Edition: `{report.get('edition_status', 'unknown')}`. Analysis: `{analysis.get('status', 'not_recorded')}`.\n\n")
            handle.write(f"Candidates submitted: {analysis.get('candidates_submitted', 'not_recorded')}. "
                         f"Proposals: {analysis.get('proposed_items', 'not_recorded')}. "
                         f"Accepted: {analysis.get('accepted_items', 'not_recorded')}. "
                         f"Rejected: {analysis.get('rejected_items', 'not_recorded')}.\n\n")
            if report.get("edition_status") == "links_only":
                handle.write("**Fallback, not a completed briefing.** Inspect `analysis.validation_errors` and `fallback_reason` in `report.json`.\n\n")
            handle.write("Download `newsletter.html`, `newsletter.txt` and `report.json`. "
                         "A successful send confirms API acceptance, not inbox delivery.\n")


def demo(output: Path) -> None:
    cfg = settings()
    fixture = load_json(ROOT / "tests/fixtures/demo.json")
    now = parse_date(fixture["now"])
    payload = render(fixture["briefing"], fixture["report"], cfg, now, demo=True)
    write_outputs(output, payload, fixture["briefing"], fixture["report"])
    print("Fictional layout example saved; no external services used.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily Komotic Briefing")
    parser.add_argument("mode", choices=["preview", "send-test", "scheduled", "send-edition", "check-sources", "arm-monitor", "demo"])
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--local-state", type=Path)
    args = parser.parse_args()
    cfg = settings()
    if args.mode == "demo":
        demo(args.output)
        return 0
    if production_mode(args.mode) and not cfg["enabled"]:
        print("Delivery disabled: NEWSLETTER_ENABLED is not true.")
        return 0
    api = APIs()
    client = PublicClient()
    if args.mode == "check-sources":
        report = check_sources(cfg, client, args.output)
        print(f"Sources checked: {report['healthy_sources']}/{report['total_sources']} successful. No model request, email, state write or Healthchecks signal.")
        write_run_summary("check-sources", report["collection_status"], args.output)
        return 1 if report["fatal_collection"] else 0
    store = store_from_environment(api, args.local_state)
    keys = {"openai": os.getenv("OPENAI_API_KEY", "").strip(), "resend": os.getenv("RESEND_API_KEY", "").strip(),
            "healthchecks": os.getenv("HEALTHCHECKS_PING_URL", "").strip()}
    # A unique local run identifier prevents unrelated tests sharing an outbox key.
    run_id = os.getenv("GITHUB_RUN_ID") or utcnow().strftime("%Y%m%dT%H%M%S%f")
    status = run(args.mode, cfg, store, api, client, keys, args.output, run_id)
    write_run_summary(args.mode, status, args.output)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (APIError, RuntimeError, ValueError) as error:
        print(f"BRIEFING FAILED: {error}", file=sys.stderr)
        sys.exit(1)
