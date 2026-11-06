"""Tiny key-value cache in SQLite, so repeat research doesn't re-spend API credits."""
import json
from datetime import datetime, timedelta, timezone

from . import db


def get(key: str, max_age_hours: float):
    with db.session() as s:
        row = s.execute("SELECT value, fetched_at FROM cache WHERE key=?", (key,)).fetchone()
    if not row:
        return None
    fetched = datetime.fromisoformat(row["fetched_at"]).replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - fetched > timedelta(hours=max_age_hours):
        return None
    return json.loads(row["value"])


def put(key: str, value) -> None:
    with db.session() as s:
        s.execute(
            "INSERT INTO cache(key, value, fetched_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, fetched_at=excluded.fetched_at",
            (key, json.dumps(value), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")),
        )
