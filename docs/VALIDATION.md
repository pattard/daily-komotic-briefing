# Validation record

Build date: 30-09-2026.

## Preview evidence-selection correction (01-10-2026)

- The supplied preview reported `quote_not_found`, with one proposal rejected
  and an honest English links-only fallback. It did not retain the failed quote,
  so its precise mismatch mechanism cannot be reconstructed from the artifacts.
- Response-schema evidence choices now bind exact original-language body-text
  spans to each source ID. The existing independent validator remains strict;
  no approximate matching, quote repair or paid retry was introduced.
- Safe diagnostics add evidence-option counts and fixed mismatch reasons without
  exporting model quotes or source bodies. Reports use `evidence_version: 1`.
- Full offline suite: **206 tests passed** under Python 3.12.13, including all
  previous 185 tests and 21 new evidence-selection regression tests. French and
  Spanish evidence is unchanged; reader-facing English checks still pass.
- Request-size and enum bounds were checked with a 20-source fixture. The
  spending guard still accounts for the complete request, including its schema.
- No live model request, email, monitoring, schedule or GitHub settings change
  was made. A new live preview workflow is required before send-test; rerunning
  the old workflow can reuse its saved edition. See
  [EVIDENCE_SELECTION.md](EVIDENCE_SELECTION.md) for trade-offs and acceptance checks.

## Source-report relevance corrections (01-10-2026)

- Reproduced the Comic Social false exclusion and GlobalComix false expansion
  signal with exact report headlines before applying the fix.
- Recognise “launch of” platform/app objects and restrict “global” to the whole
  word or “globally”. No broad relaxation of routine-title filtering.
- Full offline suite: 185 tests passed under Python 3.12.13, including all
  previous 177 tests and eight new report-based regression tests.
- Collector regression confirms the exact Comic Social headline enters the
  fetch queue with no feed excerpt, while insufficient article text still
  prevents a model request and summary.
- Reports now use `relevance_version: 2`; `selection_version: 2` is unchanged.
- No live collection, paid model request, email, monitoring or GitHub settings
  change was made. Rerun `check-sources` before the next live preview.

## Relevance and English-output update (01-10-2026)

- Full offline suite: 177 tests passed under local Python 3.12.13, including all
  116 existing tests and 61 new relevance/language regression tests.
- Tests cover all requested routine exclusions and strategic inclusions,
  post-fetch relevance backfilling and bounded exclusion diagnostics.
- French/Spanish source fixtures retain original-language text/evidence and
  produce English previews from simulated model responses. Translated evidence
  and confidently detected non-English output are rejected without paid retries.
- Existing date, evidence, unsupported-number, duplicate/history, budget,
  scheduling, delivery/idempotency and Healthchecks tests continue to pass.
- No live collector, model, email, monitoring or GitHub requests were made.
  The existing Publishers Weekly access limitation was not changed.
- See [EDITORIAL_FILTERING.md](EDITORIAL_FILTERING.md) for the heuristic and
  language-detector limitations. Live preview and send-test validation is still
  required before enabling scheduled delivery.

## Bounded source-selection update verification

- Python 3.13.5: all 116 offline tests passed, including 20 new collector tests.
- The same controlled queue fixture produced 4 eligible candidates from 20
  attempts with the original collector, and 20 from 36 attempts after the fix.
  Both rejected the same 16 old pages. This was synthetic, not a replay of live news.
- The fictional demo completed. Newsletter templates and rendering code were unchanged.
- The complete archive was checked to retain every path from the previous full package.
- No live news, model, email, monitoring or authenticated GitHub requests were made.
- No source, secret, state-schema, email-address, schedule, model, evidence-validation
  or scoring-rule changes. Only collection limits/progression and documentation changed.
- See SOURCE_SELECTION_FIX.md for the distinction between collection eligibility
  and genuine editorial relevance.

## Complete-repository recovery verification (previous package)

- Restored every path from the original archive and overlaid the diagnostics-fix archive.
- No application, configuration or workflow changes beyond that existing fix.
- Re-ran all 96 automated tests under Python 3.13.5: passed.
- Re-ran the fictional, offline newsletter demo successfully.
- Included hidden workflow and configuration files; excluded caches, credentials, Git metadata and runtime state.
- This restoration did not contact live news, model, email or monitoring services.

## Initial package validation record

- Python 3.13.5.
- 70 automated unittest cases passed at the initial validation pass.
- Synthetic RSS/Atom parsing, HTML listing parsing and article extraction.
- Rejection of unsafe URLs and XML entity expansion; robots checks before redirected article fetches.
- Paywall-preview handling, missing publication dates, future dates and old items.
- Friday/weekend inclusion in Monday's rolling publication window.
- Model-response schema, source-ID, exact-quote, number and size checks.
- Quiet-day, missing-key, API-failure, inadequate-source and spending-cap paths.
- Durable budget reservation before a potentially billable request.
- Suppression of repeated paid calls after an ambiguous failure.
- Preview/test separation from production history and monitoring.
- Correct Europe/Madrid summer and winter 08:00 target conversion.
- Repeated-run suppression, immutable resend payload/key reuse, bounded retry and stale-schedule guards.
- Explicit monitoring arming after an adequate recent full test.
- HTML escaping and absence of secrets from output artifacts.
- Fictional newsletter rendered in Chromium at desktop and 390 px mobile widths; no horizontal overflow.

Tests use controlled synthetic inputs and simulated API responses. They do not demonstrate semantic editorial accuracy on live news or prove provider delivery behaviour. Current test output, rather than this historical count, is authoritative after changes.

## Live validation still required

- A new source-check run of this collector update from GitHub-hosted runners.
  The user supplied a prior report showing 9/10 endpoints successful; the updated
  collector has not been run there by this build process.
- Live OpenAI, Resend, Healthchecks or authenticated GitHub state API requests.
- A real end-to-end email delivery.
- A production schedule, GitHub repository push or change to the user's repository settings.
- Real-feed editorial acceptance testing across several consecutive days.

The initial build reported a DNS-resolution limitation. This update deliberately uses offline fixtures only and makes no new claim about network availability. The packaged GitHub workflows are the next live validation environment.

## Before enabling

Run `check-sources` as necessary, then `preview`, inspect `report.json`, run `send-test` and inspect the actual inbox email. Only after an acceptable result should we enable `NEWSLETTER_ENABLED` and run `arm-monitor`. Review at least the first five production editions for source balance and usefulness.

The example under `examples/` is explicitly fictional and demonstrates layout only. It is not a current-news sample.
