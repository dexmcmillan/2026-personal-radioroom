# GitHub Actions Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the PostgreSQL/EC2 storage layer with JSON files committed to git, making the project run entirely on GitHub Actions.

**Architecture:** `tps_calls.py` gains standalone file I/O helpers (`load_seen`, `save_seen`, `append_records`). `scan.py` gains `prune_state` and a refactored `build_feed` that reads JSON files directly. Both scripts' `main()` functions drop their `db` imports and use JSON files instead. `psycopg` is removed from dependencies.

**Tech Stack:** Python 3.12, stdlib `json`/`pathlib`/`datetime`, uv, pytest

---

## File Map

| File | Change |
|---|---|
| `tps_calls.py` | Add `load_seen`, `save_seen`, `append_records`; update `main()`; remove `import db` |
| `scan.py` | Add `prune_state`; refactor `build_feed` signature + body; add path constants; update `main()`; remove `import db` |
| `pyproject.toml` | Remove `psycopg[binary]>=3.2` |
| `db.py` | Left unchanged (dead code, not imported by workflows) |

---

## Task 1: Confirm test baseline

**Files:**
- Run: `tests/test_tps_calls.py`, `tests/test_scan.py`

- [ ] **Step 1: Run the full test suite**

```bash
cd /path/to/2026-personal-policescout
uv run pytest tests/ -v 2>&1 | head -80
```

Expected: Multiple failures — `load_seen`, `save_seen`, `append_records` not found in `tps_calls`; `prune_state` not found in `scan`; `build_feed` signature mismatch. This confirms the tests are driving the implementation.

- [ ] **Step 2: Commit (nothing to commit yet — baseline only)**

No code changes in this task.

---

## Task 2: Add file I/O helpers to tps_calls.py

The tests in `tests/test_tps_calls.py` import `load_seen`, `save_seen`, and `append_records` directly from `tps_calls`. These replace the `db.py` calls.

**Files:**
- Modify: `tps_calls.py`
- Test: `tests/test_tps_calls.py`

- [ ] **Step 1: Run the tps_calls tests to see current failures**

```bash
uv run pytest tests/test_tps_calls.py -v
```

Expected: 4–5 failures — `ImportError: cannot import name 'load_seen'` etc.

- [ ] **Step 2: Add imports and file I/O helpers to tps_calls.py**

At the top of `tps_calls.py`, replace:
```python
from datetime import datetime, timezone

import requests

import db
```

with:
```python
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
```

Then add these three functions after `parse_feature` (before `main`):

```python
def load_seen(path: Path) -> set[int]:
    """Load seen objectids from a JSON file. Returns empty set if missing or corrupt."""
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return set()


def save_seen(seen: set[int], path: Path) -> None:
    """Save seen objectids to a JSON file as a sorted array."""
    path.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def append_records(records: list[dict], path: Path) -> None:
    """Append records to an NDJSON file (one JSON object per line)."""
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
```

- [ ] **Step 3: Run tps_calls tests — expect pass**

```bash
uv run pytest tests/test_tps_calls.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tps_calls.py
git commit -m "feat: add load_seen, save_seen, append_records to tps_calls"
```

---

## Task 3: Update tps_calls.py main() to use JSON files

Replace the `db.*` calls in `main()` with the new file helpers. Add module-level path constants.

**Files:**
- Modify: `tps_calls.py`

- [ ] **Step 1: Add module-level path constants after the FEATURE_URL constant**

```python
_DATA_DIR = Path(__file__).parent / "data"
_TPS_NDJSON = _DATA_DIR / "tps_calls.ndjson"
_SEEN_FILE = _DATA_DIR / "tps_calls_seen.json"
```

- [ ] **Step 2: Replace main() body**

Replace the existing `main()` function with:

```python
def main() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    seen_objectids = load_seen(_SEEN_FILE)
    print(f"Known OBJECTIDs: {len(seen_objectids)}")

    raw_features = fetch_features()
    print(f"Fetched: {len(raw_features)} features from API")

    new_records = [
        parse_feature(attrs)
        for attrs in raw_features
        if attrs.get("OBJECTID") is not None and attrs["OBJECTID"] not in seen_objectids
    ]

    if new_records:
        append_records(new_records, _TPS_NDJSON)
        seen_objectids.update(rec["objectid"] for rec in new_records)
        save_seen(seen_objectids, _SEEN_FILE)
        print(f"Inserted: {len(new_records)} new records")
    else:
        print("No new records.")
```

