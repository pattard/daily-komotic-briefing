# Operations

## State and spending

`briefing-state/state.json` is the durable ledger. The application creates the branch using the job's `GITHUB_TOKEN`; no personal access token or external database is needed. Optimistic SHA checks on writes and a single shared workflow concurrency group protect normal concurrent operation. Do not run a second instance with an independent ledger.

The ledger contains edition payloads/status, Resend IDs, assessed-article fingerprints, a short event history and model-cost reservations. It does not contain API keys, the monitoring URL or full source articles. Private repository members who can read that branch can see recipient/sender addresses and newsletter contents.

The earlier standalone `setup-check.yml`, if retained, does not use this application ledger. Its tiny setup requests and any other applications are outside this guard.

Every model request is reserved in durable state before it is made. A normal successful response replaces the conservative reservation with usage-based estimated cost at configured prices; cached input is conservatively priced as uncached. An ambiguous failed request keeps its reservation. The same edition does not automatically make a second model request. New manual preview/test runs are separate editions and count towards the same monthly limit.

Current configured prices: GPT-4.1 mini, USD 0.40/million input tokens and USD 1.60/million output tokens, checked 30-09-2026. Reservation uses UTF-8 request bytes plus framing allowance, output cap and 15% margin rather than claiming exact advance token accounting. Review prices before changing the model. There is no SDK retry loop that can silently multiply paid requests.

**Do not delete the state branch or reset the budget to resolve a delivery error.** That can remove duplicate-send and spending protections. If a state branch exists but its file is missing, the application stops rather than assuming a clean install. A crash during first-time branch creation can require manual restoration/initialisation before the first preview; verify there is no prior ledger before doing that.

Recent edition payloads are pruned after four days once queued/previewed; their delivery markers remain for 45 days. The current state limits seen-item fingerprints to 1,200 records and event history to 60 entries. Git commit history still retains older versions unless separately rewritten. Repository history is not a privacy-erasing retention mechanism.

## Delivery state machine

1. Collect evidence and create the edition.
2. Save the complete, immutable outgoing payload and idempotency key.
3. Save a send-attempt marker before calling Resend.
4. Submit that exact payload.
5. Save the returned email ID and queued status, then advance production coverage.
6. Signal Healthchecks only for production or explicit monitor arming.

The 07:43 recovery run sees the same dated edition. If already queued it does not call the model or email API again. If a send result is ambiguous, it reuses the identical saved payload/key; it does not regenerate the newsletter under the same key.

Resend retains idempotency keys for 24 hours. This application stops ambiguous retries after 23 hours and after three send attempts. It also refuses to replay a saved `scheduled_at` timestamp that is already in the past. These restrictions prefer an explicit operational exception over a duplicate or silently changed message.

This is **not an exactly-once guarantee** across every possible provider/state/network failure. A provider may accept an email before a durable local success record is confirmed. The saved key/payload and dashboard reconciliation are the recovery mechanism.

## Reconcile an ambiguous send

1. Set `NEWSLETTER_ENABLED=false` temporarily if further runs would confuse the investigation. Pausing the Healthchecks check can avoid duplicate alerts while the known incident is handled.
2. Inspect the dated entry in `briefing-state/state.json` and the Resend dashboard. Match date, recipient, subject and the saved email ID if available.
3. If Resend accepted/scheduled the email, do not send another. Restore the correct queued record and coverage state from a known-good ledger or have a developer perform a targeted reconciliation. Do not change only the idempotency key to force a second send.
4. If Resend definitely never accepted it, a developer can reconcile that single pending entry. Do not clear the whole ledger. Resume with the scheduled workflow or the guarded `send-edition` mode.
5. Re-enable the toggle and monitoring once the incident is understood. A new successful production heartbeat restores Healthchecks status.

For a **test** failure after changing sender settings, start a **new manual `send-test` run**. Do not rerun an old frozen payload with new expected contents. Credential-only corrections can reuse the old run because credentials are not part of its saved email payload.

## Troubleshooting

