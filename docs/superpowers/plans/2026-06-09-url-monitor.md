# URL Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone GitHub-native URL change monitoring service where users subscribe via a web form and receive HTML diff emails when watched pages change.

**Architecture:** Static GitHub Pages frontend (split-layout form) triggers GitHub Actions `workflow_dispatch` to manage subscriptions stored in `data/subscriptions.json`. An hourly GitHub Actions cron job checks due URLs, compares SHA-256 hashes against stored text snapshots, and sends Gmail SMTP notifications with HTML diffs. No login or external services required beyond Gmail.

**Tech Stack:** Python 3.12, uv, requests, BeautifulSoup4, playwright, pytest, GitHub Actions, GitHub Pages, Gmail SMTP

**Spec gap resolved:** The design spec stores only `last_hash` per subscription, but diff generation requires the previous page text. This plan adds `data/snapshots/{id}.txt` (one file per subscription, containing last-seen extracted text) so diffs can be computed. The hash in `subscriptions.json` is still used for quick change detection; the snapshot file is only read when a change is confirmed.

---

## File Map

| File | Responsibility |
|---|---|
| `scripts/check_urls.py` | URL fetching, text extraction, hashing, diff generation, email building, email sending, main loop |
| `scripts/add_subscription.py` | Append new subscription entry to subscriptions.json |
| `scripts/remove_subscription.py` | Remove subscription by token, delete snapshot file |
| `data/subscriptions.json` | Flat JSON array of all active subscriptions |
| `data/snapshots/{id}.txt` | Last-seen extracted page text per subscription |
| `.github/workflows/add_subscription.yml` | workflow_dispatch: receive inputs, run add script, commit |
| `.github/workflows/check_urls.yml` | Hourly cron: run checker, commit updated state |
| `.github/workflows/remove_subscription.yml` | workflow_dispatch: receive token, run remove script, commit |
| `index.html` | Subscribe form (GitHub Pages, split layout) |
| `unsubscribe.html` | Unsubscribe page (reads ?token= from URL, calls remove workflow) |
| `tests/conftest.py` | sys.path setup for importing from scripts/ |
| `tests/test_check_urls.py` | Unit + integration tests for all checker logic |
| `tests/test_subscriptions.py` | Unit tests for add and remove scripts |
| `pyproject.toml` | Python dependencies |
| `.python-version` | Pins Python 3.12 |
| `.gitignore` | Excludes venv, cache, superpowers |

---

### Task 1: Initialize the new repo

**Files:**
- Create: `~/Documents/Code/url-monitor/` (new project directory)
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `data/subscriptions.json`
- Create: `data/snapshots/.gitkeep`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create the project directory and initialize git**

```bash
cd ~/Documents/Code
mkdir url-monitor && cd url-monitor
git init
echo "3.12" > .python-version
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "url-monitor"
version = "0.1.0"
description = "Self-service URL change monitoring with email notifications"
requires-python = ">=3.12"
dependencies = [
    "beautifulsoup4>=4.12",
    "playwright>=1.40",
    "requests>=2.31",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
]
```

- [ ] **Step 3: Install dependencies**

```bash
uv sync
uv run playwright install chromium
```

Expected: packages installed, no errors.

- [ ] **Step 4: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
.env
.superpowers/
```

- [ ] **Step 5: Create directory structure and initial data files**

```bash
mkdir -p data/snapshots scripts tests .github/workflows
echo "[]" > data/subscriptions.json
touch data/snapshots/.gitkeep
```

- [ ] **Step 6: Create tests/conftest.py**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
```

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "chore: initialize url-monitor project"
```

---

### Task 2: Text extraction, hashing, and due-check logic

**Files:**
- Create: `scripts/check_urls.py` (utility functions only — more added in later tasks)
- Create: `tests/test_check_urls.py` (partial)

- [ ] **Step 1: Write failing tests**

Create `tests/test_check_urls.py`:

```python
from datetime import datetime, timezone, timedelta
import pytest
from check_urls import extract_text, hash_content, is_due


def test_extract_text_removes_nav():
    html = "<html><body><nav>Nav</nav><p>Content</p></body></html>"
    result = extract_text(html)
    assert "Content" in result
    assert "Nav" not in result


def test_extract_text_removes_script():
    html = "<html><body><script>var x=1;</script><p>Content</p></body></html>"
    result = extract_text(html)
    assert "Content" in result
    assert "var x" not in result


def test_extract_text_removes_footer():
    html = "<html><body><p>Content</p><footer>Footer</footer></body></html>"
    result = extract_text(html)
    assert "Content" in result
    assert "Footer" not in result


def test_extract_text_no_blank_lines():
    html = "<html><body><p>A</p><p>B</p></body></html>"
    result = extract_text(html)
    assert "" not in result.splitlines()


def test_hash_content_stable():
    assert hash_content("hello") == hash_content("hello")


def test_hash_content_differs():
    assert hash_content("hello") != hash_content("world")


def test_hash_content_is_64_char_hex():
    h = hash_content("test")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_is_due_null_last_checked():
    sub = {"last_checked": None, "frequency": "daily"}
    assert is_due(sub, datetime.now(timezone.utc))


