# Daily Komotic Briefing

A private, source-grounded comics-industry newsletter for Komotic. Python application, GitHub Actions scheduler, OpenAI summarisation and Resend delivery. No separate database or paid news-search service.

This repository contains the original application, diagnostics fix, bounded source-selection fix, and conservative relevance/English-output update. Changes are applied directly to the application. See [docs/EDITORIAL_FILTERING.md](docs/EDITORIAL_FILTERING.md) for the current rules, diagnostics and trade-offs; [docs/RECOVERY.md](docs/RECOVERY.md) covers restoration from earlier archives.

**The schedule is disabled until the repository variable `NEWSLETTER_ENABLED` is set to `true`. Installing these files alone does not send a scheduled email.**

## Our configuration

| Setting | Value |
|---|---|
| Recipient | `paul.attard@wearegoat.com` |
| Sender | `Daily Komotic Briefing <komotic@briefings.wearegoat.com>` |
| Intended delivery | Monday-Friday, 08:00, `Europe/Madrid` |
| Evening preparation / recovery | 20:13 and 22:13, Sunday-Thursday, `Europe/Madrid` |
| Overnight recovery | 02:13 and 05:13 on delivery weekdays |
| Morning confirmation / recovery | 07:13 and 07:43 on delivery weekdays |
| Submission deadline / missing-edition audit | 07:55 deadline; 08:13 audit |
| Monthly model-spending guard | USD 1.50, including preview/test runs |
| Newsletter | Up to five substantive items; no padding |
| Markets | US, UK, Canada and EU, initially English-led |

The automated pipeline checks selected feeds and announcement pages, not the entire internet. Links point to the publisher/trade source, not an invented URL or a search-result page. The model receives source excerpts, never API credentials. Its interpretation is separated from reported facts.

Each edition is prepared the previous evening and queued in the existing Resend account for the following weekday at 08:00. Recovery reuses that edition; it does not refresh already-queued news. Developments after the collection cutoff are considered in a later edition. If nothing is queued before 07:55, that day's edition is skipped and monitoring signals failure. No production email is submitted for immediate catch-up delivery. See [docs/SCHEDULING.md](docs/SCHEDULING.md) for the schedule and rollout checks.

## 1. Install into our existing repository

Extract the archive and copy the **contents** of its `daily-komotic-briefing` folder into the root of the existing repository. Include the hidden `.github` directory, `.gitignore` and `.env.example`. Do not create a second nested `daily-komotic-briefing` folder inside the repository.

Keep the existing `.git` directory, local credentials and runtime state. If an earlier `.github/workflows/setup-check.yml` is still present, preserve it too: that optional standalone workflow was not in either saved package and is not required by the included newsletter or Tests workflows. Recover it from existing Git history if needed. Review conflicts with any user-customised files before committing.

Using a local checkout is the most reliable way to include hidden files. After copying:

```bash
git status --short
git diff
# Review what will be committed. Never add real credentials.
git add README.md briefing config docs tests examples requirements.txt .gitignore .env.example .github
git diff --cached --stat
git commit -m "Add source-grounded daily Komotic briefing"
git push
```

Merge to the repository's **default branch** if the change goes through a pull request. Manual and scheduled briefing runs intentionally execute only trusted default-branch code. The Tests workflow runs automatically for relevant changes and uses no service credentials.

## 2. Check variables, secrets and permissions

In **Settings > Secrets and variables > Actions**:

| Repository variable | Value |
|---|---|
| `EMAIL_FROM` | `Daily Komotic Briefing <komotic@briefings.wearegoat.com>` |
| `EMAIL_TO` | `paul.attard@wearegoat.com` |
| `NEWSLETTER_TIMEZONE` | `Europe/Madrid` |
| `NEWSLETTER_SEND_TIME` | `08:00` |
| `NEWSLETTER_ENABLED` | `false` initially |

The first four values also have matching defaults in `config/settings.json`. Existing repository variables take precedence. Do not include quotation marks around a value in GitHub's UI.

Keep the existing repository secrets:

- `OPENAI_API_KEY`
- `RESEND_API_KEY`
- `HEALTHCHECKS_PING_URL`

No personal GitHub access token is required. The workflow uses its automatically supplied `GITHUB_TOKEN`, with `contents: write` **only for the briefing job**, to maintain a `briefing-state` branch. Repository or organisation policies must allow that job to create/update this branch. Do not weaken protection of the default branch; apply any necessary exception only to the dedicated state branch.

Keep Resend's key on Sending access, scoped to `briefings.wearegoat.com`. The application does not require full Resend account access. It does not independently poll delivery events because that would require additional read access or a webhook service.

## 3. Run the preview

Open **Actions > Daily Komotic Briefing > Run workflow**. Select the default branch and mode **`preview`**.

This collects real sources and makes at most one small, billable OpenAI request when sufficient source material and budget are available. It writes usage/state records but **does not send an email, advance production coverage history or ping Healthchecks**.

