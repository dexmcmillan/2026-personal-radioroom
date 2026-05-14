# Design: Migrate Police Scout from EC2/PostgreSQL to GitHub Actions + JSON Files

**Date:** 2026-05-14  
**Status:** Approved

## Goal

Remove the EC2 instance and PostgreSQL database. Run the project entirely on GitHub Actions with data persisted as JSON files committed to the repository. GitHub Pages serves the static frontend.

## Architecture

Two scheduled GitHub Actions workflows run the project:

| Workflow | Schedule | Script | Commits |
|---|---|---|---|
| `scan.yml` | Weekdays at 7 AM ET (noon UTC) | `scan.py` | `docs/`, `data/seen_items.json`, `data/archive/` |
| `tps_calls.yml` | Hourly, every day | `tps_calls.py` | `data/tps_calls.ndjson`, `data/tps_calls_seen.json` |

Both workflows already exist and reference the correct file paths — no changes needed.

**Frontend hosting:** GitHub Pages serves from `docs/` on the main branch. Must be enabled once in repo Settings → Pages.

## Data Files

Four files replace the two PostgreSQL tables:

| File | Replaces | Format |
|---|---|---|
| `data/seen_items.json` | `press_releases.item_hash` | `{"<hash>": "<YYYY-MM-DD>", ...}` |
| `data/archive/<service-slug>.json` | `press_releases` table | JSON array of release objects |
| `data/tps_calls.ndjson` | `tps_calls` table | Append-only, one JSON object per line |
| `data/tps_calls_seen.json` | 48h dedup window query | `{"<objectid>": "<ISO datetime>", ...}` |

**Service slug:** `service_name.lower().replace(" ", "-")` with non-alphanumeric chars replaced by `-`.

**Pruning:** `tps_calls_seen.json` is pruned to entries within the last 48 hours on every `insert_tps_calls()` call. `seen_items.json` is never pruned (grows slowly; ~785 entries currently).

**Archive object schema** (same fields as the PostgreSQL row):
```json
{
  "item_hash": "string",
  "title": "string",
  "url": "string or null",
  "date": "YYYY-MM-DD or null",
  "service_name": "string",
  "content": "string or null",
  "first_scraped_at": "YYYY-MM-DD"
}
```

## Code Changes

### `db.py` — Full rewrite

Replace psycopg with stdlib `json` and `pathlib`. Module-level `DATA_DIR = Path(__file__).parent / "data"` replaces the connection object. The `conn` parameter is removed from all public functions.

**Public interface:**

```python
def init_schema() -> None
    # Creates data/ and data/archive/ if missing. Safe to call on every run.

def get_known_hashes(hashes: list[str]) -> set[str]
    # Reads seen_items.json, returns subset of hashes already present.

def insert_press_releases(items: list[dict]) -> int
    # Appends new items to per-service archive files.
    # Updates seen_items.json with new hashes.
    # Returns count of inserted items.

def load_press_releases(cutoff: date) -> list[dict]
    # Reads all data/archive/*.json files.
    # Includes items where date >= cutoff, OR date is None AND first_scraped_at >= cutoff.
    # Returns list of feed dicts (same shape as before, with _sort_key).

def get_recent_tps_objectids() -> set[int]
    # Reads tps_calls_seen.json, returns objectids with collected_at within 48h.

def insert_tps_calls(records: list[dict]) -> int
    # Appends new records to tps_calls.ndjson.
    # Prunes tps_calls_seen.json to 48h window, adds new objectids.
    # Returns count of inserted records.

def load_tps_calls(cutoff: date) -> list[dict]
    # Reads tps_calls.ndjson line by line.
    # Returns calls where occurred_at >= cutoff, newest first.
    # Returns list of feed dicts (same shape as before, with _sort_key).
```

`get_connection()` and `init_schema(conn)` are removed entirely (replaced by parameterless `init_schema()`).

### `scan.py` — Minor updates

- Remove `conn = db.get_connection()`
- Change `db.init_schema(conn)` → `db.init_schema()`
- Drop `conn` argument from all `db.*` calls
- Update `build_feed(conn, output_dir, days)` → `build_feed(output_dir, days)`
- Inside `build_feed`: drop `conn` from `db.load_press_releases()` and `db.load_tps_calls()`

### `tps_calls.py` — Minor updates

- Remove `conn = db.get_connection()`
- Change `db.init_schema(conn)` → `db.init_schema()`
- Drop `conn` from `db.get_recent_tps_objectids()` and `db.insert_tps_calls()`

### `pyproject.toml`

Remove `psycopg[binary]>=3.2`. No new dependencies needed (stdlib only).

### Workflows

No changes required. Both workflows already commit the correct files.

### `deploy/`

Left in place — obsolete but harmless.

## Out of Scope

- `backfill.py`, `migrate.py`, `fetch_missing_dates.py` — PostgreSQL migration utilities, left in place
- Tests in `tests/` — may need minor updates to remove conn mocking; not in scope for this migration