- [ ] **Step 3: Run tests to confirm nothing broke**

```bash
uv run pytest tests/test_tps_calls.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tps_calls.py
git commit -m "feat: update tps_calls main() to use JSON file storage"
```

---

## Task 4: Add prune_state to scan.py

`test_scan.py` tests `scan.prune_state(state, today)` which prunes a `{hash: ISO-timestamp}` dict, removing entries older than 30 days.

**Files:**
- Modify: `scan.py`
- Test: `tests/test_scan.py` (the `test_prune_state_*` tests)

- [ ] **Step 1: Run just the prune_state tests to see current failure**

```bash
uv run pytest tests/test_scan.py -k "prune_state" -v
```

Expected: FAIL — `AttributeError: module 'scan' has no attribute 'prune_state'`

- [ ] **Step 2: Add prune_state to scan.py**

Add this function immediately after the `item_hash` function (around line 40):

```python
def prune_state(state: dict, today: date) -> dict:
    """Remove entries older than 30 days from a {key: ISO-timestamp} dict."""
    cutoff = (today - timedelta(days=30)).isoformat()
    return {k: v for k, v in state.items() if v[:10] >= cutoff}
```

- [ ] **Step 3: Run prune_state tests — expect pass**

```bash
uv run pytest tests/test_scan.py -k "prune_state" -v
```

Expected: All 4 `test_prune_state_*` tests PASS.

- [ ] **Step 4: Commit**

```bash
git add scan.py
git commit -m "feat: add prune_state helper to scan"
```

---

## Task 5: Refactor scan.py build_feed to read from JSON files

The tests call `scan.build_feed(archive_dir=..., tps_ndjson=..., output_dir=..., days=7)`. The current signature is `build_feed(conn, output_dir, days)`. Replace the entire function.

**Files:**
- Modify: `scan.py`
- Test: `tests/test_scan.py` (the `test_build_feed_*` tests)

- [ ] **Step 1: Run the build_feed tests to see current failures**

```bash
uv run pytest tests/test_scan.py -k "build_feed" -v
```

Expected: Multiple failures — wrong number of arguments, missing `search_text` field, etc.

- [ ] **Step 2: Replace build_feed in scan.py**

Find the existing `build_feed` function (starts around line 672) and replace it entirely with:

```python
def build_feed(
    archive_dir: Path,
    tps_ndjson: Path,
    output_dir: Path,
    days: int = 365,
) -> None:
    """
    Build the card feed from JSON archive files and TPS NDJSON.
    Writes docs/data.json and docs/index.html.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    print(f"  [build_feed] Cutoff: {cutoff} ({days} days)")

    # Load press releases from per-service archive files
    press_items = []
    if archive_dir.exists():
        for f in sorted(archive_dir.glob("*.json")):
            try:
                releases = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for item in releases:
                item_date = item.get("date")
                fallback_date = item.get("first_scraped_at") or ""
                if item_date is not None and item_date < cutoff:
                    continue
                sort_key = item_date or fallback_date
                press_items.append({
                    "type": "press_release",
                    "title": item.get("title", ""),
                    "url": item.get("url"),
                    "date": item_date,
                    "source": item.get("service_name", ""),
                    "content": item.get("content"),
                    "search_text": " ".join(
                        s.lower()
                        for s in [
                            item.get("title") or "",
                            item.get("service_name") or "",
                            item.get("content") or "",
                        ]
                        if s
                    ),
                    "_sort_key": sort_key,
                })
    print(f"  [build_feed] Press releases in window: {len(press_items)}")

    # Load TPS calls from NDJSON
    tps_items = []
    if tps_ndjson.exists():
        for line in tps_ndjson.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            occurred_at = rec.get("occurred_at")
            if not occurred_at:
                continue
            rec_date = occurred_at[:10]
            if rec_date < cutoff:
                continue
            tps_items.append({
                "type": "tps_call",
                "title": rec.get("call_type") or "",
                "call_type": rec.get("call_type") or "",
                "url": None,
                "date": rec_date,
                "occurred_at": occurred_at,
                "source": "Toronto Police Service",
                "division": rec.get("division") or "",
                "cross_streets": rec.get("cross_streets") or "",
                "search_text": " ".join(
                    s.lower()
                    for s in [
                        rec.get("call_type") or "",
                        rec.get("division") or "",
                        rec.get("cross_streets") or "",
                    ]
                    if s
                ),
                "_sort_key": occurred_at,
            })
    print(f"  [build_feed] TPS calls in window: {len(tps_items)}")

    all_items = sorted(press_items + tps_items, key=lambda x: x["_sort_key"], reverse=True)
    for item in all_items:
        item.pop("_sort_key", None)

    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / "data.json"
    data_path.write_text(json.dumps(all_items, ensure_ascii=False), encoding="utf-8")
    print(f"  [build_feed] Wrote {data_path} ({len(all_items)} items)")

    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/Toronto"))
    et_label = now_et.strftime("%Z")
    generated_at = now_et.strftime(f"%B %d, %Y at %H:%M {et_label}")
    sources = sorted({item["source"] for item in press_items if item.get("source")})
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    try:
        template = env.get_template("feed.html")
    except Exception as e:
        print(f"  [build_feed] WARNING: could not load feed.html template: {e}")
        return
    html = template.render(generated_at=generated_at, sources=sources)
    index_path = output_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    print(f"  [build_feed] Wrote {index_path}")
```

