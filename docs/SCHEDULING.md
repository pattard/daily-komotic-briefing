# Advance preparation with GitHub Actions

The 01-10-2026 and 02-10-2026 scheduled runs were created at 13:34 and 13:04
Madrid time. Their runners started within seconds, but the scheduled triggers
were hours later than the 07:13/07:43 preparation window. The old noon cutoff
prevented those sends but also allowed immediate delayed editions before noon.

The application now prepares the next weekday's edition in advance using the
existing GitHub Actions, state branch, Resend and Healthchecks services. There
is no additional scheduler, database or account to configure.

## Schedule

All times use `Europe/Madrid`, including daylight-saving changes.

| Time | Days | Purpose |
|---|---|---|
| 20:13 | Sunday-Thursday | Prepare tomorrow's edition and queue its 08:00 send |
| 22:13 | Sunday-Thursday | Recover the same edition |
| 02:13, 05:13 | Monday-Friday | Overnight recovery |
| 07:13, 07:43 | Monday-Friday | Recover or confirm the queue record; morning monitoring heartbeat |
| 07:55 | Monday-Friday | Hard application deadline; no new production submission at or after this time |
| 08:00 | Monday-Friday | Requested Resend send time |
| 08:13 | Monday-Friday | Audit the queue record; fail if missing, with no catch-up send |

From 20:00 the application targets tomorrow's calendar date. Before 20:00 it
targets today's date. Saturday/Sunday targets are skipped rather than advanced
to Monday: Monday's news is prepared on Sunday evening. An evening trigger
delayed past midnight can recover the same edition until the deadline. A late
daytime run can confirm an already-queued edition, but cannot create/send a
missed edition. The target remains fixed if collection crosses midnight.

Each production payload contains the explicit future `scheduled_at` timestamp.
The edition date and idempotency key are shared by evening and morning runs.
An ambiguous send reuses its immutable payload and key, within the existing
three-attempt/23-hour limits and the new submission deadline. Legacy pending
payloads without a schedule or with a different send time stop for dashboard
reconciliation; the application never silently modifies them.

## News and monitoring

The edition is frozen at collection/preparation time. Recovery does not refresh
an edition already accepted by Resend, so overnight developments after the
printed collection cutoff are considered for a later newsletter. The subject
and heading show the delivery date; the footer retains the actual collection
cutoff and explains the advance preparation.

Keep the existing Healthchecks cron `13 7 * * 1-5`, timezone `Europe/Madrid`,
and 42-minute grace. Successful evening/overnight preparation withholds the
heartbeat. Success is signalled by morning confirmation from 07:13 on the
delivery date. Failure signals can occur earlier. No monitoring settings change
is required if the check already uses these values. If all morning triggers
are delayed/dropped, monitoring can alert even though Resend has an evening-
queued edition; its signal confirms the queue record, not inbox delivery.

GitHub can still delay/drop all opportunities. The application guarantees it
does not request an immediate late production send; it cannot guarantee that
an edition is available every morning or that mail providers deliver it at
exactly 08:00.

## Rollout

1. Run the offline Tests workflow for the updated code, then merge/push it to
   the default branch so GitHub uses the new schedule.
2. Keep `NEWSLETTER_TIMEZONE=Europe/Madrid`, `NEWSLETTER_SEND_TIME=08:00` and
   the existing secrets. No new variable or secret is required. Confirm the
   existing Healthchecks schedule matches the values above.
3. Preserve `briefing-state` and its ledger. Already-accepted editions are
   recognised without duplicate submissions. Updating this code does not
   cancel any email already queued in Resend.
4. If delivery is already enabled, the next eligible evening/overnight run
   prepares the next weekday edition automatically. If disabled, follow the
   preview, explicit `send-test`, enabling and `arm-monitor` steps in README.md.
5. Inspect the first production report for `edition_date`, `prepared_at`,
   `scheduled_at` and `submission_deadline`. In Resend, confirm the saved
   schedule is 08:00 Madrid time. Morning recovery should log `already_queued`
   and make no additional model/email request.

Manual `send-edition` follows the production deadline. Manual `send-test`
continues to send immediately with `[TEST]`; it does not consume a production
edition or signal the production monitor.
