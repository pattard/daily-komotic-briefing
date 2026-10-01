"""Verbatim evidence options and non-publishing quote-mismatch diagnostics."""
from __future__ import annotations

import re
import unicodedata

from .common import clean
from .sources import Article

MAX_OPTIONS = 12
MAX_QUOTE_CHARS = 220


def quote_options(article: Article, excerpt_chars: int) -> list[str]:
    """Select bounded, unmodified source spans across the submitted body text.

    Sentence-sized spans are preferred; long sentences are split at word
    boundaries. Sampling limits schema size without changing the model excerpt.
    Headlines alone are never evidence options.
    """
    excerpt = article.excerpt[:excerpt_chars]
    options: list[str] = []
    for sentence in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|\n|$)", excerpt, re.S):
        text = sentence.group().strip()
        words = list(re.finditer(r"\S+", text))
        start = 0
        while start < len(words):
            end = min(start + 25, len(words))
            if end - start < 4:
                start = max(0, end - 4)
            if end - start < 4:
                break
            # Keep long-word sentences useful by choosing a shorter verbatim
            # span, rather than dropping a whole 25-word chunk for size alone.
            while end - start > 4 and words[end - 1].end() - words[start].start() > MAX_QUOTE_CHARS:
                end -= 1
            quote = text[words[start].start():words[end - 1].end()]
            if len(quote) <= MAX_QUOTE_CHARS and quote not in options:
                options.append(quote)
            start = end
    if len(options) > MAX_OPTIONS:
        # Include the beginning and end, with deterministic evenly spaced spans.
        options = [options[i * (len(options) - 1) // (MAX_OPTIONS - 1)] for i in range(MAX_OPTIONS)]
    return options


def submitted_context(article: Article, excerpt_chars: int) -> str:
    return clean(article.title + " " + article.excerpt[:excerpt_chars])


def typography(text: str) -> str:
    """For diagnostic comparison only. Never used to accept or repair quotes."""
    table = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"',
                          '–': '-', '—': '-', '…': '...'})
    return clean(unicodedata.normalize('NFC', text).translate(table))


def without_punctuation(text: str) -> str:
    return clean(''.join(' ' if unicodedata.category(c).startswith('P') else c for c in text))


def quote_mismatch(quote: str, article: Article, articles: list[Article], excerpt_chars: int) -> dict:
    """Describe possible mismatch mechanisms without exporting either text."""
    context = submitted_context(article, excerpt_chars)
    reason = "no_exact_source_span"
    if quote in clean(article.title + " " + article.excerpt):
        reason = "outside_submitted_excerpt"
    elif any(a.id != article.id and quote in submitted_context(a, excerpt_chars) for a in articles):
        reason = "matches_another_submitted_source"
    elif quote.casefold() in context.casefold():
        reason = "case_mismatch"
    elif typography(quote) in typography(context):
        reason = "typography_mismatch"
    elif len(quote) > 2 and (quote[0], quote[-1]) in {('"', '"'), ("'", "'"), ('“', '”'), ('«', '»')} and clean(quote[1:-1]) in context:
        reason = "added_quotation_marks"
    elif without_punctuation(quote) in without_punctuation(context):
        reason = "punctuation_mismatch"
    language = article.language.lower()
    return {"reason": reason, "quote_words": len(quote.split()), "quote_chars": len(quote),
            "source_language": language if re.fullmatch(r"[a-z]{2,3}(?:[-_][a-z0-9]{2,8})?", language) else "unknown",
            "submitted_excerpt_chars": len(article.excerpt[:excerpt_chars]),
            "excerpt_truncated": len(article.excerpt) > excerpt_chars}