def test_is_due_hourly_not_yet():
    now = datetime.now(timezone.utc)
    sub = {"last_checked": (now - timedelta(minutes=30)).isoformat(), "frequency": "hourly"}
    assert not is_due(sub, now)


def test_is_due_hourly_past():
    now = datetime.now(timezone.utc)
    sub = {"last_checked": (now - timedelta(hours=2)).isoformat(), "frequency": "hourly"}
    assert is_due(sub, now)


def test_is_due_daily_not_yet():
    now = datetime.now(timezone.utc)
    sub = {"last_checked": (now - timedelta(hours=12)).isoformat(), "frequency": "daily"}
    assert not is_due(sub, now)


def test_is_due_daily_past():
    now = datetime.now(timezone.utc)
    sub = {"last_checked": (now - timedelta(hours=25)).isoformat(), "frequency": "daily"}
    assert is_due(sub, now)


def test_is_due_weekly_not_yet():
    now = datetime.now(timezone.utc)
    sub = {"last_checked": (now - timedelta(days=3)).isoformat(), "frequency": "weekly"}
    assert not is_due(sub, now)


def test_is_due_weekly_past():
    now = datetime.now(timezone.utc)
    sub = {"last_checked": (now - timedelta(days=8)).isoformat(), "frequency": "weekly"}
    assert is_due(sub, now)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_check_urls.py -v
```

Expected: `ModuleNotFoundError: No module named 'check_urls'`

- [ ] **Step 3: Create scripts/check_urls.py with the utility functions**

```python
import hashlib
import json
import os
import smtplib
import difflib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

SUBSCRIPTIONS_FILE = Path(__file__).parent.parent / "data" / "subscriptions.json"
SNAPSHOTS_DIR = Path(__file__).parent.parent / "data" / "snapshots"


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text(separator="\n").splitlines() if ln.strip()]
    return "\n".join(lines)


