# Diagnostics fix: source checks versus newsletter generation

Date: 30-09-2026

**Follow-up update:** the complete package also includes the bounded collector
replacement fix described in `SOURCE_SELECTION_FIX.md`. The original diagnostics
changes and their historical validation record are documented below.

## What this update fixes

The original fallback discarded per-item rejection warnings and set the displayed
assessment count to zero. That made a completed model request with rejected
proposals look like a run that had not attempted analysis. The original source-only
command also did not record its mode explicitly.

This update preserves the evidence and format checks. It does not force an edition
to pass, increase API spending, add retries, change recipients or change the schedule.

### Scope

- Record `run_mode`, `collection_status` and `diagnostics_version` in new reports.
- Give `check-sources` the explicit status `edition_status: not_generated` and
  `analysis.status: not_requested`. This mode does not call OpenAI, send email,
  update coverage/budget state or ping Healthchecks.
- Remove stale `newsletter.html` and `newsletter.txt` when a local output directory
  is reused for a source-only check.
- Preserve individual rejection codes, proposal counts, submitted-candidate counts
  and fallback reasons in newsletter reports.
- Show generation status in the GitHub run summary, not just execution success.
- Explain that internal evidence quotations must remain in the original source
  language. Only reader-facing text is translated into English.
- Record candidate filtering outcomes, including old dates discovered after
  fetching a page. No article excerpts are added to the report.
- Do not mark failed proposals or fallback links as successfully assessed in
  production history. They remain eligible for a later run.
- Require a non-fallback test newsletter before arming monitoring.

There are no source-registry, ranking-rule, model, pricing, credential, dependency,
workflow-schedule or state-schema changes. The existing $1.50 application budget
and single-attempt model-call behaviour are unchanged. Source and evidence material
remains untrusted data, not executable instructions.

## Installation

**Already applied in the complete recovery archive.** When restoring from `daily-komotic-briefing-complete.zip`, follow [RECOVERY.md](RECOVERY.md) instead. The instructions below describe the earlier changed-files patch only; do not apply it again.

1. Keep `NEWSLETTER_ENABLED=false` while validating the update.
2. Work on the repository's default branch with local changes reviewed or committed.
3. Extract the patch ZIP. Merge the contents of its `daily-komotic-briefing` folder
   into the existing repository root, replacing only matching files. This is a
   changed-files package, not a complete repository. Keep all other files.
4. Review the diff, commit and push. Do not delete or reset the `briefing-state`
   branch, `state.json`, existing budget history or existing repository secrets.
5. Start a NEW `check-sources` workflow from the updated default branch.
6. Start a NEW `preview` workflow from the updated default branch.

The alternative `.patch` file can be applied from the repository root with:

```bash
git apply --check /path/to/daily-komotic-briefing-diagnostics-fix.patch
git apply /path/to/daily-komotic-briefing-diagnostics-fix.patch
python -m unittest discover -s tests -v
```

Use either the ZIP or the Git patch, not both. The `--check` step catches conflicts
with local modifications before applying the Git patch. The Python test command
requires the repository's existing dependencies to be installed.

Changed or added paths:

```text
briefing/app.py
briefing/editor.py
briefing/render.py
briefing/sources.py
config/editorial.md
docs/DIAGNOSTICS_FIX.md
tests/test_diagnostics.py
```

Stage only these paths, review the staged diff, then commit and push:

```bash
git add briefing/app.py briefing/editor.py briefing/render.py briefing/sources.py
git add config/editorial.md docs/DIAGNOSTICS_FIX.md tests/test_diagnostics.py
git diff --cached --stat
git commit -m "Preserve briefing validation diagnostics and distinguish source checks"
git push
```

Do not reuse a previously prepared edition to validate new code. A new manual
workflow run creates a fresh preview while preserving the historical spending ledger.
Preview requests remain subject to the same spending guard as other model requests.

## Reading a source-only report

Expected distinguishing fields:

```json
{
  "run_mode": "check-sources",
  "diagnostics_version": 2,
  "edition_status": "not_generated",
  "analysis": {
    "status": "not_requested",
    "model_requested": false,
    "candidates_submitted": 0
  }
}
```

`collection_status` is `ok`, `partial` or `failed`. A result of 9/10 successful
sources would be `partial`, not an analysis failure. A source-only artifact contains
`report.json`, not a newsletter. No model-spending estimate is added because this
mode does not open the spending ledger.

An inaccessible/robots-restricted source remains a coverage warning. Do not bypass
access restrictions or change keys merely to make every source appear green.

## Reading a preview report

A generated preview records `run_mode: preview`. A valid edition can be `briefing`
or `quiet`; there is no minimum number of stories to force through.

