# Source-bound evidence selection

## Why this changed

The supplied preview artifacts (`briefing-36838617857-1`) showed one submitted
candidate and one rejected proposal, with `quote_not_found`. The newsletter
correctly fell back to English, unassessed source links. The failed quote and
source body were intentionally absent from exported diagnostics. We cannot
identify its precise mismatch mechanism from those artifacts.

Previously the model composed its own supporting quote. The request now offers
exact original-language source spans instead. This addresses the failure class
without relaxing validation or pretending the failed preview was successful.

## Request and validation

`briefing/evidence.py` extracts four-to-25-word spans from the body text inside
the submitted excerpt window. It preserves spelling, accents, punctuation and
internal whitespace. Headlines alone are not offered. Sentence spans are
preferred; long sentences are split at word boundaries. Each source offers at
most 12 spans, each at most 220 characters. Longer lists are sampled evenly,
including their beginning and end.

`briefing/editor.py` builds source-specific `anyOf` branches in the request
schema. Each branch couples one source ID with an enum of its exact spans.
Source IDs themselves are also restricted to the submitted IDs. The source
excerpt remains available as factual context; the quote catalogue is not
duplicated in the user message. Quote enum strings are explicitly untrusted
source data, never instructions.

Nested `anyOf` and string enums are supported by
[OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
The schema stays within the documented enum limits and the existing application
request-size guard with the tested 20-source fixture.

Independent application validation is retained: source IDs, exact source text,
four-word minimum, aggregate 25-word per-source maximum, unsupported numbers,
English reader-facing fields, duplicates/history and word limits. A fake API or
unexpected response cannot bypass these checks just because the request schema
is constrained. No case-insensitive or punctuation-normalised quote is accepted
or repaired. French and Spanish evidence stays French and Spanish; only
newsletter copy is generated in English. Evidence is removed before publication.

## Diagnostics

Within `analysis`:

- `evidence_version: 1` identifies this request-selection implementation.
- `candidates_with_evidence_options` counts usable-text candidates that also have
  an eligible original-language span; it appears once that step is reached.
- `evidence_options_offered` counts the spans in a requested model schema; it
  stays zero when no request is made.
- `insufficient_evidence` is the failure status when usable text has no eligible
  span. It produces honest links-only copy and makes no model request.

Existing `quote_not_found` errors can also contain a fixed `reason`:

- `outside_submitted_excerpt`
- `matches_another_submitted_source`
- `case_mismatch`
- `typography_mismatch`
- `added_quotation_marks`
- `punctuation_mismatch`
- `no_exact_source_span`

These are diagnostic comparisons only, not acceptance rules or proof of the
model's intent. Unclassified paraphrases and translations use
`no_exact_source_span`, without guessing. Numeric metadata includes quote word/
character counts, excerpt length and truncation, plus a sanitised language code.
Neither rejected quote text nor raw source bodies are exported to reports,
newsletter artifacts or state by this change.

## Trade-offs and verification

The bounded span sample can omit the best supporting passage. The model should
skip a story if no offered span supports its development. Exact evidence still
does not prove every sentence in the summary is semantically supported; early
live editions still need human review. No paid repair pass was added.

The schema adds input tokens. Its bytes are included in the unchanged size and
USD 1.50/month spending guards. There is no new service, model, schedule or
delivery path. Relevance, collection age checks, seen-state, Resend, Healthchecks
and fallback behaviour are preserved.

All **206 offline tests pass**, including 21 new evidence tests. They exercise
exact options and mutations, source binding, original-language preservation,
window and size bounds, diagnostic privacy, insufficient-evidence fallback and
independent quote-budget enforcement. They use simulated API responses, not a
live OpenAI request, and do not establish live editorial accuracy.

After deploying the changes, start a **new** `preview` workflow. Do not simply
rerun the old workflow: saved editions are keyed by run ID and may be reused.
Check `analysis.evidence_version: 1`, inspect the analysis status and newsletter,
and review factual support and English copy. Only after an acceptable preview
should `send-test` be run. Scheduled delivery remains disabled until the user
explicitly enables it after these checks.
