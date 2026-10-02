"""First-party, anonymous pageview statistics stored outside application assets."""

import hashlib
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from visit_geolocation import CountryLookup

ROUTES = ("/", "/spectral", "/hyperspectral", "/extra-tools", "/tutorial", "/contributors")
DATA_DIR = Path(os.environ.get("RAMANCLOUD_ANALYTICS_DIR", Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ramancloud" / "analytics"))
HISTORY_PATH = Path(__file__).with_name("historical_visits.json")
router = APIRouter(prefix="/api/visits", tags=["Visit statistics"])
logger = logging.getLogger(__name__)


class Pageview(BaseModel):
    event_id: UUID
    session_id: UUID
    path: Literal["/", "/spectral", "/hyperspectral", "/extra-tools", "/tutorial", "/contributors"]


class VisitStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "visits.sqlite3"

    def connect(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pageviews (
                event_id TEXT PRIMARY KEY,
                session_hash TEXT NOT NULL,
                path TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                day TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS pageviews_day ON pageviews(day);
            CREATE INDEX IF NOT EXISTS pageviews_session_time ON pageviews(session_hash, occurred_at);
        """)
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            if "country" not in {row["name"] for row in connection.execute("PRAGMA table_info(pageviews)")}:
                connection.execute("ALTER TABLE pageviews ADD COLUMN country TEXT NOT NULL DEFAULT 'ZZ'")
            connection.execute("INSERT OR IGNORE INTO metadata VALUES ('started_at', ?)", (datetime.now(timezone.utc).isoformat(),))
            if not connection.execute("SELECT 1 FROM metadata WHERE key='historical_baseline'").fetchone():
                baseline = json.loads(HISTORY_PATH.read_text()) if os.environ.get("RAMANCLOUD_ANALYTICS_IMPORT_V1", "1") != "0" else {"pageviews": 0, "since": None, "countries": {}}
                connection.execute("INSERT INTO metadata VALUES ('historical_baseline', ?)", (json.dumps(baseline),))
            baseline = json.loads(connection.execute("SELECT value FROM metadata WHERE key='historical_baseline'").fetchone()[0])
            if baseline.get('source') == 'Owner-provided ClustrMaps screenshots' and baseline.get('pageviews') == 7470:
                # Correct the owner's confirmed source/date without reimporting counts or events.
                baseline.update(source='Owner-recorded MapMyVisitors snapshot (May 2026)', snapshot_month='2026-05')
                connection.execute("UPDATE metadata SET value=? WHERE key='historical_baseline'", (json.dumps(baseline),))
        os.chmod(self.path, 0o600)
        return connection

    def record(self, event, now=None, country="ZZ"):
        now = now or datetime.now(timezone.utc)
        session_hash = hashlib.sha256(str(event.session_id).encode()).hexdigest()
        connection = self.connect()
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                if connection.execute("SELECT 1 FROM pageviews WHERE event_id=?", (str(event.event_id),)).fetchone():
                    return False
                count = connection.execute(
                    "SELECT COUNT(*) FROM pageviews WHERE session_hash=? AND occurred_at>=?",
                    (session_hash, (now - timedelta(hours=1)).isoformat()),
                ).fetchone()[0]
                if count >= 240:
                    raise HTTPException(429, "Pageview rate limit exceeded")
                connection.execute("INSERT INTO pageviews (event_id, session_hash, path, occurred_at, day, country) VALUES (?, ?, ?, ?, ?, ?)",
                                   (str(event.event_id), session_hash, event.path, now.isoformat(), now.date().isoformat(), country))
            return True
        finally:
            connection.close()

    def summary(self, days=30, now=None):
        now = now or datetime.now(timezone.utc)
        first_day = (now.date() - timedelta(days=days - 1)).isoformat()
        connection = self.connect()
        try:
            totals = connection.execute("SELECT COUNT(*) AS pageviews, COUNT(DISTINCT session_hash) AS sessions FROM pageviews").fetchone()
            rows = connection.execute("SELECT day, COUNT(*) AS pageviews, COUNT(DISTINCT session_hash) AS sessions FROM pageviews WHERE day>=? GROUP BY day ORDER BY day", (first_day,)).fetchall()
            by_day = {row["day"]: dict(row) for row in rows}
            daily = []
            for offset in range(days):
                day = (now.date() - timedelta(days=days - 1 - offset)).isoformat()
                daily.append(by_day.get(day, {"day": day, "pageviews": 0, "sessions": 0}))
            pages = [dict(row) for row in connection.execute("SELECT path, COUNT(*) AS pageviews FROM pageviews WHERE day>=? GROUP BY path ORDER BY pageviews DESC, path", (first_day,))]
            baseline = json.loads(connection.execute("SELECT value FROM metadata WHERE key='historical_baseline'").fetchone()[0])
            current_countries = {row["country"]: row["count"] for row in connection.execute("SELECT country, COUNT(*) AS count FROM pageviews GROUP BY country")}
            codes = set(baseline["countries"]) | set(current_countries)
            countries = [{"code": code, "historical": baseline["countries"].get(code, 0), "recorded": current_countries.get(code, 0),
                          "count": baseline["countries"].get(code, 0) + current_countries.get(code, 0)} for code in codes]
            countries.sort(key=lambda row: (-row["count"], row["code"]))
            return {"schema_version": 2, "timezone": "UTC", "started_at": connection.execute("SELECT value FROM metadata WHERE key='started_at'").fetchone()[0],
                    "total": {"pageviews": baseline["pageviews"] + totals["pageviews"], "sessions": totals["sessions"]},
                    "historical": baseline, "recorded": dict(totals), "countries": countries,
                    "geolocation": {"enabled": CountryLookup(self.directory).enabled, "provider": "DB-IP"},
                    "today": daily[-1], "days": days, "daily": daily, "pages": pages}
        finally:
            connection.close()

    def backup(self, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        source = self.connect()
        target = sqlite3.connect(temporary)
        try:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Analytics backup integrity check failed")
        finally:
            target.close()
            source.close()
        os.chmod(temporary, 0o600)
        temporary.replace(destination)


store = VisitStore(DATA_DIR)


@router.post("/pageview")
def record_pageview(event: Pageview, request: Request):
    origins = os.environ.get("RAMANCLOUD_ANALYTICS_ORIGINS", "https://ramancloud.xmu.edu.cn,http://localhost:5173,http://127.0.0.1:5173").split(",")
    if request.headers.get("origin") not in origins:
        raise HTTPException(403, "Unrecognized analytics origin")
    if request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1":
        return {"recorded": False}
    try:
        return {"recorded": store.record(event, country=CountryLookup(store.directory).lookup(request))}
    except (sqlite3.Error, OSError):
        logger.exception("Pageview persistence failed")
        raise HTTPException(503, "Visit statistics storage unavailable")


@router.get("/summary")
def visit_summary():
    try:
        return store.summary()
    except (sqlite3.Error, OSError):
        logger.exception("Visit statistics query failed")
        raise HTTPException(503, "Visit statistics storage unavailable")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Back up or export RamanCloud's local visit statistics")
    parser.add_argument("action", choices=("backup", "export"))
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.action == "backup":
        store.backup(args.destination)
    else:
        args.destination.write_text(json.dumps(store.summary(), indent=2) + "\n")
