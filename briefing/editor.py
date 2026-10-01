from __future__ import annotations

import json
import re
from collections import defaultdict

from jsonschema import Draft202012Validator

from .common import ROOT, clean, load_json
from .evidence import quote_mismatch, quote_options, submitted_context
from .http import APIError
from .language import non_english_language
from .sources import Article
from .state import Budget


def analysis_record(status: str = "not_started") -> dict:
    """Public diagnostics: counts and check codes, never raw model output or quotes."""
    return {"status": status, "evidence_version": 1, "evidence_options_offered": 0,
            "model_requested": False, "candidates_submitted": 0,
            "proposed_items": 0, "accepted_items": 0, "rejected_items": 0,
            "skipped_items": 0, "validation_errors": [], "skipped": []}


def fallback(articles: list[Article], reason: str, status: str = "links_only", *,
             warnings: list[str] | None = None, analysis: dict | None = None) -> dict:
    return {"status": status, "items": [], "links": [a.record() for a in articles[:5]],
            "note": reason, "warnings": list(warnings or []), "assessed_ids": [],
            "analysis": analysis if analysis is not None else analysis_record("not_run")}


def make_payload(articles: list[Article], history: list[dict], cfg: dict) -> dict:
    profile = (ROOT / "config/komotic.md").read_text(encoding="utf-8")
    editorial = (ROOT / "config/editorial.md").read_text(encoding="utf-8")
    material = [{"id": a.id, "title": a.title, "source": a.source, "source_kind": a.source_kind,
                 "region": a.region, "language": a.language, "published": a.published,
                 "access": a.access, "excerpt": a.excerpt[:cfg["model_excerpt_chars"]]} for a in articles]
    schema = load_json(ROOT / "config/briefing.schema.json")
    fields = schema["properties"]["items"]["items"]["properties"]
    branches = []
    for a in articles:
        quotes = quote_options(a, cfg["model_excerpt_chars"])
        if not quotes:
            raise ValueError("Source has no usable verbatim evidence spans")
        branches.append({"type": "object", "properties": {
            "source_id": {"type": "string", "enum": [a.id]},
            "quote": {"type": "string", "enum": quotes,
                      "description": "Choose an exact ORIGINAL-language source span supporting this event. Never translate."}},
            "required": ["source_id", "quote"], "additionalProperties": False})
    if not branches:
        raise ValueError("Evidence-constrained requests require at least one source")
    fields["evidence"]["items"] = {"anyOf": branches}
    fields["source_ids"]["items"]["enum"] = [a.id for a in articles]
    return {"model": cfg["model"], "store": False, "max_output_tokens": cfg["max_output_tokens"],
            "input": [
                {"role": "system", "content": editorial + "\n\nTrusted Komotic context:\n" + profile},
                {"role": "user", "content": json.dumps({"untrusted_source_material": material,
                    "previously_reported_events": history[-35:]}, ensure_ascii=False)}],
            "text": {"format": {"type": "json_schema", "name": "komotic_briefing", "strict": True,
                                "schema": schema}}}


def number_tokens(text: str) -> set[str]:
    return {m.replace(",", "").lower() for m in re.findall(r"\d+(?:[.,]\d+)*(?:%|[kmb])?", text, re.I)}