- [ ] **Step 3: Run all build_feed tests — expect pass**

```bash
uv run pytest tests/test_scan.py -k "build_feed" -v
```

Expected: All 10 `test_build_feed_*` tests PASS.

- [ ] **Step 4: Run full scan test suite to confirm no regressions**

```bash
uv run pytest tests/test_scan.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scan.py
git commit -m "feat: refactor build_feed to read from JSON archive and NDJSON files"
```

---

## Task 6: Update scan.py main() to use JSON files

Replace the `db.*` calls in `main()` with direct JSON file I/O. Add module-level path constants. Remove `import db`.

**Files:**
- Modify: `scan.py`

- [ ] **Step 1: Remove `import db` and add path constants**

Find the `import db` line (near the top of scan.py after `from jinja2 import ...`) and remove it.

Add these constants immediately after the existing path constants block (after `SOURCES_FILE`):

```python
DATA_DIR = BASE_DIR / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
TPS_NDJSON = DATA_DIR / "tps_calls.ndjson"
SEEN_ITEMS_FILE = DATA_DIR / "seen_items.json"
```

- [ ] **Step 2: Add private helpers for JSON storage**

Add these three helpers before `main()`:

```python
def _load_seen_items() -> dict:
    """Load {hash: ISO-timestamp} from seen_items.json. Returns {} if missing."""
    try:
        return json.loads(SEEN_ITEMS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_seen_items(seen: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_ITEMS_FILE.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")


def _service_slug(service_name: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "-", service_name.lower()).strip("-")


def _append_to_archive(service_name: str, items: list[dict]) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE_DIR / f"{_service_slug(service_name)}.json"
    existing: list = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []
    existing.extend(items)
    path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 3: Replace main()**

Replace the existing `main()` function with:

```python
def main():
    from collections import defaultdict

    today_utc = datetime.now(timezone.utc).date()
    print(f"Police Scout — {today_utc}")

    seen = _load_seen_items()
    known = set(seen.keys())

    sources = load_sources()
    print(f"Loaded {len(sources)} sources")

    # Scrape all sources
    all_scraped: list[dict] = []
    failed_services: list[str] = []

    for source in sources:
        print(f"  Scraping {source['name']}...", end=" ")
        items, error = scrape_site(
            source["name"],
            source["url"],
            link_selector=source["link_selector"],
            date_selector=source["date_selector"],
        )
        if error:
            print(f"FAILED: {error}")
            failed_services.append(source["name"])
            continue
        print(f"{len(items)} links found")
        all_scraped.extend(items)

    # Dedup against seen hashes
    new_items = [i for i in all_scraped if item_hash(i["title"], i["url"] or "") not in known]
    print(f"\nScraped: {len(all_scraped)}, new: {len(new_items)}, failed services: {len(failed_services)}")

    # Fetch content and expand CK daily releases into per-incident items
    to_insert: list[dict] = []
    for item in new_items:
        url = item.get("url")
        content = item.get("content") or (fetch_release_content(url) if url else None)
        if content and item["service_name"] == "Hamilton Police Service":
            content = _clean_hamilton_content(content, item["title"])

        base = {
            "item_hash": item_hash(item["title"], url or ""),
            "title": item["title"],
            "url": url,
            "date": normalize_date(item.get("date")),
            "service_name": item["service_name"],
            "content": content,
            "first_scraped_at": today_utc.isoformat(),
        }

        if item["service_name"] == "Chatham-Kent Police Service" and content:
            for incident in split_ck_daily_release({**base, "content": content}):
                to_insert.append({
                    "item_hash": item_hash(incident["title"], incident.get("url") or ""),
                    "title": incident["title"],
                    "url": incident.get("url"),
                    "date": incident.get("date"),
                    "service_name": incident["service_name"],
                    "content": incident.get("content"),
                    "first_scraped_at": today_utc.isoformat(),
                })
        else:
            to_insert.append(base)

    # Write to archive files and update seen dict
    by_service: defaultdict[str, list] = defaultdict(list)
    for item in to_insert:
        by_service[item["service_name"]].append(item)
    for service_name, service_items in by_service.items():
        _append_to_archive(service_name, service_items)
    for item in to_insert:
        seen[item["item_hash"]] = datetime.now(timezone.utc).isoformat()
    seen = prune_state(seen, today_utc)
    _save_seen_items(seen)
    print(f"Inserted {len(to_insert)} new items")

    # Build the static feed
    build_feed(archive_dir=ARCHIVE_DIR, tps_ndjson=TPS_NDJSON, output_dir=DOCS_DIR, days=365)
    print("Done.")