Download the run's artifact and open:

| File | Purpose |
|---|---|
| `newsletter.html` | Rendered newsletter to inspect in a browser |
| `newsletter.txt` | Plain-text email alternative |
| `report.json` | Source availability, coverage warnings and estimated model spending |

Check relevance, source links, factual summaries, implications and warning messages. With the diagnostics fix, reports explicitly record the run mode and analysis outcome. A `check-sources` run produces only `report.json`, with `edition_status: not_generated` and `analysis.status: not_requested`. It does not generate a newsletter. See [docs/DIAGNOSTICS_FIX.md](docs/DIAGNOSTICS_FIX.md) for validation codes. The collector now replaces date/seen rejections from the remaining queue, subject to a separate cap of 60 article-page attempts and a 240-second between-batch expansion budget. The model shortlist is still capped at 20. See [docs/SOURCE_SELECTION_FIX.md](docs/SOURCE_SELECTION_FIX.md) for collection diagnostics and limitations.

A green workflow only means the software completed: `report.json` can still show `collection_failure` or `links_only`. Do not mistake a graceful fallback for successful editorial processing.

Relevance filtering now requires a concrete strategic development before model submission, scores specific signals once each, and reassesses retrieved article text. Routine reviews, lists, interviews, crowdfunding and title promotions receive penalties; watchlist names alone cannot qualify. The report includes signal labels and a bounded sample of relevance exclusions. Reader-facing copy must be English, with offline language validation; evidence stays verbatim in the original language. Fallback links use English labels without attempting another paid translation. See [docs/EDITORIAL_FILTERING.md](docs/EDITORIAL_FILTERING.md).

Evidence selection now offers bounded, exact source spans in the response schema, paired with their source IDs. Independent quote validation remains strict. Reports include evidence-option counts and safe mismatch reasons, not rejected quotes or article bodies. See [docs/EVIDENCE_SELECTION.md](docs/EVIDENCE_SELECTION.md). After deploying a fix, start a **new** preview workflow rather than rerunning an old run: prepared editions are cached by run ID.

The initial registry contains 10 enabled source endpoints and two disabled candidates. The supplied source-check report dated 30-09-2026 records nine successful endpoints and an unavailable Publishers Weekly endpoint. That single run is not a guarantee of continuing availability or editorial quality. Initial browser research recognised several RSS endpoints without being able to parse them. Run **`check-sources`** for an independent, zero-model-cost source check. Failed or blocked sources appear in the report; the collector does not bypass their restrictions.

## 4. Send a real test edition

Run the same workflow in **`send-test`** mode. It sends immediately to the configured inbox, with `[TEST]` in the subject. A successful test does not use up the day's production edition and does not ping Healthchecks.

Confirm receipt and inspect the email itself. Resend accepting an API request is not proof that the message reached the inbox. Check the Resend dashboard and spam folder when necessary. Tests are recorded by GitHub run ID, so re-running the same successful test does not request another email; a new manual run creates a new test.

## 5. Configure monitoring and enable delivery

Configure the existing Healthchecks check as follows:

| Field | Value |
|---|---|
| Schedule type | Cron |
| Cron expression | `13 7 * * 1-5` |
| Timezone | `Europe/Madrid` |
| Grace time | **42 minutes** |
| Notification integration | Email to our intended monitoring inbox |

Keep this existing morning check. Success heartbeats are withheld during evening and overnight preparation, then sent from 07:13 on the edition's delivery date when the application confirms it was queued. The check allows confirmation/recovery until approximately **07:55**. Do not move its cron to the evening or to 07:55, and do not add a second expected check at 07:43. Collection and workflow failures may signal failure earlier.

After a successful `send-test` and an acceptable preview:

1. Set `NEWSLETTER_ENABLED` to `true` in repository variables.
2. Run **`arm-monitor`** once within 24 hours of that test. It verifies the recorded test had adequate source coverage, sends an explicit setup heartbeat and primes monitoring for the next expected weekday run. It sends no new newsletter and makes no model request. It does not claim that a scheduled run has already happened.
3. Confirm Healthchecks is **Up**, not New or Paused, and that its next expected check has the intended weekday/time. If manual-resume protection is enabled in Healthchecks, resume the check before arming it.

The next eligible preparation starts at 20:13 Sunday-Thursday for the following morning. Sunday prepares Monday; Friday and Saturday evenings do not prepare weekend editions. Overnight and morning recovery can queue a missing edition before 07:55. All production payloads include an explicit 08:00 Resend schedule. The 08:13 audit confirms an already-queued edition or fails without sending if it is missing.

A `send-edition` manual run follows the same production rules and requires delivery to be enabled. From 20:00 it targets tomorrow's date; overnight and during the day it targets today's date. Weekend targets are skipped, and new submissions stop at 07:55 on the target date. A queued edition can still be confirmed after the deadline without another send. Only `send-test` sends immediately, with its explicit `[TEST]` subject.