def validate_selection(data: dict, articles: list[Article], history: list[dict], cfg: dict,
                       diagnostics: dict | None = None) -> tuple[list[dict], list[str]]:
    diagnostics = diagnostics if diagnostics is not None else analysis_record()
    schema = load_json(ROOT / "config/briefing.schema.json")
    schema_errors = list(Draft202012Validator(schema).iter_errors(data))
    if schema_errors:
        # jsonschema messages can contain the rejected text. Export only the
        # validator name, not its message, instance, extra property or value.
        diagnostics["status"] = "schema_invalid"
        diagnostics["validation_errors"] = [{"item": None, "source_ids": [], "checks": [
            {"code": "schema_invalid", "validator": error.validator} for error in schema_errors[:10]]}]
        raise ValueError("Model output did not match the expected schema")
    available = {a.id: a for a in articles}
    prior = {row["event_key"] for row in history}
    used_sources, used_events = set(), set()
    selected, warnings = [], []
    quote_words = defaultdict(int)
    limits = {"headline": 25, "summary": 85, "implication": 55, "action": 25, "new_development": 40}
    diagnostics["proposed_items"] = len(data["items"])
    for index, item in enumerate(data["items"][:5], 1):
        checks: list[dict] = []
        ids = item["source_ids"]
        if not ids or len(ids) != len(set(ids)) or any(k not in available for k in ids):
            checks.append({"code": "invalid_source_ids"})
        # Keep duplicate handling distinct from validation failures.
        skip_reason = ""
        if set(ids) & used_sources or item["event_key"] in used_events:
            skip_reason = "duplicate_in_edition"
        elif item["event_key"] in prior and not item["is_update"]:
            skip_reason = "already_reported"
        if skip_reason:
            diagnostics["skipped_items"] += 1
            diagnostics["skipped"].append({"item": index, "reason": skip_reason})
            continue
        if item["is_update"] and not item["new_development"].strip():
            checks.append({"code": "missing_update_detail"})
        for field, maximum in limits.items():
            actual = len(item[field].split())
            if actual > maximum:
                checks.append({"code": "word_limit_exceeded", "field": field,
                               "actual_words": actual, "maximum_words": maximum})
            if re.search(r"https?://|www\.", item[field], re.I):
                checks.append({"code": "generated_url", "field": field})
            detected = non_english_language(item[field])
            if detected:
                checks.append({"code": "non_english_output", "field": field, "language": detected})
        if not item["evidence"]:
            checks.append({"code": "missing_evidence"})
        cited = set()
        local_counts = defaultdict(int)
        for ev in item["evidence"]:
            sid, quote = ev["source_id"], clean(ev["quote"])
            cited.add(sid)
            count = len(quote.split())
            local_counts[sid] += count
            if sid not in ids or sid not in available:
                checks.append({"code": "invalid_evidence_source"})
                continue
            if count < 4:
                checks.append({"code": "quote_too_short", "source_id": sid, "actual_words": count})
                continue
            context = submitted_context(available[sid], cfg["model_excerpt_chars"])
            if quote not in context:
                checks.append({"code": "quote_not_found", "source_id": sid,
                               **quote_mismatch(quote, available[sid], articles, cfg["model_excerpt_chars"])})
            if local_counts[sid] + quote_words[sid] > 25:
                checks.append({"code": "quote_word_limit_exceeded", "source_id": sid,
                               "actual_words": local_counts[sid] + quote_words[sid], "maximum_words": 25})
        if cited != set(ids):
            checks.append({"code": "evidence_source_mismatch"})
        context = " ".join(available[sid].title + " " + available[sid].excerpt[:cfg["model_excerpt_chars"]]
                           for sid in ids if sid in available)
        unsupported = sorted(number_tokens(item["summary"]) - number_tokens(context))
        if unsupported:
            # Numeric tokens only, not arbitrary rejected text.
            checks.append({"code": "unsupported_number", "field": "summary", "tokens": unsupported})
        if checks:
            diagnostics["rejected_items"] += 1
            diagnostics["validation_errors"].append({"item": index,
                "source_ids": [sid for sid in ids if sid in available], "checks": checks})
            labels = list(dict.fromkeys(check["code"] + ("(" + check["field"] + ")" if "field" in check else "")
                                        for check in checks))
            warnings.append(f"Item {index} was not published: " + ", ".join(labels) + ".")
            continue
        for sid, count in local_counts.items():
            quote_words[sid] += count
        result = {k: v for k, v in item.items() if k != "evidence"}
        result["sources"] = [available[sid].record() for sid in ids]
        result["sources"].sort(key=lambda a: ("Paywalled" in a["access"], "excerpt only" in a["access"].lower(), a["source_kind"] != "official"))
        selected.append(result)
        used_sources.update(ids)
        used_events.add(item["event_key"])
    diagnostics["accepted_items"] = len(selected)
    return selected, warnings