| Field | Meaning |
| --- | --- |
| `edition_status` | `briefing`, `quiet`, `links_only`, or `collection_failure` |
| `fallback_reason` | Explanation for a fallback; empty for a normal briefing/quiet edition |
| `analysis.status` | Generation stage/outcome, independent of collection health |
| `analysis.model_requested` | Whether the application attempted its model API call |
| `analysis.candidates_submitted` | Candidate records included in that request, not a claim that all were successfully evaluated |
| `analysis.proposed_items` | Items in the structurally valid returned proposal |
| `analysis.accepted_items` | Proposed items accepted for publication |
| `analysis.rejected_items` | Proposed items rejected by evidence/format checks |
| `analysis.skipped_items` | Duplicates or previously reported events skipped separately from failures |
| `analysis.validation_errors` | Item numbers, trusted source IDs, check codes and safe numeric details |
| `editorial_warnings` | Human-readable rejection notices, retained on fallback |

### Analysis statuses

`completed` and `completed_with_rejections` mean the response reached the item
selection stage. A response selecting no stories can legitimately produce `quiet`.
`validation_failed` means all publishable proposals were rejected; it is not a
quiet-day result. Other explicit statuses include `schema_invalid`,
`response_not_json`, `response_incomplete`, `api_error`, `missing_api_key`,
`insufficient_text`, `request_size_guard`, `budget_or_repeat_guard`, `no_candidates`
and `collection_failed`.

### Validation codes

| Code | Meaning |
| --- | --- |
| `quote_not_found` | The supporting quote was not found verbatim in the supplied title/excerpt after whitespace normalisation. Translation, paraphrasing and punctuation differences can cause this; the code alone does not distinguish them. |
| `unsupported_number` | A numeric token in the summary was not found by the existing numeric guard in the cited material. This is a conservative format check, not a complete semantic fact-check. |
| `word_limit_exceeded` | A named field exceeded its word allowance; actual and allowed counts are included. |
| `quote_word_limit_exceeded` | The per-source quotation allowance was exceeded. |
| `quote_too_short` | The quote contained fewer than four words. |
| `invalid_source_ids` | At least one source ID was unknown, duplicated or missing. |
| `invalid_evidence_source` | Evidence pointed to an unknown or uncited source. |
| `evidence_source_mismatch` | The cited-source set and supporting-evidence set differed. |
| `generated_url` | A generated text field contained a URL. Links must come from collected source records. |
| `missing_update_detail` | An item claimed to be an update without describing the new development. |
| `schema_invalid` | The model response did not meet the required JSON structure. Raw validator messages are not exported. |

The diagnostic report intentionally does not contain raw model responses, rejected
quotations, full article excerpts, credentials or the monitoring URL. Unsupported
numeric tokens, counts and trusted source identifiers are sufficient for identifying
which programmed checks fired without publishing the rejected material.

## Candidate diagnostics and editorial quality

The existing preselection and fetch limits remain unchanged. New fields distinguish
raw entries from unique URLs and show why fetched candidates were excluded:

- `unique_entries`, `score_omitted`, `old_omitted`, `old_after_fetch`,
  `already_seen_omitted`, `article_fetch_attempts`, and `eligible_candidates`.
- `candidate_diagnostics`: selected candidate metadata and an outcome of `eligible`,
  `old_after_fetch`, `future_after_fetch`, `undated`, or `already_seen`.

`candidate_overflow` is the existing shortlist-cap warning, not an API error. An
`eligible` candidate passed collection filters; it has NOT necessarily passed the
editorial relevance or evidence checks.

A links-only fallback is an unassessed source list, not an approved industry
briefing. Book-review-looking headlines in that list do not establish that the
model selected them for the finished newsletter. Candidate selection still needs
review using the next live report; this patch does not claim to fix ranking.

## Verification and limits

The original 70 automated tests pass with this update. There are 26 additional
regression tests, for a total of 96 passing tests on 30-09-2026. Inputs and API
responses were simulated; no live model requests, email deliveries or source fetches
were performed during this fix.

A mocked invalid quotation reproduces the original reporting failure: the original
code exports empty editorial warnings and a zero-assessed footer. The patched code
still correctly refuses that quotation, but now records `quote_not_found`, the
submission/proposal/rejection counts and the `preview` mode.

The original uploaded artifacts did not retain the rejected output or individual
check reasons. They therefore cannot establish which exact check rejected the
original proposals. The prompt clarification may help with multilingual evidence,
but that is not a confirmed diagnosis of the original run. One new live preview
is required; inspect its diagnostics before changing validation rules or enabling
production delivery.
