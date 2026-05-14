"""
tps_calls.py — Hourly collector for TPS Calls for Service.

Fetches the live ArcGIS FeatureServer snapshot (last ~4 hours, ~70 records),
deduplicates by OBJECTID against the PostgreSQL database, and inserts new
records into the tps_calls table.

ArcGIS endpoint (public, no auth required):
  https://services.arcgis.com/S9th0jAJ7bqgIRjw/arcgis/rest/services/C4S_Public_NoGO/FeatureServer/0
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

FEATURE_URL = (
    "https://services.arcgis.com/S9th0jAJ7bqgIRjw/arcgis/rest/services"
    "/C4S_Public_NoGO/FeatureServer/0/query"
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; PolicePressScout/1.0; "
    "+https://github.com/globeandmail)"
)


def fetch_features() -> list[dict]:
    """Fetch all current calls for service from the TPS FeatureServer."""
    params = {
        "where": "1=1",
        "outFields": (
            "OBJECTID,OCCURRENCE_TIME,DIVISION,"
            "CALL_TYPE_CODE,CALL_TYPE,CROSS_STREETS,"
            "LATITUDE,LONGITUDE"
        ),
        "orderByFields": "OCCURRENCE_TIME DESC",
        "resultRecordCount": 2000,
        "f": "json",
    }
    try:
        resp = requests.get(
            FEATURE_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.Timeout:
        print("ERROR: Request timed out")
        return []
    except requests.RequestException as e:
        print(f"ERROR: Failed to fetch data: {e}")
        return []
    try:
        data = resp.json()
    except Exception as e:
        print(f"ERROR: Invalid JSON response: {e}")
        return []
    return [feat["attributes"] for feat in data.get("features", [])]


def parse_feature(attrs: dict) -> dict:
    """Convert raw ArcGIS attributes to a clean record."""
    ts = attrs.get("OCCURRENCE_TIME")
    if ts is not None:
        occurred_at = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
    else:
        occurred_at = None

    return {
        "objectid": attrs.get("OBJECTID"),
        "occurred_at": occurred_at,
        "division": attrs.get("DIVISION"),
        "call_type_code": attrs.get("CALL_TYPE_CODE"),
        "call_type": attrs.get("CALL_TYPE"),
        "cross_streets": attrs.get("CROSS_STREETS"),
        "latitude": attrs.get("LATITUDE"),
        "longitude": attrs.get("LONGITUDE"),
        "collected_at": datetime.now(tz=timezone.utc).isoformat(),
    }


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


def main() -> None:
    conn = db.get_connection()
    db.init_schema(conn)

    seen_objectids = db.get_recent_tps_objectids(conn)
    print(f"Known OBJECTIDs (last 48h): {len(seen_objectids)}")

    raw_features = fetch_features()
    print(f"Fetched: {len(raw_features)} features from API")

    new_records = [
        parse_feature(attrs)
        for attrs in raw_features
        if attrs.get("OBJECTID") is not None and attrs["OBJECTID"] not in seen_objectids
    ]

    inserted = db.insert_tps_calls(conn, new_records)
    if inserted:
        print(f"Inserted: {inserted} new records into database")
    else:
        print("No new records.")


if __name__ == "__main__":
    main()
