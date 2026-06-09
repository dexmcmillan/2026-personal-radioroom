# URL Monitor — Design Spec

**Date:** 2026-06-09
**Status:** Approved

## Overview

A self-service URL monitoring tool hosted on GitHub Pages. Users submit a URL, their email address, and a check frequency via a web form. A GitHub Actions cron job checks each URL at the specified frequency and emails a unified text diff when the page content changes. No login required — users unsubscribe via a token link in every email.

This is a new standalone project, separate from `2026-tgam-urlmonitor`.

## Repository Layout

```
url-monitor/
├── index.html                      # Subscribe form (GitHub Pages)
├── unsubscribe.html                # Unsubscribe page (reads ?token= from URL)
├── data/
│   └── subscriptions.json          # All active subscriptions
├── scripts/
│   └── check_urls.py               # URL checker and email sender
├── .github/workflows/
│   ├── add_subscription.yml        # workflow_dispatch: add new subscription
│   ├── check_urls.yml              # cron: hourly, processes due subscriptions
│   └── remove_subscription.yml    # workflow_dispatch: remove by token
└── pyproject.toml
```

**Hosting note:** GitHub Pages for private repos requires GitHub Pro/Team. Two valid options:
1. Single private repo + GitHub Pro (recommended — keeps emails private)
2. Two repos: a public repo for `index.html` + `unsubscribe.html` only, a private repo for `data/` and `.github/workflows/`

## Components

### Frontend — index.html

Split layout: left panel explains what the tool does; right panel is the subscription form.

**Form fields:**
- URL (text input, required, basic URL validation)
- Email (email input, required)
- Frequency (dropdown: Hourly / Daily / Weekly)

**Submit flow:**
1. JavaScript validates inputs client-side
2. Calls `POST /repos/{owner}/{repo}/actions/workflows/add_subscription.yml/dispatches` with `inputs: { url, email, frequency }`
3. Authorization header uses the embedded `GH_WORKFLOW_PAT`
4. Shows success: "You'll receive a confirmation email shortly."
5. Shows error on API failure with a retry prompt

**PAT security:** A fine-grained GitHub PAT scoped to `Actions: write` for this repo only, hardcoded in the JS source. Acceptable tradeoff for an internal tool — the PAT cannot read data or write files directly. Because it's embedded in a public JS file, do not reuse this PAT for anything else.

### Frontend — unsubscribe.html

Reads `?token=` from the URL query string on page load. Calls `remove_subscription.yml` via `workflow_dispatch` with `inputs: { token }`. Because `workflow_dispatch` returns immediately (before the workflow completes), the page cannot confirm whether the token was valid. It displays: "Unsubscribe request received — you'll be removed within a minute." on API success, or an error message if the API call itself fails.

### Data model — data/subscriptions.json

Flat JSON array. Each entry:

```json
{
  "id": "a3f2b1c4",
  "url": "https://example.com/page",
  "email": "user@globeandmail.com",
  "frequency": "daily",
  "created_at": "2026-06-09T14:00:00Z",
  "unsubscribe_token": "d9e8f7a6b5c4",
  "last_checked": null,
  "last_hash": null
}
```

- `id`: random 8-char hex
- `unsubscribe_token`: random 12-char hex, embedded in every outgoing email link
- `last_checked`: ISO datetime, null until first check
- `last_hash`: SHA-256 of extracted page text, null until first check

### Workflow — add_subscription.yml

Trigger: `workflow_dispatch` with inputs `url`, `email`, `frequency`

Steps:
1. Read `data/subscriptions.json`
2. Generate `id` (8-char hex) and `unsubscribe_token` (12-char hex)
3. Append new entry with `last_checked: null`, `last_hash: null`
4. Commit and push updated JSON with message `add subscription {id}`
5. Do not send an email — the first run of `check_urls.yml` sends the welcome

### Workflow — check_urls.yml

Trigger: `schedule: cron: '0 * * * *'` (every hour on the hour)

Steps:
1. Run `uv run python scripts/check_urls.py`
2. Script reads `subscriptions.json`
3. For each subscription, determine if due:
   - `hourly`: always
   - `daily`: `last_checked` is null or ≥24h ago
   - `weekly`: `last_checked` is null or ≥7 days ago
4. For each due subscription:
   a. Fetch URL with `requests`; fall back to headless `playwright` if `requests` raises an exception or returns a 4xx/5xx status
   b. Extract body text via BeautifulSoup (strip `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, cookie banners)
   c. Compute SHA-256 of extracted text
   d. If `last_hash` is null (first check): send welcome email ("Snapshot taken — you'll be notified when this changes"), set `last_hash` and `last_checked`
   e. If hash differs from `last_hash`: send diff email, update `last_hash` and `last_checked`
   f. If hash matches: update `last_checked` only
5. Commit updated `subscriptions.json` back with message `update checks {timestamp}`

### Workflow — remove_subscription.yml

Trigger: `workflow_dispatch` with input `token`

Steps:
1. Read `subscriptions.json`
2. Filter out entry where `unsubscribe_token == token`
3. If no match found: exit successfully (idempotent)
4. Commit and push with message `remove subscription`

### Python checker — scripts/check_urls.py

Pattern matches the existing `2026-tgam-urlmonitor` project:

- `requests` + `BeautifulSoup` — primary fetch and text extraction
- `playwright` (headless Chromium) — fallback for JS-rendered pages
- `difflib.unified_diff` — text comparison for diff emails
- `hashlib.sha256` — content hashing
- `smtplib` + `email.mime` — Gmail SMTP sending

### Email format

**Welcome email (first check):**
- Subject: `Now watching: {domain}`
- Body: URL, frequency, "we'll email you when this changes", unsubscribe link

**Change notification email:**
- Subject: `Change detected: {domain}`
- Body:
  - URL and detection timestamp
  - HTML-formatted unified diff (added lines highlighted green, removed lines red)
  - "View page" link
  - Unsubscribe link at the bottom

## Error Handling

| Scenario | Behaviour |
|---|---|
| URL fetch fails (requests + playwright both fail) | Log error, skip subscription for this run; do not update `last_checked` so it retries next run |
| GitHub API call fails on form submit | Show error to user, prompt to try again |
| Invalid/expired token on unsubscribe | Show "Token not found" message, no crash |
| Concurrent workflow runs both writing subscriptions.json | Last writer wins — acceptable race condition at this scale for v1 |

## Testing

- `tests/test_check_urls.py`: unit tests for text extraction, hashing, diff generation, and "due" scheduling logic (mirrors existing urlmonitor test patterns)
- Manual smoke test: subscribe with a test URL, verify welcome email arrives, modify the target page, run checker manually, verify diff email

## Secrets Required

Set once in GitHub repo Settings → Secrets and Variables → Actions:

| Secret | Value |
|---|---|
| `GMAIL_USER` | Gmail address used as sender |
| `GMAIL_APP_PASSWORD` | Gmail app password (not account password) |

**Note:** `GH_WORKFLOW_PAT` is NOT stored as a GitHub Actions secret. It is hardcoded in the frontend JS source file (`index.html` / `unsubscribe.html`). Create it as a fine-grained PAT with `Actions: write` for this repo only, and do not reuse it elsewhere.
