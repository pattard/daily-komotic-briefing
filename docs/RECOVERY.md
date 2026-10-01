# Restore the complete repository

Date: 30-09-2026

This is a complete application-source package, not a patch. It contains all files
from the original repository package plus the diagnostics and bounded source-selection
fixes already applied, including `.github`, `.gitignore` and `.env.example`. No
separate patch is needed. See `SOURCE_SELECTION_FIX.md` for the latest changes.

## Preserve before copying

Keep `NEWSLETTER_ENABLED=false` while restoring and testing. Back up the existing
checkout, including hidden files, before copying over it. Keep that backup outside
the repository and private if it contains local credentials.

Do not delete or replace `.git`, real `.env` files, `.local/`, or the remote
`briefing-state` branch. This archive contains no Git history, runtime state or
secret values. It cannot recreate any of those if they were deleted. Do not reset
history or spending records to make a run pass.

Existing repository variables and secrets should remain in place. We are restoring
source files into the existing repository, not creating a replacement GitHub repo.

## Copy files safely

Extract `daily-komotic-briefing-source-selection-complete.zip` to a temporary location separate from
our existing checkout. Its top-level folder is `daily-komotic-briefing`.

From a terminal, change to the existing checkout. Adjust these two example paths
to the actual locations before running them:

```bash
cd /path/to/existing/daily-komotic-briefing
rsync -av /path/to/extracted/daily-komotic-briefing/ ./
```

The source path ends with `/`: copy its contents, not another nested repository
folder. Do not add `--delete`. This copy includes hidden files, replaces matching
application files, and leaves other existing files in place. The source and
destination must be different directories.

An alternative on systems without `rsync`, from the existing repository root:

```bash
cp -R /path/to/extracted/daily-komotic-briefing/. .
```

Review the result before committing:

```bash
git status --short
git diff

git add .github briefing config docs examples tests requirements.txt \
  README.md .gitignore .env.example

git diff --cached --stat
git diff --cached

git commit -m "Replace rejected collection candidates within bounded fetch limits"
git push
```

Make sure no credentials are being committed. Do not use `git reset --hard`,
`git clean`, delete the repository, or force-push as part of this restoration.
If work is on a feature branch, review and merge through the normal process so
the new workflow runs use the updated default branch.

The optional earlier `.github/workflows/setup-check.yml` was not in either saved
archive, so this package does not recreate it. Preserve an existing copy or recover
it from Git history if required. The complete operational workflows are included:
`.github/workflows/briefing.yml` and `.github/workflows/tests.yml`. They do not
depend on the optional setup check.

## Test from the updated default branch

1. Run the Tests workflow and confirm all 116 automated tests pass.
2. Start a new Daily Komotic Briefing run with mode `check-sources`.
3. Its artifact should contain only `report.json`, with these distinguishing fields:

```json
{
  "run_mode": "check-sources",
  "selection_version": 2,
  "edition_status": "not_generated",
  "analysis": {
    "status": "not_requested",
    "model_requested": false
  }
}
```

4. Start a new `preview` run. If it still produces `links_only`, inspect
   `analysis.validation_errors` and `editorial_warnings` in the new report.
   The existing fix exposes the rejection reasons; restoration does not guarantee
   that the live newsletter will pass its evidence checks.
5. Keep `NEWSLETTER_ENABLED=false` until the preview is acceptable and a
   `send-test` email is confirmed. Monitoring and activation steps are in README.md.

Use new workflow runs, not re-runs of an old run prepared before the code update.

## Settings retained

- Sender: `Daily Komotic Briefing <komotic@briefings.wearegoat.com>`.
- Recipient: `paul.attard@wearegoat.com`.
- Intended delivery: 08:00, Monday-Friday, `Europe/Madrid`.
- Preparation/recovery: 07:13 and 07:43 in the same timezone.
- Application model-spending guard: USD 1.50 per month.

Repository variable overrides continue to take precedence over the bundled defaults.
No credentials, state schema, sources, model, schedule or scoring rules were changed.
The collector now replaces rejected candidates within separate fetch-count and
between-batch time limits. Live source availability and editorial quality still
require testing.
