# Conservative relevance and English output

Implemented directly in the repository on 01-10-2026. Scheduled sending remains
disabled; no live model request, email delivery, monitoring change or GitHub
configuration change was made as part of this update.

## Candidate relevance

`briefing/relevance.py` replaces the broad keyword counter. A candidate must
contain a specific material-development signal in its title or bounded source
text. Examples include a platform/app launch, corporate acquisition or closure,
funding, creator compensation/terms, monetisation, paid downloads/ownership,
distribution/licensing partnerships, publishing tools, reading technology,
accessibility/localisation and expansion into markets.

The rules recognise English, French and Spanish terminology from the configured
feeds. Accent normalisation is used only for relevance matching. Stored titles,
excerpts, fingerprints and evidence are never translated or normalised by this
filter. Signals are matched within individual titles/sentences, generally with
bounded proximity, rather than combining unrelated words from an entire page.
Scoring considers up to the first 3,600 source-text characters, matching the
default model excerpt window.

Scoring gives a material development a base of 8 points, then up to 6 for distinct
signal categories and up to 4 for title signals. Watchlist matches add 2 and
official sources add 1. Region bonuses are US 4, UK 3, Canada 2 and EU 1. Routine
format categories subtract 2 each, capped at 6. Without materiality, the score is
capped at zero; the existing minimum score is 4. Repeated occurrences do not add
points. The existing preference for up to four eligible EU candidates is retained.

Reviews/recaps, bestseller lists, interviews/profiles, crowdfunding spotlights,
title/issue promotions, previews, adaptations and convention/promotional
roundups cannot qualify solely through company names or broad words such as
“launch”, “digital”, “publisher” or “licensing”. An interview reporting an
acquisition, or a review revealing changed creator terms, can still qualify.
Ordinary title crowdfunding, download availability and adaptation licensing
are distinguished from company financing and platform/economics changes.
Teasers need a substantive material detail beyond their title.

`sources.collect()` scores feeds before article fetching, then scores again
after public-text/preview extraction. A relevance rejection after fetching is
backfilled from the remaining ranked queue. The 20-candidate model limit,
60-article fetch limit, 240-second between-batch budget and all date/seen checks
are retained. A failed fetch can still use a labelled eligible feed excerpt.

This is a conservative heuristic shortlist, not a semantic judgement or a claim
that the reported event is verified. The editor makes the final selection and
can select zero stories. A real development hidden behind a generic interview
title and an uninformative feed excerpt can be missed because its page never
enters the fetch queue. Terminology not covered by the rules can also be missed;
additional languages need rule coverage if added to the source registry. Review
the next source-check report and early editions before tuning thresholds.

## Relevance diagnostics

`selection_version: 2` continues to describe the existing backfill algorithm.
New `relevance_version: 1` identifies the scoring rules separately.

Fetched `candidate_diagnostics` now also contain:

- `feed_score`, plus `score` / `relevance_score` after extraction;
- `positive_signals` and `negative_signals`, as fixed English labels;
- `business_materiality` and `watchlist_match` booleans;
- `exclusion_reason` (empty for a qualifying relevance assessment);
- `outcome: irrelevant_after_fetch` for a relevance rejection after date/seen checks.

Top-level fields include `relevance_after_fetch_omitted`, complete
`relevance_exclusion_counts`, and `relevance_exclusions`: a sample of at most
25 relevance rejections with stage `feed` or `article`. `score_omitted` retains
its existing meaning of feed-stage threshold exclusions. Typical reasons are
`routine_without_material_development`, `no_material_development`,
`teaser_without_substantive_detail`, and `below_minimum_score`.

The report does not export source excerpts or evidence quotes. Original source
titles remain original-language diagnostic metadata; all generated newsletter
copy, analysis messages, notes and signal labels are English.

## English copy, original-language evidence

The system editorial contract and structured-output schema explicitly require
English `headline`, `summary`, `implication`, optional `action`, and optional
`new_development`. Company/product proper names are preserved. Source titles,
language metadata and source excerpts passed to the model remain unchanged.

Evidence quotes must still be exact original-language source substrings, with
the existing word limits and source-ID checks. Translating a quote causes
`quote_not_found`; accents, case and punctuation are not “repaired”. Numeric
checks remain unchanged. Evidence is removed before publication.

`briefing/language.py` uses pinned `langdetect==1.0.9`, locally, with a seeded
detector for reproducible results. Each generated field with at least four
linguistic words is checked; a non-English detection with probability at least
0.90 rejects that proposal with `non_english_output`, naming the field and
language in the existing validation diagnostics. The check ignores markup tag
names without changing the text passed to the HTML-escaping renderer.

As described in the [language detector documentation](https://github.com/Mimino666/langdetect#basic-usage),
short or ambiguous text is less reliable. Very short names/phrases rely on the
English prompt contract, and mixed-language text or detection errors remain
possible. This guard is not proof of translation accuracy or a guarantee for
every phrase. There is no extra translation API or paid repair request.

Rejected proposals follow the existing diagnosed fallback path and are not
marked as successfully assessed. If every proposal fails, the edition is
`links_only`, never a quiet-day claim. Fallback links use “Read source article”
in English instead of untranslated source headlines. This loses headline detail
on failed runs, but retains source names, dates, access labels and direct URLs
without inventing a translation. Quiet-day, partial-coverage and failure copy
remain English.

## Verification and next steps

The full offline suite passes: **177 tests**, including the existing 116 tests
and 61 new tests for relevance, post-fetch replacement, report bounds, French/
Spanish sources with English copy, exact original-language evidence, translated
quote rejection, non-English output rejection, and fallback/quiet/failure copy.
Tests use simulated model responses, not live translation. Local runtime:
Python 3.12.13; the GitHub workflow continues to use Python 3.13.

The model, monthly USD 1.50 guard, state/history, schedule, Resend, Healthchecks,
source configuration and original evidence/number/duplicate checks are retained.
No new recurring service cost is introduced.

Next: run `check-sources`, then `preview`, inspect the relevance diagnostics and
newsletter, run `send-test` and verify the inbox. Enable production only after
those checks. Publishers Weekly's existing access limitation remains unresolved.