def edit(articles: list[Article], report: dict, cfg: dict, store, now, request_id: str, api, api_key: str) -> dict:
    analysis = analysis_record()

    def fail(reason: str, stage: str, status: str = "links_only", warnings: list[str] | None = None) -> dict:
        analysis["status"] = stage
        return fallback([] if status == "collection_failure" else articles, reason, status,
                        warnings=warnings, analysis=analysis)

    if report["fatal_collection"]:
        return fail("Collection failed or coverage was too incomplete to assess the news. This is not a quiet-day confirmation.",
                    "collection_failed", "collection_failure")
    if not articles:
        analysis["status"] = "no_candidates"
        return {"status": "quiet", "items": [], "links": [],
                "note": "No material developments were identified in the sources and publication window checked.",
                "warnings": [], "assessed_ids": [], "analysis": analysis}
    usable = [a for a in articles if len(a.excerpt) >= 140]
    analysis["candidates_with_usable_text"] = len(usable)
    if not usable:
        return fail("Only headlines or insufficient previews were available. These links have not been assessed or summarised.", "insufficient_text")
    usable = [a for a in usable if quote_options(a, cfg["model_excerpt_chars"])]
    analysis["candidates_with_evidence_options"] = len(usable)
    if not usable:
        return fail("No usable verbatim source spans were available for evidence selection. Source links have not been assessed or summarised.",
                    "insufficient_evidence")
    if not api_key:
        return fail("OpenAI is not configured. Source links are provided without generated analysis.", "missing_api_key")
    payload = make_payload(usable, store.data["history"], cfg)
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > cfg["max_model_request_bytes"]:
        return fail("The input exceeded the configured request-size guard; no paid model request was made.", "request_size_guard")
    budget = Budget(store, cfg, now)
    permitted, reason = budget.reserve(request_id, payload)
    if not permitted:
        return fail(reason, "budget_or_repeat_guard")
    analysis["model_requested"] = True
    analysis["candidates_submitted"] = len(usable)
    branches = payload["text"]["format"]["schema"]["properties"]["items"]["items"]["properties"]["evidence"]["items"]["anyOf"]
    analysis["evidence_options_offered"] = sum(len(b["properties"]["quote"]["enum"]) for b in branches)
    try:
        response = api.call("OpenAI", "POST", "https://api.openai.com/v1/responses", api_key, payload)
    except APIError as error:
        return fail(f"Analysis unavailable ({error}). No automatic paid retry was made.", "api_error")
    budget.settle(request_id, response.get("usage", {}))
    if response.get("status") != "completed":
        return fail("The model response did not complete. These source links are unassessed; no unsupported summary was sent.", "response_incomplete")
    try:
        text = "".join(part.get("text", "") for row in response.get("output", []) if isinstance(row, dict)
                       for part in row.get("content", []) if isinstance(part, dict) and part.get("type") == "output_text")
        data = json.loads(text)
    except (ValueError, KeyError, TypeError):
        return fail("Analysis could not be decoded. These source links are unassessed; no unsupported summary was sent.", "response_not_json")
    try:
        selected, warnings = validate_selection(data, usable, store.data["history"], cfg, analysis)
    except (ValueError, KeyError, TypeError):
        stage = "schema_invalid" if analysis["status"] == "schema_invalid" else "validation_error"
        return fail("Analysis failed validation. These source links are unassessed; no unsupported summary was sent.", stage)
    if not selected and warnings:
        return fail("Proposed summaries failed evidence or format checks. Source links are provided without generated analysis.",
                    "validation_failed", warnings=warnings)
    analysis["status"] = "completed_with_rejections" if warnings else "completed"
    # Failed proposals must remain eligible for a future run rather than being
    # silently marked as fully assessed. Non-selected candidates were assessed.
    rejected_ids = {sid for entry in analysis["validation_errors"] for sid in entry.get("source_ids", [])}
    result = {"status": "briefing" if selected else "quiet", "items": selected, "links": [],
              "note": "" if selected else "No material developments were identified in the sources and publication window checked.",
              "warnings": warnings, "assessed_ids": [a.id for a in usable if a.id not in rejected_ids], "analysis": analysis}
    if len(usable) != len(articles):
        result["warnings"].append(f"{len(articles) - len(usable)} candidate items lacked enough source text for analysis.")
    return result
