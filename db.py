"""
Database access layer for Police Scout.

All reads and writes go through this module. The connection string is read
from the DATABASE_URL environment variable:
    postgresql://user:password@host:5432/dbname
"""

import os
from datetime import date, datetime, timedelta, timezone

import psycopg


def get_connection() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Set it to your PostgreSQL connection string, e.g.:\n"
            "  export DATABASE_URL=postgresql://user:pass@host:5432/dbname"
        )
    return psycopg.connect(url)


def init_schema(conn: psycopg.Connection) -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS press_releases (
                id               SERIAL PRIMARY KEY,
                item_hash        TEXT UNIQUE NOT NULL,
                title            TEXT NOT NULL,
                url              TEXT,
                date             DATE,
                service_name     TEXT NOT NULL,
                content          TEXT,
                first_scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tps_calls (
                id             SERIAL PRIMARY KEY,
                objectid       INTEGER UNIQUE NOT NULL,
                call_type      TEXT,
                call_type_code TEXT,
                division       TEXT,
                cross_streets  TEXT,
                latitude       DOUBLE PRECISION,
                longitude      DOUBLE PRECISION,
                occurred_at    TIMESTAMPTZ,
                collected_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    conn.commit()


# ---------------------------------------------------------------------------
# Press releases
# ---------------------------------------------------------------------------

def get_known_hashes(conn: psycopg.Connection, hashes: list[str]) -> set[str]:
    """Return the subset of hashes already stored in press_releases."""
    if not hashes:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT item_hash FROM press_releases WHERE item_hash = ANY(%s)",
            (hashes,),
        )
        return {row[0] for row in cur.fetchall()}


def insert_press_releases(conn: psycopg.Connection, items: list[dict]) -> int:
    """
    Insert new press releases, skipping any that already exist (by item_hash).
    Returns the number of rows actually inserted.
    """
    if not items:
        return 0
    inserted = 0
    with conn.cursor() as cur:
        for item in items:
            cur.execute(
                """
                INSERT INTO press_releases
                    (item_hash, title, url, date, service_name, content)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (item_hash) DO NOTHING
                """,
                (
                    item["item_hash"],
                    item["title"],
                    item.get("url"),
                    item.get("date"),
                    item["service_name"],
                    item.get("content"),
                ),
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted


def load_press_releases(conn: psycopg.Connection, cutoff: date) -> list[dict]:
    """
    Return all press releases on or after cutoff, newest first.
    Items with no date fall back to first_scraped_at for filtering and display.
    """
    cutoff_ts = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT title, url,
                   date::text,
                   service_name, content,
                   first_scraped_at::date::text
            FROM press_releases
            WHERE date >= %s
               OR (date IS NULL AND first_scraped_at >= %s)
            ORDER BY COALESCE(date, first_scraped_at::date) DESC NULLS LAST,
                     first_scraped_at DESC
            """,
            (cutoff, cutoff_ts),
        )
        rows = cur.fetchall()

    items = []
    for title, url, date_str, service_name, content, scraped_date in rows:
        display_date = date_str or scraped_date
        items.append({
            "type": "press_release",
            "title": title,
            "url": url,
            "date": display_date,
            "source": service_name,
            "content": content,
            "_sort_key": display_date or "",
        })
    return items


# ---------------------------------------------------------------------------
# TPS calls
# ---------------------------------------------------------------------------

def get_recent_tps_objectids(conn: psycopg.Connection) -> set[int]:
    """Return OBJECTIDs collected in the last 48 hours (mirrors the old seen-file logic)."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=48)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT objectid FROM tps_calls WHERE collected_at >= %s",
            (cutoff,),
        )
        return {row[0] for row in cur.fetchall()}


def insert_tps_calls(conn: psycopg.Connection, records: list[dict]) -> int:
    """Insert new TPS call records, skipping duplicates by objectid."""
    if not records:
        return 0
    inserted = 0
    with conn.cursor() as cur:
        for rec in records:
            cur.execute(
                """
                INSERT INTO tps_calls
                    (objectid, call_type, call_type_code, division,
                     cross_streets, latitude, longitude, occurred_at, collected_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (objectid) DO NOTHING
                """,
                (
                    rec["objectid"],
                    rec.get("call_type"),
                    rec.get("call_type_code"),
                    rec.get("division"),
                    rec.get("cross_streets"),
                    rec.get("latitude"),
                    rec.get("longitude"),
                    rec.get("occurred_at"),
                    rec.get("collected_at"),
                ),
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted


def load_tps_calls(conn: psycopg.Connection, cutoff: date) -> list[dict]:
    """Return all TPS calls on or after cutoff, newest first."""
    cutoff_ts = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT call_type, division, cross_streets,
                   occurred_at AT TIME ZONE 'UTC' AS occurred_at_utc,
                   occurred_at::date::text
            FROM tps_calls
            WHERE occurred_at >= %s
            ORDER BY occurred_at DESC
            """,
            (cutoff_ts,),
        )
        rows = cur.fetchall()

    items = []
    for call_type, division, cross_streets, occurred_at_dt, iso_date in rows:
        occurred_at_iso = occurred_at_dt.isoformat() if occurred_at_dt else None
        items.append({
            "type": "tps_call",
            "title": call_type or "",
            "call_type": call_type or "",
            "url": None,
            "date": iso_date,
            "occurred_at": occurred_at_iso,
            "source": "Toronto Police Service",
            "division": division or "",
            "cross_streets": cross_streets or "",
            "_sort_key": occurred_at_iso or iso_date or "",
        })
    return items