| Symptom | Interpretation and check |
|---|---|
| Workflow not listed | Confirm `.github/workflows/briefing.yml` exists on the default branch, not in a nested folder. |
| Scheduled job skipped | Confirm `NEWSLETTER_ENABLED` is exactly `true`; check the default-branch restriction and Actions policy. |
| GitHub 403 | The job cannot write contents/create the state branch, or repository/organisation policy blocks it. Scope fixes to `briefing-state`. |
| GitHub 409 | State write conflict. Do not force-reset; investigate another instance, manual edit or blocked ref. |
| OpenAI 401/403 | Check project key, model access and Responses API permissions. Never paste credentials into issue comments. |
| OpenAI 429 | Check project credit, spend limit and rate limits. The edition falls back to links rather than repeatedly charging retries. |
| Resend 403 | Check that the key can send from the verified `briefings.wearegoat.com` domain. |
| Resend 409 | A frozen idempotency key was used with different contents or an identical request is still in progress. Investigate; do not invent a fresh key blindly. |
| Green workflow but no newsletter | Inspect the mode and `report.json`. Preview does not send. A queued email may be scheduled for later or fail during provider delivery. |
| Green workflow plus collection-failure notice | API delivery worked but research did not. Inspect per-source statuses; Healthchecks is signalled as failed for this case. |
| Many `robots_disallowed_or_unavailable` statuses | The site's automation policy cannot be safely read or denies the collector. Disable/replace the source; do not bypass it. |
| `parse_failure` or `empty_or_unrecognised_source` | Feed URL/site markup may have changed or returned a challenge page. Verify with `check-sources`. |
| Repeated quiet days | Inspect coverage, candidate counts and cutoff dates before assuming no industry news. Tune filters and source selection. |
| Healthchecks remains New/Paused | Configure cron, allow/resume monitoring, then run `arm-monitor` after a successful full send-test and enabling the schedule. |
| Email arrives late | GitHub may have delayed/dropped preparation; Resend or the receiving server may also be delayed. Inspect both service logs. |

## Monitoring semantics

Use one check: cron `13 7 * * 1-5`, timezone `Europe/Madrid`, grace 42 minutes. This aligns the monitor with the **start of the preparation window** and allows the recovery run before a 07:55 missing-heartbeat alert.

A quiet-day email with successful collection counts as healthy. An explicitly labelled links-only email also counts as a completed delivery, while its editorial degradation remains visible. A major collection failure, state/API error or explicit production workflow failure produces a failure signal. Some primary failures may alert before recovery; a successful recovery restores status.

`arm-monitor` is an explicit setup heartbeat after a recent successful full test. It primes the first expected check even if the first scheduled GitHub job never starts. It does not test future scheduler reliability, does not send another email, and does not claim an automatic run has already occurred.

The monitor confirms preparation and email API acceptance. It does not confirm delivery to the mailbox, future delivery of a scheduled Resend message, or the truth of every generated implication. End-to-end delivery monitoring would require Resend event webhooks or additional read permissions and implementation.

## Pausing or changing the schedule

Set `NEWSLETTER_ENABLED=false` to stop new automatic editions. Pause Healthchecks while intentionally inactive. **Cancel already-queued scheduled emails in Resend separately**; changing a GitHub variable does not cancel an external queued message.

Changing time or timezone requires coordinated edits to:

- Repository variables/default settings used by the application.
- `.github/workflows/briefing.yml` cron/timezone.
- The Healthchecks cron/timezone/grace configuration.

## Source and editorial maintenance

Review the first five delivered editions for quality, not only successful execution. Check whether implications are useful, routine launches are excluded, important EU stories surface, and the same event is being repeated under different headlines.

Source discovery happens through broad trade feeds as well as watchlist-name matching. It is not a web-wide discovery engine. A watchlist entity has no dedicated monitoring coverage unless a source reports it or an official endpoint has been configured. Add validated sources as gaps become apparent rather than assuming 54 names equals 54 independently monitored sites.

The heuristic shortlist, excerpt truncation and 20-candidate cap can miss stories. Rejected date/seen candidates are now replaced from the queue, up to 60 article-page attempts and a 240-second between-batch expansion budget. The report exposes the stop reason, genuinely unattempted overflow and failed retrieval. These bounds are still selective, not exhaustive; see SOURCE_SELECTION_FIX.md. Semantic event grouping and significance judgments remain model-dependent. Do not interpret citation/quote validation as proof of every inference.

Dependabot is configured monthly for direct Python dependencies and GitHub actions. Review updates and keep CI passing. Official actions currently use their documented major tags; projects requiring immutable supply-chain pinning should review and replace those tags with verified commit SHAs, retaining update automation.
