from __future__ import annotations

import concurrent.futures
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from time import monotonic
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from defusedxml import ElementTree

from .common import canonical_url, clean, digest, iso, parse_date
from .http import FetchError, PublicClient


@dataclass
class Article:
    id: str
    title: str
    url: str
    source: str
    source_kind: str
    region: str
    language: str
    published: str = ""
    updated: str = ""
    excerpt: str = ""
    access: str = "Feed excerpt only"
    fingerprint: str = ""
    score: int = 0

    def record(self) -> dict:
        return asdict(self)

    def refresh_fingerprint(self) -> None:
        self.fingerprint = digest(self.title + "|" + self.updated + "|" + self.excerpt[:4000])


def plain_html(text: str) -> str:
    soup = BeautifulSoup(text or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return clean(soup.get_text(" "))


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(element, names: tuple[str, ...]) -> str:
    for name in names:
        for child in element:
            if local_name(child.tag) == name:
                return "".join(child.itertext())
    return ""


def article(source: dict, title: str, url: str, published: str = "", excerpt: str = "", updated: str = "") -> Article:
    url = canonical_url(urljoin(source["url"], url))
    published_date = parse_date(published)
    updated_date = parse_date(updated)
    result = Article(
        id=digest(url), title=plain_html(title)[:280], url=url,
        source=source["name"], source_kind=source["source_kind"], region=source["region"],
        language=source["language"], published=iso(published_date) if published_date else "",
        updated=iso(updated_date) if updated_date else "", excerpt=plain_html(excerpt)[:8500],
    )
    result.refresh_fingerprint()
    return result


def parse_feed(body: bytes, source: dict) -> list[Article]:
    root = ElementTree.fromstring(body)
    if local_name(root.tag) not in ("rss", "feed", "rdf"):
        raise ValueError("Response is not an RSS or Atom feed")
    results: list[Article] = []
    for entry in root.iter():
        if local_name(entry.tag) not in ("item", "entry"):
            continue
        link = child_text(entry, ("link",))
        for node in entry:
            if local_name(node.tag) == "link" and node.attrib.get("href") and node.attrib.get("rel", "alternate") == "alternate":
                link = node.attrib["href"]
                break
        if not link:
            candidate = child_text(entry, ("guid", "id"))
            link = candidate if candidate.startswith(("https://", "http://")) else ""
        title = child_text(entry, ("title",))
        if not title or not link:
            continue
        try:
            results.append(article(source, title, link,
                child_text(entry, ("pubdate", "published", "date")),
                child_text(entry, ("encoded", "content", "description", "summary")),
                child_text(entry, ("updated", "modified"))))
        except (ValueError, TypeError):
            continue
    return results[:150]


def find_date_in_text(text: str) -> str:
    patterns = [r"\b\d{4}-\d{2}-\d{2}(?:T[^\s]+)?", r"\b\d{2}\.\d{2}\.\d{4}\b",
                r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b"]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match and parse_date(match.group()):
            return match.group()
    return ""


def parse_listing(body: bytes, source: dict) -> list[Article]:
    soup = BeautifulSoup(body, "html.parser")
    pattern = re.compile(source["article_url_pattern"])
    results: dict[str, Article] = {}
    for link in soup.select("a[href]"):
        href = urljoin(source["url"], link.get("href", ""))
        title = clean(link.get_text(" "))
        if not pattern.search(href) or len(title) < 18 or title.lower() in {"read more", "continue reading"}:
            continue
        published = ""
        ancestor = link
        for _ in range(4):
            if ancestor is None:
                break
            time_tag = ancestor.find("time")
            if time_tag:
                published = time_tag.get("datetime") or find_date_in_text(time_tag.get_text(" "))
            context = clean(ancestor.get_text(" "))
            if not published and len(context) < 1600:
                published = find_date_in_text(context)
            if published:
                break
            ancestor = ancestor.parent
        try:
            item = article(source, title, href, published)
            results.setdefault(item.id, item)
        except ValueError:
            pass
    return list(results.values())[:40]


def extract_page(item: Article, body: bytes) -> Article:
    soup = BeautifulSoup(body, "html.parser")
    # Only explicitly published dates qualify; a site's current date or last-modified
    # timestamp is not evidence that an old article is new.
    if not item.published:
        for selector, attribute in (("meta[property='article:published_time']", "content"),
                                    ("meta[name='date']", "content"),
                                    ("meta[itemprop='datePublished']", "content"),
                                    ("time[datetime]", "datetime")):
            tag = soup.select_one(selector)
            when = parse_date(tag.get(attribute, "")) if tag else None
            if when:
                item.published = iso(when)
                break
    raw = body.decode("utf-8", errors="replace")
    if not item.published:
        match = re.search(r'"datePublished"\s*:\s*"([^"<>]+)"', raw)
        when = parse_date(match.group(1)) if match else None
        if when:
            item.published = iso(when)
    paywall = bool(re.search(r'"isAccessibleForFree"\s*:\s*(?:false|"false")', raw, re.I))
    paywall = paywall or bool(soup.select_one(".paywall, #paywall, [data-paywall='true']"))
    paywall = paywall or bool(re.search(r"subscribe to (?:read|continue reading) (?:the|this) (?:full )?article|this article is for subscribers", soup.get_text(" "), re.I))
    if paywall:
        description = soup.select_one("meta[name='description'], meta[property='og:description']")
        # Do not read hidden/full content behind a subscription marker.
        if not item.excerpt and description:
            item.excerpt = plain_html(description.get("content", ""))[:2500]
        item.access = "Paywalled: public preview only"
    else:
        for tag in soup.select("script, style, noscript, template, nav, footer, header, aside, form, .comments, #comments, .sharedaddy, .related-posts"):
            tag.decompose()
        containers = soup.select("[itemprop='articleBody'], .entry-content, .article-body, .article-content, .view-body, .notice_detail, .notice_detail_wrap, article, main")
        text = ""
        for node in containers:
            paragraphs = [clean(p.get_text(" ")) for p in node.select("p, h2, h3, li")]
            candidate = "\n".join(p for p in paragraphs if len(p) > 35)
            if len(candidate) > len(text):
                text = candidate
        if len(text) >= 300:
            item.excerpt = text[:8500]
            item.access = "Public text extracted"
        elif item.excerpt:
            item.access = "Feed excerpt only"
        else:
            description = soup.select_one("meta[name='description'], meta[property='og:description']")
            item.excerpt = plain_html(description.get("content", ""))[:2000] if description else ""
            item.access = "Public preview only"
    item.refresh_fingerprint()
    return item


STRONG = re.compile(r"acquir|acquisi|merg|shutdown|shut(?:s|ting)? down|clos(?:ure|ing)|cease|bankrupt|insolven|funding|invest(?:ment|s|or)|revenue|royalt|commission|creator.{0,20}(?:pay|earn)|moneti[sz]|pricing|ownership|DRM|download|digital.{0,12}(?:market|store|reader)|platform|distribution|distribut(?:or|ion)|licens|partnership|partner(?:s|ed|ing)?\b|publishing house|new publisher|new imprint|imprint|new press|launch(?:es|ed|ing)?|accessib|translation|locali[sz]|print.on.demand|subscription|toolkit|interface|cierre|adquisi|fusi[o\u00f3]n|plataforma|distribu|editorial|rachat|fusion|fermeture|[e\u00e9]diteur|[e\u00e9]dition|num[e\u00e9]rique", re.I)
ROUTINE = re.compile(r"\breview\b|\bpreview\b|solicitation|this week.s comics|new comic book day|\btrailer\b|\bcosplay\b|\brecap\b|\brese[n\u00f1]a\b|\bcritique\b", re.I)


def score_article(item: Article, aliases: list[str]) -> int:
    title, text = item.title.lower(), (item.title + " " + item.excerpt[:2000]).lower()
    signal = len(STRONG.findall(title)) * 4 + min(len(STRONG.findall(text)), 8)
    watched = any(re.search(r"(?<!\w)" + re.escape(name.lower()) + r"(?!\w)", text) for name in aliases)
    score = signal + (3 if watched else 0) + (2 if item.source_kind == "official" else 0)
    if ROUTINE.search(title):
        score -= 10
    if item.region in ("US", "UK", "CA", "EU"):
        score += 1
    return score


def collect(client: PublicClient, sources: list[dict], aliases: list[str], seen: dict,
            now: datetime, cfg: dict, initialised: bool) -> tuple[list[Article], dict]:
    candidate_limit = cfg["max_candidates"]
    if type(candidate_limit) is not int or candidate_limit < 1:
        raise ValueError("max_candidates must be a positive integer")
    fetch_limit = cfg.get("max_article_fetches", candidate_limit * 3)
    time_budget = cfg.get("max_article_fetch_seconds", 240)
    if type(fetch_limit) is not int or fetch_limit < candidate_limit:
        raise ValueError("max_article_fetches must be an integer at least max_candidates")
    if type(time_budget) is not int or time_budget < 1:
        raise ValueError("max_article_fetch_seconds must be a positive integer")
    active = [s for s in sources if s.get("enabled")]
    report = {"sources": [], "warnings": [], "fetched_entries": 0, "undated_omitted": 0,
              "future_omitted": 0, "preselected": 0, "candidate_overflow": 0, "article_fetch_failures": 0,
              "old_omitted": 0, "old_after_fetch": 0, "score_omitted": 0,
              "already_seen_omitted": 0, "candidate_diagnostics": []}
    items: dict[str, Article] = {}

    def one(source):
        try:
            page = client.get(source["url"])
            found = parse_feed(page.body, source) if source["type"] == "rss" else parse_listing(page.body, source)
            # An empty response can indicate a changed site/parser, not a quiet day.
            if not found:
                return source, [], "empty_or_unrecognised_source"
            return source, found, "ok"
        except Exception as error:
            reason = str(error) if isinstance(error, FetchError) else "parse_failure"
            return source, [], reason

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for source, found, status in pool.map(one, active):
            report["sources"].append({"id": source["id"], "name": source["name"], "region": source["region"],
                                      "status": status, "entries": len(found)})
            report["fetched_entries"] += len(found)
            for item in found:
                items.setdefault(item.id, item)
    report["unique_entries"] = len(items)
    lookback = cfg["lookback_days"] if initialised else cfg["initial_lookback_days"]
    cutoff = now - timedelta(days=lookback)
    report["window_start"] = iso(cutoff)
    report["window_end"] = iso(now)
    candidates: list[Article] = []
    for item in items.values():
        published = parse_date(item.published)
        if published and published > now + timedelta(minutes=5):
            report["future_omitted"] += 1
            continue
        if published and published < cutoff:
            report["old_omitted"] += 1
            continue
        # Unchanged already-reviewed records do not consume article/model requests.
        previous = seen.get(item.id, {})
        if previous.get("feed_fingerprint") == item.fingerprint:
            report["already_seen_omitted"] += 1
            continue
        item.score = score_article(item, aliases)
        if item.score >= cfg["candidate_min_score"]:
            candidates.append(item)
        else:
            report["score_omitted"] += 1
    candidates.sort(key=lambda a: (-a.score, a.id))
    report["preselected"] = len(candidates)
    # Reserve up to four EU slots when relevant candidates exist; never pad with
    # irrelevant items solely to satisfy a geographical quota.
    eu = [a for a in candidates if a.region == "EU"][:4]
    rest = [a for a in candidates if a.id not in {x.id for x in eu}]
    # Keep the full ranked queue. A candidate with an unknown publication date
    # can turn out to be old only after its article page has been fetched. Such
    # rejections must not permanently consume slots in the model shortlist.
    candidates = eu + rest
    report["selection_version"] = 2
    report["candidate_limit"] = candidate_limit
    report["article_fetch_limit"] = fetch_limit
    report["article_fetch_time_budget_seconds"] = time_budget
    report["article_fetch_attempts"] = 0
    feed_fingerprints: dict[str, str] = {}

    def expand(item):
        try:
            page = client.get(item.url)
            return extract_page(item, page.body), False
        except (FetchError, ValueError):
            item.access = "Feed excerpt only; article not retrieved"
            return item, True

    expanded: list[Article] = []
    cursor = 0
    started = monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        while cursor < len(candidates) and len(expanded) < candidate_limit:
            attempts_left = fetch_limit - report["article_fetch_attempts"]
            # This is a between-batch deadline. In-flight requests still obey
            # the HTTP client's existing timeout, redirect and pacing limits.
            if attempts_left <= 0 or monotonic() - started >= time_budget:
                break
            batch_size = min(4, candidate_limit - len(expanded), attempts_left)
            batch = candidates[cursor:cursor + batch_size]
            cursor += len(batch)
            report["article_fetch_attempts"] += len(batch)
            for item in batch:
                feed_fingerprints[item.id] = item.fingerprint
            for item, failed in pool.map(expand, batch):
                report["article_fetch_failures"] += int(failed)
                candidate = {"id": item.id, "title": item.title, "source": item.source,
                             "region": item.region, "score": item.score, "published": item.published,
                             "access": item.access, "outcome": "eligible"}
                report["candidate_diagnostics"].append(candidate)
                published = parse_date(item.published)
                if not published:
                    candidate["outcome"] = "undated"
                    report["undated_omitted"] += 1
                    continue
                if published < cutoff:
                    candidate["outcome"] = "old_after_fetch"
                    report["old_omitted"] += 1
                    report["old_after_fetch"] += 1
                    continue
                if published > now + timedelta(minutes=5):
                    candidate["outcome"] = "future_after_fetch"
                    report["future_omitted"] += 1
                    continue
                item.refresh_fingerprint()
                if seen.get(item.id, {}).get("fingerprint") == item.fingerprint:
                    candidate["outcome"] = "already_seen"
                    report["already_seen_omitted"] += 1
                    continue
                expanded.append(item)
    report["article_fetch_elapsed_seconds"] = round(monotonic() - started, 3)
    report["eligible_candidates"] = len(expanded)
    report["backfill_fetches"] = max(0, report["article_fetch_attempts"] - min(report["preselected"], candidate_limit))
    report["candidate_overflow"] = len(candidates) - cursor
    if cursor == len(candidates):
        report["selection_stop_reason"] = "queue_exhausted"
    elif len(expanded) >= candidate_limit:
        report["selection_stop_reason"] = "candidate_limit"
    elif report["article_fetch_attempts"] >= fetch_limit:
        report["selection_stop_reason"] = "article_fetch_limit"
    else:
        report["selection_stop_reason"] = "article_fetch_time_limit"
    report["feed_fingerprints"] = feed_fingerprints
    report["healthy_sources"] = sum(s["status"] == "ok" for s in report["sources"])
    report["total_sources"] = len(active)
    report["fatal_collection"] = (report["healthy_sources"] < cfg["min_healthy_sources"] or
                                  report["healthy_sources"] < len(active) * cfg["min_healthy_fraction"])
    for source in report["sources"]:
        if source["status"] != "ok":
            report["warnings"].append(f"{source['name']}: {source['status']}")
    if report["candidate_overflow"]:
        report["warnings"].append(f"Capacity limit ({report['selection_stop_reason']}): {report['candidate_overflow']} additional preselected items were not checked.")
    if report["undated_omitted"]:
        report["warnings"].append(f"{report['undated_omitted']} items omitted because a publication date could not be established.")
    if report["article_fetch_failures"]:
        report["warnings"].append(f"{report['article_fetch_failures']} article pages could not be retrieved; any usable feed excerpts are labelled.")
    if not any(s["region"] == "EU" and s["status"] == "ok" for s in report["sources"]):
        report["warnings"].append("No configured EU-focused source could be checked successfully.")
    return expanded, report