def hash_content(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def is_due(sub: dict, now: datetime) -> bool:
    if sub["last_checked"] is None:
        return True
    last = datetime.fromisoformat(sub["last_checked"])
    thresholds = {
        "hourly": timedelta(hours=1),
        "daily": timedelta(hours=24),
        "weekly": timedelta(days=7),
    }
    return (now - last) >= thresholds[sub["frequency"]]
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_check_urls.py -v
```

Expected: 13 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_urls.py tests/test_check_urls.py tests/conftest.py
git commit -m "feat: add text extraction, hashing, and due-check logic"
```

---

### Task 3: Diff generation and email body builders

**Files:**
- Modify: `scripts/check_urls.py` (append diff and email functions)
- Modify: `tests/test_check_urls.py` (append tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_check_urls.py`:

```python
from check_urls import generate_diff, build_diff_html, build_change_email, build_welcome_email


def test_generate_diff_detects_addition():
    diff = generate_diff("line one\n", "line one\nline two\n")
    added = [l for l in diff if l.startswith("+") and not l.startswith("+++")]
    assert any("line two" in l for l in added)


def test_generate_diff_detects_removal():
    diff = generate_diff("line one\nline two\n", "line one\n")
    removed = [l for l in diff if l.startswith("-") and not l.startswith("---")]
    assert any("line two" in l for l in removed)


def test_generate_diff_empty_when_identical():
    diff = generate_diff("same\n", "same\n")
    meaningful = [l for l in diff if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    assert meaningful == []


def test_build_diff_html_green_for_additions():
    html = build_diff_html(["+new line"])
    assert "#e6ffed" in html
    assert "new line" in html


def test_build_diff_html_red_for_removals():
    html = build_diff_html(["-old line"])
    assert "#ffeef0" in html
    assert "old line" in html


def test_build_diff_html_skips_markers():
    html = build_diff_html(["+++file.txt", "---file.txt"])
    assert "#e6ffed" not in html
    assert "#ffeef0" not in html


def make_sub():
    return {
        "id": "a1b2c3d4",
        "url": "https://example.com/page",
        "email": "user@test.com",
        "frequency": "daily",
        "unsubscribe_token": "tok123",
    }


def test_build_change_email_subject_contains_domain(monkeypatch):
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")
    subject, _ = build_change_email(make_sub(), ["+added"])
    assert "example.com" in subject


def test_build_change_email_body_contains_unsubscribe(monkeypatch):
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")
    _, body = build_change_email(make_sub(), ["+added"])
    assert "tok123" in body
    assert "unsubscribe" in body.lower()


def test_build_change_email_body_contains_diff(monkeypatch):
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")
    _, body = build_change_email(make_sub(), ["+added line"])
    assert "added line" in body


def test_build_welcome_email_subject_contains_domain(monkeypatch):
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")
    subject, _ = build_welcome_email(make_sub())
    assert "example.com" in subject


def test_build_welcome_email_body_contains_frequency(monkeypatch):
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")
    _, body = build_welcome_email(make_sub())
    assert "daily" in body


def test_build_welcome_email_body_contains_unsubscribe(monkeypatch):
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")
    _, body = build_welcome_email(make_sub())
    assert "tok123" in body
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_check_urls.py -v -k "diff or email"
```

Expected: `ImportError: cannot import name 'generate_diff'`

- [ ] **Step 3: Append diff and email functions to scripts/check_urls.py**

```python
def generate_diff(old_text: str, new_text: str) -> list[str]:
    return list(difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        lineterm="",
    ))


def build_diff_html(diff_lines: list[str]) -> str:
    rows = []
    for line in diff_lines:
        if line.startswith("+") and not line.startswith("+++"):
            rows.append(
                f'<div style="background:#e6ffed;color:#22863a;'
                f'font-family:monospace;white-space:pre-wrap;">{line}</div>'
            )
        elif line.startswith("-") and not line.startswith("---"):
            rows.append(
                f'<div style="background:#ffeef0;color:#b31d28;'
                f'font-family:monospace;white-space:pre-wrap;">{line}</div>'
            )
        else:
            rows.append(
                f'<div style="font-family:monospace;color:#888;'
                f'white-space:pre-wrap;">{line}</div>'
            )
    return "\n".join(rows)


def build_change_email(sub: dict, diff_lines: list[str]) -> tuple[str, str]:
    domain = urlparse(sub["url"]).netloc
    subject = f"Change detected: {domain}"
    pages_host = os.environ.get("GITHUB_PAGES_HOST", "")
    unsub_url = f"https://{pages_host}/unsubscribe.html?token={sub['unsubscribe_token']}"
    diff_html = build_diff_html(diff_lines)
    body = f"""<html><body>
<p>A page you're watching was updated.</p>
<p><strong>URL:</strong> <a href="{sub['url']}">{sub['url']}</a><br>
<strong>Detected:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>
<hr>
<p><strong>What changed:</strong></p>
{diff_html}
<hr>
<p><a href="{sub['url']}">View page →</a></p>
<p style="font-size:0.8em;color:#999;">
  You subscribed to this URL. <a href="{unsub_url}">Unsubscribe</a>
</p>
</body></html>"""
    return subject, body


def build_welcome_email(sub: dict) -> tuple[str, str]:
    domain = urlparse(sub["url"]).netloc
    subject = f"Now watching: {domain}"
    pages_host = os.environ.get("GITHUB_PAGES_HOST", "")
    unsub_url = f"https://{pages_host}/unsubscribe.html?token={sub['unsubscribe_token']}"
    body = f"""<html><body>
<p>We've taken a snapshot of <a href="{sub['url']}">{sub['url']}</a>.</p>
<p>You'll receive an email when this page changes.<br>
Check frequency: <strong>{sub['frequency']}</strong></p>
<p style="font-size:0.8em;color:#999;">
  <a href="{unsub_url}">Unsubscribe at any time</a>
</p>
</body></html>"""
    return subject, body
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/test_check_urls.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_urls.py tests/test_check_urls.py
git commit -m "feat: add diff generation and email body builders"
```

---

### Task 4: Email sending

**Files:**
- Modify: `scripts/check_urls.py` (append send_email)
- Modify: `tests/test_check_urls.py` (append test)

- [ ] **Step 1: Write failing test**

Append to `tests/test_check_urls.py`:

```python
from unittest.mock import patch, MagicMock
from check_urls import send_email


def test_send_email_calls_smtp(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "sender@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "secret")

    with patch("smtplib.SMTP_SSL") as mock_smtp:
        instance = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=instance)
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
        send_email("to@example.com", "Subject", "<p>Body</p>")

    mock_smtp.assert_called_once_with("smtp.gmail.com", 465)
    instance.login.assert_called_once_with("sender@gmail.com", "secret")
    assert instance.sendmail.call_count == 1
    args = instance.sendmail.call_args[0]
    assert args[0] == "sender@gmail.com"
    assert args[1] == "to@example.com"
```

- [ ] **Step 2: Run failing test**

```bash
uv run pytest tests/test_check_urls.py::test_send_email_calls_smtp -v
```

Expected: `ImportError: cannot import name 'send_email'`

- [ ] **Step 3: Append send_email to scripts/check_urls.py**

```python
def send_email(to: str, subject: str, html_body: str) -> None:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.sendmail(gmail_user, to, msg.as_string())
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/test_check_urls.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_urls.py tests/test_check_urls.py
git commit -m "feat: add Gmail SMTP email sending"
```

---

### Task 5: Snapshot I/O and main check loop

**Files:**
- Modify: `scripts/check_urls.py` (append fetch_url, snapshot helpers, main)
- Modify: `tests/test_check_urls.py` (append integration tests for main loop)

- [ ] **Step 1: Write failing tests for main loop**

Append to `tests/test_check_urls.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch
from check_urls import main, hash_content


def _make_data_dir(tmp_path, subs):
    data = tmp_path / "data"
    data.mkdir()
    (data / "snapshots").mkdir()
    (data / "subscriptions.json").write_text(json.dumps(subs))
    return tmp_path


def test_main_skips_non_due_subscriptions(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    subs = [{
        "id": "aa", "url": "https://example.com", "email": "a@b.com",
        "frequency": "daily", "created_at": now.isoformat(),
        "unsubscribe_token": "tok",
        "last_checked": now.isoformat(),  # checked just now — not due
        "last_hash": "abc",
    }]
    tmp = _make_data_dir(tmp_path, subs)
    monkeypatch.setattr("check_urls.SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json")
    monkeypatch.setattr("check_urls.SNAPSHOTS_DIR", tmp / "data" / "snapshots")
    monkeypatch.setenv("GMAIL_USER", "x@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pass")
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")

    with patch("check_urls.fetch_url") as mock_fetch, \
         patch("check_urls.send_email") as mock_send:
        main()
        mock_fetch.assert_not_called()
        mock_send.assert_not_called()


def test_main_sends_welcome_on_first_check(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    subs = [{
        "id": "bb", "url": "https://example.com", "email": "a@b.com",
        "frequency": "hourly", "created_at": now.isoformat(),
        "unsubscribe_token": "tok",
        "last_checked": None, "last_hash": None,
    }]
    tmp = _make_data_dir(tmp_path, subs)
    monkeypatch.setattr("check_urls.SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json")
    monkeypatch.setattr("check_urls.SNAPSHOTS_DIR", tmp / "data" / "snapshots")
    monkeypatch.setenv("GMAIL_USER", "x@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pass")
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")

    with patch("check_urls.fetch_url", return_value="<html><body><p>Hello</p></body></html>"), \
         patch("check_urls.send_email") as mock_send:
        main()
        mock_send.assert_called_once()
        assert "Now watching" in mock_send.call_args[0][1]

    updated = json.loads((tmp / "data" / "subscriptions.json").read_text())
    assert updated[0]["last_hash"] is not None
    assert updated[0]["last_checked"] is not None


def test_main_sends_change_email_when_content_differs(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    old_hash = hash_content("old content")
    subs = [{
        "id": "cc", "url": "https://example.com", "email": "a@b.com",
        "frequency": "hourly", "created_at": now.isoformat(),
        "unsubscribe_token": "tok",
        "last_checked": (now - timedelta(hours=2)).isoformat(),
        "last_hash": old_hash,
    }]
    tmp = _make_data_dir(tmp_path, subs)
    (tmp / "data" / "snapshots" / "cc.txt").write_text("old content")
    monkeypatch.setattr("check_urls.SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json")
    monkeypatch.setattr("check_urls.SNAPSHOTS_DIR", tmp / "data" / "snapshots")
    monkeypatch.setenv("GMAIL_USER", "x@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pass")
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")

    with patch("check_urls.fetch_url", return_value="<html><body><p>new content</p></body></html>"), \
         patch("check_urls.send_email") as mock_send:
        main()
        mock_send.assert_called_once()
        assert "Change detected" in mock_send.call_args[0][1]


def test_main_no_email_when_content_unchanged(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    text = "same content"
    subs = [{
        "id": "dd", "url": "https://example.com", "email": "a@b.com",
        "frequency": "hourly", "created_at": now.isoformat(),
        "unsubscribe_token": "tok",
        "last_checked": (now - timedelta(hours=2)).isoformat(),
        "last_hash": hash_content(text),
    }]
    tmp = _make_data_dir(tmp_path, subs)
    (tmp / "data" / "snapshots" / "dd.txt").write_text(text)
    monkeypatch.setattr("check_urls.SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json")
    monkeypatch.setattr("check_urls.SNAPSHOTS_DIR", tmp / "data" / "snapshots")
    monkeypatch.setenv("GMAIL_USER", "x@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pass")
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")

    with patch("check_urls.fetch_url", return_value=f"<html><body><p>{text}</p></body></html>"), \
         patch("check_urls.send_email") as mock_send:
        main()
        mock_send.assert_not_called()


def test_main_skips_and_preserves_last_checked_on_fetch_error(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    subs = [{
        "id": "ee", "url": "https://example.com", "email": "a@b.com",
        "frequency": "hourly", "created_at": now.isoformat(),
        "unsubscribe_token": "tok",
        "last_checked": None, "last_hash": None,
    }]
    tmp = _make_data_dir(tmp_path, subs)
    monkeypatch.setattr("check_urls.SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json")
    monkeypatch.setattr("check_urls.SNAPSHOTS_DIR", tmp / "data" / "snapshots")
    monkeypatch.setenv("GMAIL_USER", "x@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "pass")
    monkeypatch.setenv("GITHUB_PAGES_HOST", "owner.github.io/url-monitor")

    with patch("check_urls.fetch_url", side_effect=Exception("network error")), \
         patch("check_urls.send_email") as mock_send:
        main()  # must not raise
        mock_send.assert_not_called()

    updated = json.loads((tmp / "data" / "subscriptions.json").read_text())
    assert updated[0]["last_checked"] is None  # not updated on failure
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_check_urls.py -v -k "main"
```

Expected: `ImportError: cannot import name 'main'`

- [ ] **Step 3: Append fetch_url, snapshot helpers, and main() to scripts/check_urls.py**

```python
def fetch_url(url: str) -> str:
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        if resp.ok:
            return resp.text
    except Exception:
        pass
    return _fetch_with_playwright(url)


def _fetch_with_playwright(url: str) -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle")
        content = page.content()
        browser.close()
    return content


def load_subscriptions() -> list[dict]:
    return json.loads(SUBSCRIPTIONS_FILE.read_text())


def save_subscriptions(subs: list[dict]) -> None:
    SUBSCRIPTIONS_FILE.write_text(json.dumps(subs, indent=2))


def load_snapshot(sub_id: str) -> str | None:
    path = SNAPSHOTS_DIR / f"{sub_id}.txt"
    return path.read_text() if path.exists() else None


def save_snapshot(sub_id: str, text: str) -> None:
    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    (SNAPSHOTS_DIR / f"{sub_id}.txt").write_text(text)


def main() -> None:
    now = datetime.now(timezone.utc)
    subs = load_subscriptions()

    for sub in subs:
        if not is_due(sub, now):
            continue

        try:
            html = fetch_url(sub["url"])
        except Exception as e:
            print(f"Failed to fetch {sub['url']}: {e}")
            continue

        text = extract_text(html)
        current_hash = hash_content(text)

        if sub["last_hash"] is None:
            subject, body = build_welcome_email(sub)
            send_email(sub["email"], subject, body)
        elif current_hash != sub["last_hash"]:
            old_text = load_snapshot(sub["id"]) or ""
            diff_lines = generate_diff(old_text, text)
            subject, body = build_change_email(sub, diff_lines)
            send_email(sub["email"], subject, body)

        save_snapshot(sub["id"], text)
        sub["last_hash"] = current_hash
        sub["last_checked"] = now.isoformat()

    save_subscriptions(subs)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/check_urls.py tests/test_check_urls.py
git commit -m "feat: add URL fetching, snapshot I/O, and main check loop"
```

---

### Task 6: add_subscription.py

**Files:**
- Create: `scripts/add_subscription.py`
- Create: `tests/test_subscriptions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_subscriptions.py`:

```python
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def _make_data_dir(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "subscriptions.json").write_text("[]")
    return tmp_path


def test_add_subscription_appends_entry(monkeypatch, tmp_path):
    tmp = _make_data_dir(tmp_path)
    monkeypatch.setenv("SUB_URL", "https://example.com")
    monkeypatch.setenv("SUB_EMAIL", "user@test.com")
    monkeypatch.setenv("SUB_FREQUENCY", "daily")

    import add_subscription
    importlib.reload(add_subscription)

    with patch.object(add_subscription, "SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json"):
        add_subscription.main()

    subs = json.loads((tmp / "data" / "subscriptions.json").read_text())
    assert len(subs) == 1
    assert subs[0]["url"] == "https://example.com"
    assert subs[0]["email"] == "user@test.com"
    assert subs[0]["frequency"] == "daily"
    assert subs[0]["last_checked"] is None
    assert subs[0]["last_hash"] is None
    assert len(subs[0]["id"]) == 8
    assert len(subs[0]["unsubscribe_token"]) == 12


def test_add_subscription_generates_unique_tokens(monkeypatch, tmp_path):
    tmp = _make_data_dir(tmp_path)
    monkeypatch.setenv("SUB_URL", "https://example.com")
    monkeypatch.setenv("SUB_EMAIL", "user@test.com")
    monkeypatch.setenv("SUB_FREQUENCY", "hourly")

    import add_subscription
    importlib.reload(add_subscription)

    with patch.object(add_subscription, "SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json"):
        add_subscription.main()
        add_subscription.main()

    subs = json.loads((tmp / "data" / "subscriptions.json").read_text())
    assert len(subs) == 2
    assert subs[0]["unsubscribe_token"] != subs[1]["unsubscribe_token"]
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_subscriptions.py -v
```

Expected: `ModuleNotFoundError: No module named 'add_subscription'`

- [ ] **Step 3: Create scripts/add_subscription.py**

```python
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

SUBSCRIPTIONS_FILE = Path(__file__).parent.parent / "data" / "subscriptions.json"


def main() -> None:
    url = os.environ["SUB_URL"]
    email = os.environ["SUB_EMAIL"]
    frequency = os.environ["SUB_FREQUENCY"]

    subs = json.loads(SUBSCRIPTIONS_FILE.read_text())
    entry = {
        "id": secrets.token_hex(4),
        "url": url,
        "email": email,
        "frequency": frequency,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "unsubscribe_token": secrets.token_hex(6),
        "last_checked": None,
        "last_hash": None,
    }
    subs.append(entry)
    SUBSCRIPTIONS_FILE.write_text(json.dumps(subs, indent=2))
    print(f"Added subscription {entry['id']} for {email} -> {url}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_subscriptions.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/add_subscription.py tests/test_subscriptions.py
git commit -m "feat: add add_subscription script"
```

---

### Task 7: remove_subscription.py

**Files:**
- Create: `scripts/remove_subscription.py`
- Modify: `tests/test_subscriptions.py` (append tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_subscriptions.py`:

```python
def _make_data_dir_with_subs(tmp_path, subs):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "snapshots").mkdir(exist_ok=True)
    (data / "subscriptions.json").write_text(json.dumps(subs))
    return tmp_path


def _sample_subs():
    return [
        {"id": "aa", "url": "https://a.com", "email": "a@test.com", "frequency": "daily",
         "created_at": "2026-01-01T00:00:00+00:00", "unsubscribe_token": "token_aa",
         "last_checked": None, "last_hash": None},
        {"id": "bb", "url": "https://b.com", "email": "b@test.com", "frequency": "weekly",
         "created_at": "2026-01-01T00:00:00+00:00", "unsubscribe_token": "token_bb",
         "last_checked": None, "last_hash": None},
    ]


def test_remove_subscription_by_token(monkeypatch, tmp_path):
    tmp = _make_data_dir_with_subs(tmp_path, _sample_subs())
    monkeypatch.setenv("SUB_TOKEN", "token_aa")

    import remove_subscription
    importlib.reload(remove_subscription)

    with patch.object(remove_subscription, "SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json"), \
         patch.object(remove_subscription, "SNAPSHOTS_DIR", tmp / "data" / "snapshots"):
        remove_subscription.main()

    remaining = json.loads((tmp / "data" / "subscriptions.json").read_text())
    assert len(remaining) == 1
    assert remaining[0]["id"] == "bb"


def test_remove_subscription_invalid_token_is_noop(monkeypatch, tmp_path):
    subs = _sample_subs()[:1]
    tmp = _make_data_dir_with_subs(tmp_path, subs)
    monkeypatch.setenv("SUB_TOKEN", "nonexistent")

    import remove_subscription
    importlib.reload(remove_subscription)

    with patch.object(remove_subscription, "SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json"), \
         patch.object(remove_subscription, "SNAPSHOTS_DIR", tmp / "data" / "snapshots"):
        remove_subscription.main()  # must not raise

    remaining = json.loads((tmp / "data" / "subscriptions.json").read_text())
    assert len(remaining) == 1


def test_remove_subscription_deletes_snapshot(monkeypatch, tmp_path):
    subs = _sample_subs()[:1]
    tmp = _make_data_dir_with_subs(tmp_path, subs)
    snapshot = tmp / "data" / "snapshots" / "aa.txt"
    snapshot.write_text("some content")
    monkeypatch.setenv("SUB_TOKEN", "token_aa")

    import remove_subscription
    importlib.reload(remove_subscription)

    with patch.object(remove_subscription, "SUBSCRIPTIONS_FILE", tmp / "data" / "subscriptions.json"), \
         patch.object(remove_subscription, "SNAPSHOTS_DIR", tmp / "data" / "snapshots"):
        remove_subscription.main()

    assert not snapshot.exists()
```

- [ ] **Step 2: Run failing tests**

```bash
uv run pytest tests/test_subscriptions.py -v -k "remove"
```

Expected: `ModuleNotFoundError: No module named 'remove_subscription'`

- [ ] **Step 3: Create scripts/remove_subscription.py**

```python
import json
import os
from pathlib import Path

SUBSCRIPTIONS_FILE = Path(__file__).parent.parent / "data" / "subscriptions.json"
SNAPSHOTS_DIR = Path(__file__).parent.parent / "data" / "snapshots"


def main() -> None:
    token = os.environ["SUB_TOKEN"]
    subs = json.loads(SUBSCRIPTIONS_FILE.read_text())

    to_remove = [s for s in subs if s["unsubscribe_token"] == token]
    remaining = [s for s in subs if s["unsubscribe_token"] != token]

    if to_remove:
        SUBSCRIPTIONS_FILE.write_text(json.dumps(remaining, indent=2))
        for sub in to_remove:
            snapshot = SNAPSHOTS_DIR / f"{sub['id']}.txt"
            if snapshot.exists():
                snapshot.unlink()
        print(f"Removed {len(to_remove)} subscription(s) with token {token}")
    else:
        print(f"No subscription found with token {token}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/remove_subscription.py tests/test_subscriptions.py
git commit -m "feat: add remove_subscription script"
```

---

### Task 8: GitHub Actions workflows

**Files:**
- Create: `.github/workflows/add_subscription.yml`
- Create: `.github/workflows/check_urls.yml`
- Create: `.github/workflows/remove_subscription.yml`

No automated tests — verified manually in Task 11.

- [ ] **Step 1: Create .github/workflows/add_subscription.yml**

```yaml
name: Add Subscription

on:
  workflow_dispatch:
    inputs:
      url:
        description: URL to monitor
        required: true
        type: string
      email:
        description: Email to notify
        required: true
        type: string
      frequency:
        description: Check frequency
        required: true
        type: choice
        options:
          - hourly
          - daily
          - weekly

jobs:
  add:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"

      - run: uv sync

      - name: Add subscription
        run: uv run python scripts/add_subscription.py
        env:
          SUB_URL: ${{ inputs.url }}
          SUB_EMAIL: ${{ inputs.email }}
          SUB_FREQUENCY: ${{ inputs.frequency }}

      - name: Commit
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/subscriptions.json
          git diff --cached --quiet || git commit -m "add subscription"
          git push
```

- [ ] **Step 2: Create .github/workflows/check_urls.yml**

```yaml
name: Check URLs

on:
  schedule:
    - cron: '0 * * * *'
  workflow_dispatch: {}

jobs:
  check:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"

      - run: uv sync

      - name: Install Playwright browser
        run: uv run playwright install chromium --with-deps

      - name: Check URLs for changes
        run: uv run python scripts/check_urls.py
        env:
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          GITHUB_PAGES_HOST: ${{ vars.GITHUB_PAGES_HOST }}

      - name: Commit updated state
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/subscriptions.json data/snapshots/
          git diff --cached --quiet || git commit -m "update checks $(date -u +%Y-%m-%dT%H:%M:%SZ)"
          git push
```

- [ ] **Step 3: Create .github/workflows/remove_subscription.yml**

```yaml
name: Remove Subscription

on:
  workflow_dispatch:
    inputs:
      token:
        description: Unsubscribe token
        required: true
        type: string

jobs:
  remove:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"

      - run: uv sync

      - name: Remove subscription
        run: uv run python scripts/remove_subscription.py
        env:
          SUB_TOKEN: ${{ inputs.token }}

      - name: Commit
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/subscriptions.json data/snapshots/
          git diff --cached --quiet || git commit -m "remove subscription"
          git push
```

- [ ] **Step 4: Commit**

```bash
git add .github/
git commit -m "feat: add GitHub Actions workflows"
```

---

### Task 9: Frontend — index.html

**Files:**
- Create: `index.html`

Placeholders `YOUR_GITHUB_USERNAME`, `YOUR_REPO_NAME`, and `YOUR_FINE_GRAINED_PAT` are filled in during Task 11 Step 4. Commit with placeholder values for now.

- [ ] **Step 1: Create index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>URL Monitor</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      background: #f8f9fa;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }
    .container {
      background: white;
      border-radius: 10px;
      box-shadow: 0 2px 16px rgba(0,0,0,0.08);
      max-width: 720px;
      width: 100%;
      padding: 2.5rem;
      display: flex;
      gap: 3rem;
    }
    .info { flex: 1; }
    .info h1 { font-size: 1.4rem; color: #111; margin-bottom: 0.5rem; }
    .info p { color: #555; font-size: 0.9rem; line-height: 1.6; margin-bottom: 1rem; }
    .info ul { color: #555; font-size: 0.9rem; line-height: 1.9; padding-left: 1.2rem; }
    .form-panel { flex: 1; display: flex; flex-direction: column; gap: 0.75rem; }
    label { font-size: 0.8rem; font-weight: 600; color: #333; margin-bottom: 0.2rem; display: block; }
    input, select {
      width: 100%;
      padding: 0.6rem 0.75rem;
      border: 1px solid #ddd;
      border-radius: 6px;
      font-size: 0.9rem;
      color: #111;
      outline: none;
      transition: border-color 0.15s;
    }
    input:focus, select:focus { border-color: #2563eb; }
    button {
      background: #2563eb;
      color: white;
      border: none;
      border-radius: 6px;
      padding: 0.7rem;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      margin-top: 0.25rem;
      transition: background 0.15s;
    }
    button:hover { background: #1d4ed8; }
    button:disabled { background: #93c5fd; cursor: not-allowed; }
    #status { font-size: 0.85rem; margin-top: 0.5rem; min-height: 1.2em; }
    .success { color: #15803d; }
    .error { color: #b91c1c; }
    @media (max-width: 560px) {
      .container { flex-direction: column; gap: 1.5rem; }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="info">
      <h1>URL Monitor</h1>
      <p>Watch any webpage and get an email the moment something changes. No account needed — just paste a URL and go.</p>
      <ul>
        <li>Hourly, daily, or weekly checks</li>
        <li>Email showing exactly what changed</li>
        <li>Unsubscribe any time</li>
      </ul>
    </div>
    <div class="form-panel">
      <div>
        <label for="url">URL to watch</label>
        <input type="url" id="url" placeholder="https://example.com/page" required>
      </div>
      <div>
        <label for="email">Your email</label>
        <input type="email" id="email" placeholder="you@example.com" required>
      </div>
      <div>
        <label for="frequency">Check frequency</label>
        <select id="frequency">
          <option value="hourly">Hourly</option>
          <option value="daily" selected>Daily</option>
          <option value="weekly">Weekly</option>
        </select>
      </div>
      <button id="submit-btn" onclick="subscribe()">Start watching</button>
      <div id="status"></div>
    </div>
  </div>

  <script>
    const GITHUB_OWNER = "YOUR_GITHUB_USERNAME";
    const GITHUB_REPO  = "YOUR_REPO_NAME";
    const GITHUB_PAT   = "YOUR_FINE_GRAINED_PAT";

    async function subscribe() {
      const url       = document.getElementById("url").value.trim();
      const email     = document.getElementById("email").value.trim();
      const frequency = document.getElementById("frequency").value;
      const status    = document.getElementById("status");
      const btn       = document.getElementById("submit-btn");

      if (!url || !email) {
        status.textContent = "Please fill in all fields.";
        status.className = "error";
        return;
      }

      btn.disabled = true;
      status.textContent = "Subscribing…";
      status.className = "";

      try {
        const resp = await fetch(
          `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/add_subscription.yml/dispatches`,
          {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${GITHUB_PAT}`,
              "Accept": "application/vnd.github+json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ ref: "main", inputs: { url, email, frequency } }),
          }
        );

        if (resp.status === 204) {
          status.textContent = "You'll receive a confirmation email shortly.";
          status.className = "success";
          document.getElementById("url").value = "";
          document.getElementById("email").value = "";
        } else {
          status.textContent = `Error ${resp.status}. Please try again.`;
          status.className = "error";
        }
      } catch (err) {
        status.textContent = "Network error. Please try again.";
        status.className = "error";
      } finally {
        btn.disabled = false;
      }
    }
  </script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add index.html
git commit -m "feat: add subscribe form frontend"
```

---

### Task 10: Frontend — unsubscribe.html

**Files:**
- Create: `unsubscribe.html`

- [ ] **Step 1: Create unsubscribe.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Unsubscribe — URL Monitor</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      background: #f8f9fa;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }
    .card {
      background: white;
      border-radius: 10px;
      box-shadow: 0 2px 16px rgba(0,0,0,0.08);
      max-width: 420px;
      width: 100%;
      padding: 2.5rem;
      text-align: center;
    }
    h1 { font-size: 1.3rem; color: #111; margin-bottom: 0.75rem; }
    p { color: #555; font-size: 0.9rem; line-height: 1.6; }
    .success { color: #15803d; }
    .error { color: #b91c1c; }
  </style>
</head>
<body>
  <div class="card">
    <h1 id="heading">Unsubscribing…</h1>
    <p id="message">Please wait.</p>
  </div>

  <script>
    const GITHUB_OWNER = "YOUR_GITHUB_USERNAME";
    const GITHUB_REPO  = "YOUR_REPO_NAME";
    const GITHUB_PAT   = "YOUR_FINE_GRAINED_PAT";

    (async function () {
      const heading = document.getElementById("heading");
      const message = document.getElementById("message");
      const token   = new URLSearchParams(window.location.search).get("token");

      if (!token) {
        heading.textContent = "Invalid link";
        message.textContent = "No unsubscribe token found in this URL.";
        message.className = "error";
        return;
      }

      try {
        const resp = await fetch(
          `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/remove_subscription.yml/dispatches`,
          {
            method: "POST",
            headers: {
              "Authorization": `Bearer ${GITHUB_PAT}`,
              "Accept": "application/vnd.github+json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ ref: "main", inputs: { token } }),
          }
        );

        if (resp.status === 204) {
          heading.textContent = "Unsubscribed";
          message.textContent = "Your request was received. You'll be removed within a minute.";
          message.className = "success";
        } else {
          heading.textContent = "Something went wrong";
          message.textContent = `Error ${resp.status}. Please try again.`;
          message.className = "error";
        }
      } catch (err) {
        heading.textContent = "Network error";
        message.textContent = "Could not reach the server. Please try again.";
        message.className = "error";
      }
    })();
  </script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add unsubscribe.html
git commit -m "feat: add unsubscribe page"
```

---

### Task 11: GitHub repo setup and deployment

Manual steps — no code to write.

- [ ] **Step 1: Create the GitHub repo**

Go to github.com/new. Create a **private** repository named `url-monitor`. Do not initialize with a README (we already have commits locally).

- [ ] **Step 2: Push to GitHub**

```bash
git remote add origin git@github.com:YOUR_GITHUB_USERNAME/url-monitor.git
git push -u origin main
```

- [ ] **Step 3: Create a fine-grained PAT**

GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token:
- Name: `url-monitor-form`
- Expiration: 1 year (set a calendar reminder to renew)
- Repository access: Only `url-monitor`
- Permissions: **Actions → Read and write** (no other permissions needed)

Copy the token value.

- [ ] **Step 4: Fill in the placeholders in index.html and unsubscribe.html**

In both files, replace:
- `YOUR_GITHUB_USERNAME` → your actual GitHub username
- `YOUR_REPO_NAME` → `url-monitor`
- `YOUR_FINE_GRAINED_PAT` → the token from Step 3

```bash
git add index.html unsubscribe.html
git commit -m "chore: set GitHub owner, repo, and PAT"
git push
```

- [ ] **Step 5: Add GitHub Secrets**

Repo → Settings → Secrets and variables → Actions → Secrets → New repository secret:

| Name | Value |
|---|---|
| `GMAIL_USER` | Your Gmail address (e.g. `dexmcmillan@gmail.com`) |
| `GMAIL_APP_PASSWORD` | Generate at myaccount.google.com → Security → 2-Step Verification → App passwords → create one named "url-monitor" |

- [ ] **Step 6: Add GitHub Variable for the Pages hostname**

Repo → Settings → Secrets and variables → Actions → Variables → New repository variable:

| Name | Value |
|---|---|
| `GITHUB_PAGES_HOST` | `YOUR_GITHUB_USERNAME.github.io/url-monitor` |

- [ ] **Step 7: Enable GitHub Pages**

Repo → Settings → Pages → Source: Deploy from a branch → Branch: `main` → Folder: `/ (root)` → Save.

If the repo is private and you don't have GitHub Pro, either upgrade or move only `index.html` and `unsubscribe.html` to a separate public repo (the data and workflows stay private).

- [ ] **Step 8: Smoke test end-to-end**

a. Visit `https://YOUR_GITHUB_USERNAME.github.io/url-monitor/`
b. Fill in a URL (e.g. `https://example.com`), your email, frequency `Hourly`
c. Click "Start watching" — verify the success message appears
d. Go to repo → Actions → "Add Subscription" — verify it ran and `data/subscriptions.json` was committed with your new entry
e. Repo → Actions → "Check URLs" → Run workflow (manual trigger)
f. Verify you receive a "Now watching: example.com" email within a few minutes
g. Click the unsubscribe link in that email — verify the "Unsubscribed" page shows, and the "Remove Subscription" workflow runs and removes your entry from `subscriptions.json`
