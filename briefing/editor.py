from __future__ import annotations

import json
import re
from collections import defaultdict

from jsonschema import Draft202012Validator

from .common import ROOT, clean, load_json
from .http import APIError
from .sources import Article
from .state import Budget


def fallback(articles: list[Article], reason: str, status: str = "links_only") -> dict:
    return {"status": status, "items": [], "links": [a.record() for a in articles[:5]],
            "note": reason, "warnings": [], "assessed_ids": []}


def make_payload(articles: list[Article], history: list[dict], cfg: dict) -> dict:
    profile = (ROOT / "config/komotic.md").read_text(encoding="utf-8")
    editorial = (ROOT / "config/editorial.md").read_text(encoding="utf-8")
    material = [{"id": a.id, "title": a.title, "source": a.source, "source_kind": a.source_kind,
                 "region": a.region, "language": a.language, "published": a.published,
                 "access": a.access, "excerpt": a.excerpt[:cfg["model_excerpt_chars"]]} for a in articles]
    return {"model": cfg["model"], "store": False, "max_output_tokens": cfg["max_output_tokens"],
            "input": [
                {"role": "system", "content": editorial + "\n\nTrusted Komotic context:\n" + profile},
                {"role": "user", "content": json.dumps({"untrusted_source_material": material,
                    "previously_reported_events": history[-35:]}, ensure_ascii=False)}],
            "text": {"format": {"type": "json_schema", "name": "komotic_briefing", "strict": True,
                                "schema": load_json(ROOT / "config/briefing.schema.json")}}}


def number_tokens(text: str) -> set[str]:
    return {m.replace(",", "").lower() for m in re.findall(r"\d+(?:[.,]\d+)*(?:%|[kmb])?", text, re.I)}


def validate_selection(data: dict, articles: list[Article], history: list[dict], cfg: dict) -> tuple[list[dict], list[str]]:
    schema = load_json(ROOT / "config/briefing.schema.json")
    if list(Draft202012Validator(schema).iter_errors(data)):
        raise ValueError("Model output did not match the expected schema")
    available = {a.id: a for a in articles}
    prior = {row["event_key"] for row in history}
    used_sources, used_events = set(), set()
    selected, warnings = [], []
    quote_words = defaultdict(int)
    limits = {"headline": 25, "summary": 85, "implication": 55, "action": 25, "new_development": 40}
    for item in data["items"][:5]:
        invalid = False
        ids = item["source_ids"]
        if not ids or len(ids) != len(set(ids)) or any(k not in available for k in ids):
            invalid = True
        if set(ids) & used_sources or item["event_key"] in used_events:
            continue
        if item["event_key"] in prior and not item["is_update"]:
            continue
        if item["is_update"] and not item["new_development"].strip():
            invalid = True
        for field, maximum in limits.items():
            if len(item[field].split()) > maximum or re.search(r"https?://|www\.", item[field], re.I):
                invalid = True
        if not item["evidence"]:
            invalid = True
        cited = set()
        local_counts = defaultdict(int)
        for ev in item["evidence"]:
            sid, quote = ev["source_id"], clean(ev["quote"])
            cited.add(sid)
            local_counts[sid] += len(quote.split())
            if sid not in ids or sid not in available or len(quote.split()) < 4:
                invalid = True
                continue
            context = clean(available[sid].title + " " + available[sid].excerpt[:cfg["model_excerpt_chars"]])
            if quote not in context:
                invalid = True
            if local_counts[sid] + quote_words[sid] > 25:
                invalid = True
        if cited != set(ids):
            invalid = True
        context = " ".join(available[sid].title + " " + available[sid].excerpt[:cfg["model_excerpt_chars"]]
                           for sid in ids if sid in available)
        if not number_tokens(item["summary"]) <= number_tokens(context):
            invalid = True
        if invalid:
            warnings.append("An item failed source/format validation and was not published.")
            continue
        for sid, count in local_counts.items():
            quote_words[sid] += count
        result = {k: v for k, v in item.items() if k != "evidence"}
        result["sources"] = [available[sid].record() for sid in ids]
        # Prefer accessible substantive material over a paywalled preview.
        result["sources"].sort(key=lambda a: ("Paywalled" in a["access"], "excerpt only" in a["access"].lower(), a["source_kind"] != "official"))
        selected.append(result)
        used_sources.update(ids)
        used_events.add(item["event_key"])
    return selected, warnings


def edit(articles: list[Article], report: dict, cfg: dict, store, now, request_id: str, api, api_key: str) -> dict:
    if report["fatal_collection"]:
        return fallback([], "Collection failed or coverage was too incomplete to assess the news. This is not a quiet-day confirmation.", "collection_failure")
    if not articles:
        return {"status": "quiet", "items": [], "links": [], "note": "No material developments were identified in the sources and publication window checked.", "warnings": [], "assessed_ids": []}
    usable = [a for a in articles if len(a.excerpt) >= 140]
    if not usable:
        return fallback(articles, "Only headlines or insufficient previews were available. These links have not been assessed or summarised.")
    if not api_key:
        return fallback(articles, "OpenAI is not configured. Source links are provided without generated analysis.")
    payload = make_payload(usable, store.data["history"], cfg)
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > cfg["max_model_request_bytes"]:
        return fallback(articles, "The input exceeded the configured request-size guard; no paid model request was made.")
    budget = Budget(store, cfg, now)
    permitted, reason = budget.reserve(request_id, payload)
    if not permitted:
        return fallback(articles, reason)
    try:
        response = api.call("OpenAI", "POST", "https://api.openai.com/v1/responses", api_key, payload)
    except APIError as error:
        return fallback(articles, f"Analysis unavailable ({error}). No automatic paid retry was made.")
    budget.settle(request_id, response.get("usage", {}))
    try:
        if response.get("status") != "completed":
            raise ValueError("Model response was incomplete")
        text = "".join(part.get("text", "") for row in response.get("output", []) if isinstance(row, dict)
                       for part in row.get("content", []) if isinstance(part, dict) and part.get("type") == "output_text")
        selected, warnings = validate_selection(json.loads(text), usable, store.data["history"], cfg)
    except (ValueError, KeyError, TypeError):
        return fallback(articles, "Analysis failed validation. These source links are unassessed; no unsupported summary was sent.")
    if not selected and warnings:
        return fallback(articles, "Proposed summaries failed evidence checks. Source links are provided without generated analysis.")
    result = {"status": "briefing" if selected else "quiet", "items": selected, "links": [],
              "note": "" if selected else "No material developments were identified in the sources and publication window checked.",
              "warnings": warnings, "assessed_ids": [a.id for a in usable]}
    if len(usable) != len(articles):
        result["warnings"].append(f"{len(articles) - len(usable)} candidate items lacked enough source text for analysis.")
    return result
