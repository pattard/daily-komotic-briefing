from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .common import parse_date


def esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def short_date(value: str) -> str:
    when = parse_date(value)
    return when.strftime("%d-%m-%Y") if when else "Publication date unavailable"


def render(briefing: dict, report: dict, cfg: dict, now: datetime, test: bool = False,
           delayed: bool = False, demo: bool = False) -> dict:
    day = now.astimezone(ZoneInfo(cfg["timezone"])).strftime("%d-%m-%Y")
    subject = f"Daily Komotic Briefing | {day}"
    if test:
        subject = "[TEST] " + subject
    if delayed:
        subject = "[DELAYED] " + subject
    if briefing["status"] == "collection_failure":
        subject = "[COLLECTION FAILED] " + subject
    elif briefing["status"] == "links_only":
        subject = "[LINKS ONLY] " + subject
    blocks: list[str] = []
    lines = ["DAILY KOMOTIC BRIEFING", day, ""]
    if demo:
        notice = "FICTIONAL EXAMPLE: layout demonstration only. These are invented companies and events, not news."
        blocks.append(f'<p style="padding:14px;background:#fff0c2;font-weight:bold">{esc(notice)}</p>')
        lines.extend([notice, ""])
    if test:
        notice = "Test edition. This does not enable the weekday schedule or advance production coverage history."
        blocks.append(f'<p style="padding:12px;background:#eef2f6">{esc(notice)}</p>')
        lines.extend([notice, ""])
    if delayed:
        notice = "The preparation job started late. This edition is being sent after the intended 08:00 delivery time."
        blocks.append(f'<p style="padding:12px;background:#fff0c2">{esc(notice)}</p>')
        lines.extend([notice, ""])
    if briefing.get("note"):
        blocks.append(f'<p style="font-size:17px;line-height:1.55">{esc(briefing["note"])}</p>')
        lines.extend([briefing["note"], ""])
    for index, item in enumerate(briefing["items"], 1):
        sources = item["sources"]
        lead = sources[0]
        label = item["category"] + (" / Material update" if item["is_update"] else "")
        content = [f'<p style="color:#536476;font-size:12px;letter-spacing:1px;text-transform:uppercase;margin:0 0 7px">{index:02d} / {esc(label)}</p>',
                   f'<h2 style="font-size:22px;line-height:1.25;margin:0 0 12px"><a href="{esc(lead["url"])}" style="color:#182d42;text-decoration:none">{esc(item["headline"])}</a></h2>',
                   f'<p style="margin:0 0 10px;line-height:1.55">{esc(item["summary"])}</p>',
                   f'<p style="margin:0 0 10px;line-height:1.55"><strong>Why it matters to Komotic:</strong> {esc(item["implication"])}</p>']
        lines.extend([f"{index}. {item['headline']} [{label}]", item["summary"],
                      "Why it matters to Komotic: " + item["implication"]])
        if item["action"]:
            content.append(f'<p style="margin:0 0 10px;line-height:1.55"><strong>Consider:</strong> {esc(item["action"])}</p>')
            lines.append("Consider: " + item["action"])
        for source in sources:
            meta = f"{source['source']} | {short_date(source['published'])} | {source['access']}"
            content.append(f'<p style="font-size:12px;line-height:1.5;margin:6px 0"><a href="{esc(source["url"])}" style="color:#235b79">{esc(meta)}</a></p>')
            lines.extend([meta, source["url"]])
        blocks.append('<section style="padding:25px 0;border-bottom:1px solid #dfe5e8">' + "".join(content) + "</section>")
        lines.append("")
    if briefing.get("links"):
        blocks.append('<h2 style="font-size:20px">Source links, not assessed summaries</h2>')
        lines.extend(["SOURCE LINKS, NOT ASSESSED SUMMARIES", ""])
        for source in briefing["links"]:
            label = f"{source['source']} | {short_date(source['published'])} | {source['access']}"
            blocks.append(f'<p style="line-height:1.5"><a href="{esc(source["url"])}" style="color:#235b79">{esc(source["title"])}</a><br><span style="font-size:12px;color:#536476">{esc(label)}</span></p>')
            lines.extend([source["title"], label, source["url"], ""])
    warnings = report.get("warnings", []) + briefing.get("warnings", [])
    coverage = f"Coverage: {report.get('healthy_sources', 0)}/{report.get('total_sources', 0)} configured sources checked successfully."
    count = len(briefing.get("assessed_ids", []))
    analysis = briefing.get("analysis")
    if analysis is not None:
        count = analysis.get("candidates_submitted", 0)
        assessed = (f"{count} candidate{'s' if count != 1 else ''} submitted for model analysis; "
                    f"{analysis.get('accepted_items', 0)} newsletter items passed publication checks. "
                    "Collection is selective, not exhaustive.")
    else:
        assessed = f"{count} candidate{'s' if count != 1 else ''} assessed by the model; collection is selective, not exhaustive."
    if warnings:
        blocks.append('<div style="margin-top:22px;padding:14px;background:#fff4dd"><strong>Coverage / processing notes</strong>' +
                      "".join(f'<p style="font-size:13px;line-height:1.5;margin:7px 0">{esc(note)}</p>' for note in warnings[:10]) +
                      (f'<p>{len(warnings) - 10} further notes are in the run report.</p>' if len(warnings) > 10 else "") + '</div>')
        lines.extend(["COVERAGE / PROCESSING NOTES"] + warnings + [""])
    cutoff = parse_date(report.get("window_end"))
    cutoff_text = ""
    if cutoff:
        cutoff_text = "Collection cutoff: " + cutoff.astimezone(ZoneInfo(cfg["timezone"])).strftime("%d-%m-%Y %H:%M") + " " + cfg["timezone"] + "."
    footer = [coverage, assessed, cutoff_text, "Reported developments and our interpretation are kept separate. Open the sources for the underlying reporting."]
    blocks.append('<footer style="margin-top:28px;border-top:2px solid #182d42;padding-top:15px;color:#536476;font-size:12px;line-height:1.6">' +
                  "".join(f'<p style="margin:5px 0">{esc(text)}</p>' for text in footer if text) + '</footer>')
    lines.extend(footer)
    document = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>' + esc(subject) + '</title></head>'
                '<body style="margin:0;background:#f4f6f7;color:#253341;font-family:Arial,Helvetica,sans-serif;font-size:15px">'
                '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center" style="padding:24px 12px">'
                '<table role="presentation" width="640" cellspacing="0" cellpadding="0" style="width:100%;max-width:640px;background:white"><tr><td style="padding:30px">'
                '<p style="margin:0;color:#536476;font-size:12px;letter-spacing:2px">KOMOTIC / INDUSTRY INTELLIGENCE</p>'
                '<h1 style="margin:10px 0 8px;color:#182d42;font-size:31px;line-height:1.15">Daily briefing</h1>'
                '<p style="margin:0 0 23px;color:#536476">' + esc(day) + ' / Comics business and platforms</p>' +
                "".join(blocks) + '</td></tr></table></td></tr></table></body></html>')
    return {"from": cfg["email_from"], "to": [cfg["email_to"]], "subject": subject,
            "html": document, "text": "\n".join(lines)}


def write_outputs(directory: Path, payload: dict, briefing: dict, report: dict, budget_usd: float = 0) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "newsletter.html").write_text(payload["html"], encoding="utf-8")
    (directory / "newsletter.txt").write_text(payload["text"], encoding="utf-8")
    # Never export full source excerpts, raw model responses, API keys or ping URLs.
    public_report = {k: v for k, v in report.items() if k != "feed_fingerprints"}
    public_report.update({"edition_status": briefing["status"], "estimated_monthly_model_usd": round(budget_usd, 6),
                          "selected_headlines": [item["headline"] for item in briefing["items"]],
                          "editorial_warnings": briefing.get("warnings", []),
                          "fallback_reason": briefing.get("note", "") if briefing["status"] in ("links_only", "collection_failure") else "",
                          "analysis": briefing.get("analysis", {"status": "not_recorded"})})
    (directory / "report.json").write_text(json.dumps(public_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
