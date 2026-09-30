# Validation record

Build date: 30-09-2026.

## Locally executed

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

## Not executed here

- Live source collection from GitHub-hosted runners.
- Live OpenAI, Resend, Healthchecks or authenticated GitHub state API requests.
- A real end-to-end email delivery.
- A production schedule, GitHub repository push or change to the user's repository settings.
- Real-feed editorial acceptance testing across several consecutive days.

The build environment could not resolve external hostnames. That limitation was reported rather than replaced with fabricated live results. The packaged GitHub workflows are the next validation environment.

## Before enabling

Run `check-sources` as necessary, then `preview`, inspect `report.json`, run `send-test` and inspect the actual inbox email. Only after an acceptable result should we enable `NEWSLETTER_ENABLED` and run `arm-monitor`. Review at least the first five production editions for source balance and usefulness.

The example under `examples/` is explicitly fictional and demonstrates layout only. It is not a current-news sample.