```

- [ ] **Step 4: Run full test suite — expect all pass**

```bash
uv run pytest tests/ -v
```

Expected: All tests PASS. If any fail, the error will point to a scan.py import issue or missing function — fix before continuing.

- [ ] **Step 5: Commit**

```bash
git add scan.py
git commit -m "feat: update scan main() to use JSON file storage, remove db dependency"
```

---

## Task 7: Remove psycopg from pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Remove the psycopg dependency**

In `pyproject.toml`, remove this line from the `dependencies` list:
```
"psycopg[binary]>=3.2",
```

The `dependencies` block should now read:
```toml
dependencies = [
    "beautifulsoup4>=4.14.3",
    "jinja2>=3.1.6",
    "requests>=2.32.5",
]
```

- [ ] **Step 2: Update the lockfile**

```bash
uv sync
```

Expected: `psycopg` and its binary extensions are removed from the environment. No errors.

- [ ] **Step 3: Run tests to confirm nothing broke**

```bash
uv run pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: remove psycopg dependency"
```

---

## Task 8: Smoke test the full scripts end-to-end

Verify both scripts run without errors using `--help` or a dry invocation.

**Files:** None modified.

- [ ] **Step 1: Verify scan.py imports cleanly**

```bash
uv run python -c "import scan; print('scan imports OK')"
```

Expected: `scan imports OK` with no `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 2: Verify tps_calls.py imports cleanly**

```bash
uv run python -c "import tps_calls; print('tps_calls imports OK')"
```

Expected: `tps_calls imports OK`.

- [ ] **Step 3: Run the full test suite one final time**

```bash
uv run pytest tests/ -v
```

Expected: All tests PASS. No warnings about missing modules.

- [ ] **Step 4: Push to GitHub**

```bash
git push
```

Confirm in GitHub Actions that both workflows (`Police Scout` and `TPS Calls for Service`) can be triggered manually via `workflow_dispatch` and complete without errors.

- [ ] **Step 5: Enable GitHub Pages**

In the repository Settings → Pages:
- Source: Deploy from a branch
- Branch: `main`, folder: `/docs`

The site will be live at `https://<your-username>.github.io/2026-personal-policescout/`.
