# Bounded replacement of rejected collection candidates

Date: 30-09-2026

## What the supplied report establishes

The user's `check-sources` report records `edition_status: not_generated` and
`analysis.status: not_requested`. This is the intended source-only behaviour,
not a model-validation failure. Nine of ten configured endpoints succeeded;
Publishers Weekly returned `robots_disallowed_or_unavailable`.

Of 42 preselected entries, the collector attempted 20 article pages. Sixteen
were rejected as `old_after_fetch`, leaving four eligible candidates and 22
unattempted entries. All four eligible entries came from EU sources. These facts
do not establish that there was no relevant English-market news, nor that the
remaining entries would have qualified. The report does not include the contents
or identities of all unattempted entries.

Source: user-supplied `report.json`, source-check window ending
30-09-2026 at 10:16:57 UTC. This update does not reproduce source article bodies.

## Confirmed code defect

Inspection of the supplied complete repository showed that `collect()` first
cut its ranked queue to `max_candidates` (20), fetched only that slice, and then
rejected stale, undated, future or already-seen items. It never replaced those
rejections from the remaining queue. Publication-date checks were protecting the
newsletter from old stories, but the position of the cap unnecessarily prevented
other candidates from being checked.

## Changes in this package

The collector retains the full preselected queue and checks small batches until:

- 20 collection-eligible candidates have been found;
- the ranked queue is exhausted;
- 60 article-page attempts have been made; or
- the article-expansion time budget is exhausted.

The time budget is 240 seconds and is checked between batches. It does not cancel
in-flight requests; those retain the existing HTTP timeouts, redirect limits and
per-host pacing. This is not a guarantee that all network activity ends at exactly
240 seconds. Initial feed/listing retrieval is outside that expansion budget.

Rejected items do not fill the model shortlist. The existing ranking formula,
score threshold and preference for up to four qualifying EU entries are retained.
There is no new rule that turns routine reviews into industry news or forces a
geographical mix of published newsletter items. Editorial selection still has to
be evaluated in a preview.

The existing maximum of one paid model call per preparation, 20 candidate records,
request-size guard and USD 1.50 monthly application spending guard remain in place.
A fuller shortlist can use more input tokens than a four-candidate shortlist; this
change does not mean identical cost for every edition. Source-only checking still
makes no model request and sends no email or monitoring signal.

No changes were made to sources, source URL patterns, publication-date extraction,
robots handling, paywall handling, model, editorial/evidence validation, email
settings, schedule, credentials or persistent-state schema.

## New collection diagnostics

The existing `diagnostics_version` remains 2. The additional `selection_version`
field is 2 in this collector update.

| Field | Meaning |
|---|---|
| `selection_version` | Identifies the replacement-aware collector, currently 2 |
| `candidate_limit` | Maximum collection-eligible candidates passed on, currently 20 |
| `article_fetch_limit` | Maximum article-page attempts, currently 60 |
| `article_fetch_time_budget_seconds` | Between-batch expansion budget, currently 240 |
| `article_fetch_elapsed_seconds` | Observed expansion duration |
| `article_fetch_attempts` | All attempted article-page expansions, including rejected items |
| `backfill_fetches` | Attempts beyond the original first `min(preselected, candidate_limit)` positions |
| `candidate_overflow` | Preselected entries that were never attempted, not entries already rejected |
| `selection_stop_reason` | Why the collector stopped checking the queue |

Stop reasons are `queue_exhausted`, `candidate_limit`, `article_fetch_limit` and
`article_fetch_time_limit`. If every preselected item was attempted, the reason
is `queue_exhausted`, even when the eligible count also happens to equal the cap.

Each attempted item retains its individual entry in `candidate_diagnostics`.
An `eligible` outcome means collection filters passed, not that the story has
passed editorial or evidence validation.

## Validation performed

All 116 offline automated tests passed: the prior 96 tests plus 20 new collection
regression tests. The fictional demo also completed. Tests cover replacements
for old, missing-date, future and already-seen pages; count/time limits; shortlist
bounds; retained EU preference and feed fingerprints; failure labels; configuration
validation; and absence of source article text from reports.

A separate synthetic fixture reproduced the uploaded report's queue shape, but
not its article contents. It gave the 22 unattempted positions recent, valid
pages so that queue progress could be tested deterministically:

| Result | Original collector | Updated collector |
|---|---:|---:|
| Preselected entries | 42 | 42 |
| Article-page attempts | 20 | 36 |
| Old items rejected after fetching | 16 | 16 |
| Collection-eligible candidates | 4 | 20 |
| Unattempted entries | 22 | 6 |

This verifies replacement behaviour, not that the real next run will find 20
relevant stories. No live news, OpenAI, Resend, Healthchecks or authenticated
GitHub calls were made to validate this update. The model-validation failure
from the earlier preview remains a separate issue to check with a fresh preview.

## Installation and next run

This is a complete application package, including the previous diagnostics fix.
It is not a changed-files-only patch. See `RECOVERY.md` for safe merge commands.

Keep `NEWSLETTER_ENABLED=false`. Back up the existing checkout, then merge the
contents of this archive's `daily-komotic-briefing` folder into the existing
repository without deleting unrelated files. Preserve `.git`, local credentials,
GitHub secrets/variables and the remote `briefing-state` branch.

After review, commit and push through the normal default-branch process. Start a
new `check-sources` workflow run. Confirm `selection_version: 2` and inspect the
stop reason and candidate outcomes. Do not expect fixed live-source counts.

Then start a new `preview` run. It may produce `briefing`, `quiet` or a clearly
labelled fallback. If `links_only` remains, inspect `analysis.validation_errors`,
`analysis.status` and `fallback_reason`. This collection-only fix deliberately
does not weaken validation rules to force a successful-looking result.

Enable scheduled delivery only after an acceptable preview and a successful full
`send-test`, following README.md. No API credential changes are required for this
collection issue.
