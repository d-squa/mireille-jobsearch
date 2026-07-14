# Deploying to GitHub Actions

This runs the daily lead discovery pipeline entirely on GitHub's servers -
no local Python, no admin rights, no laptop that needs to stay on.

## 1. Get the code into your repository

Since you can't run `git`/`pip` locally, the easiest path is GitHub's
web upload:

1. Go to https://github.com/d-squa/leads
2. Click **Add file → Upload files**
3. Drag the entire `lead-discovery` folder (all of it, including the
   `.github` folder) into the browser window. Modern Chrome/Edge/Firefox
   preserve the folder structure on drop.
4. Commit directly to `main`.

**Do NOT upload `.env` or `credentials/service_account.json`** if you have
local copies with real secrets in them - those go into GitHub Secrets
instead (step 3 below), never into the repository itself.

## 2. Confirm the database file made it in

`data/lead_discovery.db` (an initialized-but-empty SQLite file) needs to
be in the repo - it's how the dedup ledger persists between runs, since
every GitHub Actions run starts on a brand new machine. It's a small
binary file; it should upload fine via the same drag-and-drop.

## 3. Add repository secrets

Go to **Settings → Secrets and variables → Actions → New repository
secret** and add:

| Secret name | Value |
|---|---|
| `JOOBLE_API_KEY` | Your Jooble API key |
| `GOOGLE_SHEET_ID` | `1Vz1x7Z09lzhXwALGE0TvTzZrFp-I2Pba3LWIVdGRMQE` (just the ID, not the full URL) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | The **entire contents** of your service account JSON file, pasted as-is |
| `ADZUNA_APP_ID` | Leave unset until approved - the workflow handles a blank value fine |
| `ADZUNA_APP_KEY` | Same as above |

Non-secret config (search terms, score threshold, etc.) is already set
directly in `.github/workflows/daily-run.yml` - edit that file in GitHub
if you want to change them, no secret needed.

## 4. Share the Google Sheet with the service account

Open your sheet → **Share** → add the `client_email` from your service
account JSON (looks like `...@actiplan-444114.iam.gserviceaccount.com`)
as an **Editor**. Without this the export step will fail every run.

## 5. Test it

Go to the **Actions** tab → **Daily Lead Discovery Run** → **Run workflow**
button (this is the `workflow_dispatch` trigger - it lets you run on
demand instead of waiting for the schedule). Watch the run's log output
directly in the browser - this is your primary way to see what happened
each day, equivalent to what main.py would print locally.

## 6. Ongoing operation

Once the test run succeeds, it runs automatically every day at 06:00 UTC
(edit the `cron` line in the workflow file to change the time). Each run:
commits the updated `data/lead_discovery.db` back to the repo (small,
automated commits from `github-actions[bot]`) and exports any new leads
to your Google Sheet.

## Changing search terms, scoring, or other settings

Non-secret config (search terms, countries, minimum score, log level,
etc.) lives in **`config/pipeline.env`** - a plain text file, not YAML,
not a secret. To change it:

1. Open `config/pipeline.env` directly on GitHub (click the file, then
   the pencil icon to edit).
2. Change the value you need, e.g.:
   ```
   SEARCH_TERMS=paid media,performance marketing,media buyer,paid social,PPC,media planner
   ```
3. Commit directly to `main`.

The next run (scheduled or manually triggered) picks up the change
automatically - no need to touch the workflow files in `.github/workflows/`
at all. Those only handle secrets and orchestration now.

## Recovering from a manually-cleared Google Sheet

If you delete rows from the sheet directly, the pipeline won't
automatically re-send them - it tracks "already exported" in the
database, not by re-reading the sheet. To recover:

Go to **Actions → Reset Export Status → Run workflow**. This resets
every lead's export flag (the leads themselves were never deleted,
only marked as already-sent) so the next Daily run re-sends everything
currently in the database.

## Rotating the service account key

Since the key was shared in a chat conversation, rotate it once this is
confirmed working: Google Cloud Console → IAM & Admin → Service Accounts
→ your account → Keys → delete the old key, generate a new one, and
update the `GOOGLE_SERVICE_ACCOUNT_JSON` secret with the new file's
contents.