## Behaviour and safeguards

| Situation | Behaviour |
|---|---|
| No qualifying news within available coverage | Short quiet-day confirmation |
| Some sources unavailable | Newsletter includes specific coverage warnings |
| More than half the sources unavailable, or fewer than three healthy sources | Explicit collection-failure notice; failure monitoring signal |
| API unavailable, malformed output or budget guard reached | Source links only, labelled as unassessed |
| Monday | Sunday evening preparation includes weekend developments available by its collection cutoff |
| Preparation or recovery misses 07:55 | Skip the edition and signal failure; no late catch-up send |
| Repeated reports | URL/content fingerprints plus model-assisted event grouping/history |
| Uncertain email-send result | Reuse saved payload and idempotency key within bounded retry rules |
| Failure to save durable state | Stop before new external side effects where possible; do not silently reset history |
| GitHub never starts | Healthchecks detects the missed expected heartbeat after it has been armed |

The first edition considers up to four days of published items. Subsequent runs recheck a seven-day window and suppress items already assessed or reported. This supports recovery and delayed feeds, not an unlimited archive backfill. Publication dates are printed in the email. Undated items are omitted rather than presented as fresh news.

## Limits we should retain

- GitHub schedules may be delayed or dropped. Evening preparation and multiple recovery opportunities reduce timing risk but cannot guarantee an edition every morning or exact inbox arrival. A missed submission deadline never turns into an immediate production send.
- News is frozen when the edition is prepared. Overnight developments after its collection cutoff are not added to an already-queued edition.
- The API-spending guard uses configured prices and durable reservations. It is not an account-wide hard limit, tax calculation or guarantee against provider price changes. It does not include other API applications, Actions overages or email-provider overages. Check the provider dashboard as well.
- A single small model plus deterministic quote/ID/number checks is not a fact-checking service. Semantic errors, weak implications and imperfect event deduplication remain possible. We need to review early editions and adjust sources/rules.
- No paid web search, social-media monitoring, authenticated paywall access or JavaScript browser automation is included. Canadian coverage is initially mainly through broader trade reporting. See `docs/SOURCES.md` for gaps.
- Healthchecks monitors preparation and API acceptance, not end-to-end inbox delivery. Resend can still encounter delivery problems after scheduling.
- Pausing Actions does not cancel an email already scheduled at Resend. See the operations guide.

## Local development

Python 3.13 is the configured GitHub runtime. The implementation uses Python 3.10+ syntax, but the packaged test run used Python 3.13.5.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m briefing demo --output output/demo
python -m briefing check-sources
```

`demo` is an explicitly fictional layout example and makes no network calls. For real local previews, export `OPENAI_API_KEY` in the shell and run `python -m briefing preview`. The application does not automatically load `.env` files. Local state lives in `.local/state.json` and is excluded from Git. Never run local production delivery alongside GitHub with a separate state ledger; that would bypass shared duplicate prevention.

## Repository map

```text
.github/workflows/briefing.yml   Scheduler, manual modes and artifact retention
.github/workflows/tests.yml      Offline tests; no secrets
briefing/                       Collector, editor, renderer, state and delivery
briefing/relevance.py           Material-development signals and routine-content penalties
briefing/language.py            Deterministic offline English-output check
briefing/evidence.py            Original-language quote options and safe mismatch diagnostics
config/settings.json            Limits, model and defaults
config/sources.json             Enabled feeds/pages and disabled candidates
config/watchlist.json           Names/aliases; no assumed current company statuses
config/komotic.md                Trusted product/business context
config/editorial.md              Editorial and source-grounding rules
config/briefing.schema.json      Structured response contract
examples/                       Fictional rendered example only
tests/                          Offline parser, budget, editor and workflow tests
docs/OPERATIONS.md              Monitoring, cost, recovery and maintenance
docs/SOURCES.md                 Source verification notes and known gaps
docs/VALIDATION.md              What was and was not tested
docs/DIAGNOSTICS_FIX.md         Report fields, rejection codes and fix history
docs/EDITORIAL_FILTERING.md     Relevance and English-output rules, diagnostics and limits
docs/RECOVERY.md                Safe restoration from the complete archive
```

## Provider documentation

Documentation checked on 30-09-2026. These explain provider behaviour, not a claim that this repository has been deployed.

- GitHub schedule/timezone semantics and possible delay: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- GitHub repository contents API for state: https://docs.github.com/en/rest/repos/contents
- OpenAI GPT-4.1 mini pricing and supported features: https://developers.openai.com/api/docs/models/gpt-4.1-mini
- OpenAI structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Resend scheduled email: https://resend.com/docs/dashboard/emails/schedule-email
- Resend idempotency window: https://resend.com/docs/dashboard/emails/idempotency-keys
- Healthchecks monitoring/grace behaviour: https://healthchecks.io/docs/
