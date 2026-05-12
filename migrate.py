"""
migrate.py — One-time migration of flat JSON/NDJSON data files into PostgreSQL.

Run this on EC2 after copying your local data/ directory over:

    scp -i ~/.ssh/policescout.pem -r data/archive ubuntu@<ip>:/opt/policescout/data/
    scp -i ~/.ssh/policescout.pem data/tps_calls.ndjson ubuntu@<ip>:/opt/policescout/data/

Then on EC2:
    cd /opt/policescout
    . .env
    uv run python migrate.py
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import db

BASE_DIR = Path(__file__).parent
ARCHIVE_DIR = BASE_DIR / "data" / "archive"
TPS_NDJSON = BASE_DIR / "data" / "tps_calls.ndjson"


def item_hash(title: str, url: str) -> str:
    raw = title.strip() + "|" + url.strip()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def migrate_press_releases(conn) -> None:
    archive_files = sorted(ARCHIVE_DIR.glob("*.json"))
    if not archive_files:
        print(f"  No archive files found in {ARCHIVE_DIR}")
        return

    all_items = []
    for path in archive_files:
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  WARNING: skipping {path.name}: {e}")
            continue
        for item in items:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip() or None
            if not title:
                continue
            all_items.append({
                "item_hash": item_hash(title, url or ""),
                "title": title,
                "url": url,
                "date": item.get("date"),
                "service_name": item.get("service_name", "Unknown").strip(),
                "content": item.get("content") or None,
            })

    print(f"  Inserting {len(all_items)} press releases...")
    inserted = db.insert_press_releases(conn, all_items)
    skipped = len(all_items) - inserted
    print(f"  Done: {inserted} inserted, {skipped} skipped (already existed)")


def migrate_tps_calls(conn) -> None:
    if not TPS_NDJSON.exists():
        print(f"  TPS NDJSON not found at {TPS_NDJSON}, skipping")
        return

    records = []
    with TPS_NDJSON.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception as e:
                print(f"  WARNING: skipping line {lineno}: {e}")
                continue
            if rec.get("objectid") is None:
                continue
            records.append({
                "objectid":      rec["objectid"],
                "call_type":     rec.get("call_type"),
                "call_type_code":rec.get("call_type_code"),
                "division":      rec.get("division"),
                "cross_streets": rec.get("cross_streets"),
                "latitude":      rec.get("latitude"),
                "longitude":     rec.get("longitude"),
                "occurred_at":   parse_dt(rec.get("occurred_at")),
                "collected_at":  parse_dt(rec.get("collected_at")),
            })

    print(f"  Inserting {len(records)} TPS calls...")
    inserted = db.insert_tps_calls(conn, records)
    skipped = len(records) - inserted
    print(f"  Done: {inserted} inserted, {skipped} skipped (already existed)")


def main() -> None:
    print("Connecting to database...")
    conn = db.get_connection()
    db.init_schema(conn)
    print("Schema ready.\n")

    print("==> Press releases")
    migrate_press_releases(conn)

    print("\n==> TPS calls")
    migrate_tps_calls(conn)

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
