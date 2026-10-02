import concurrent.futures
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import HTTPException, Request
from pydantic import ValidationError
from visit_statistics import Pageview, VisitStore, record_pageview
from visit_geolocation import CountryLookup, client_address
import backup_visits


class VisitStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = VisitStore(Path(self.temporary.name) / "data")
        self.now = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
        self.session = uuid4()

    def event(self, path="/", session=None):
        return Pageview(event_id=uuid4(), session_id=session or self.session, path=path)

    def request(self, **headers):
        return Request({"type": "http", "headers": [(key.encode(), value.encode()) for key, value in headers.items()]})

    def test_deduplication_and_restart_persistence(self):
        event = self.event()
        self.assertTrue(self.store.record(event, self.now))
        self.assertFalse(self.store.record(event, self.now))
        restarted = VisitStore(self.store.directory)
        self.assertEqual(restarted.summary(now=self.now)["total"], {"pageviews": 7471, "sessions": 1})

    def test_sessions_pages_and_utc_daily_buckets(self):
        self.store.record(self.event(), self.now - timedelta(days=2))
        self.store.record(self.event("/spectral"), self.now)
        self.store.record(self.event("/spectral", uuid4()), self.now)
        summary = self.store.summary(now=self.now)
        self.assertEqual(summary["total"], {"pageviews": 7473, "sessions": 2})
        self.assertEqual(summary["recorded"], {"pageviews": 3, "sessions": 2})
        self.assertEqual(summary["today"]["pageviews"], 2)
        self.assertEqual(len(summary["daily"]), 30)
        self.assertEqual(summary["daily"][-2]["pageviews"], 0)
        self.assertEqual(summary["pages"][0], {"path": "/spectral", "pageviews": 2})

    def test_old_events_are_kept_but_not_in_recent_window(self):
        self.store.record(self.event(), self.now - timedelta(days=100))
        summary = self.store.summary(now=self.now)
        self.assertEqual(summary["total"]["pageviews"], 7471)
        self.assertEqual(sum(day["pageviews"] for day in summary["daily"]), 0)

    def test_storage_contains_no_ip_or_original_session_id(self):
        self.store.record(self.event(), self.now)
        with sqlite3.connect(self.store.path) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(pageviews)")]
            row = connection.execute("SELECT * FROM pageviews").fetchone()
        self.assertEqual(columns, ["event_id", "session_hash", "path", "occurred_at", "day", "country"])
        self.assertNotIn(str(self.session), row)
        self.assertEqual(os.stat(self.store.path).st_mode & 0o777, 0o600)

    def test_backup_and_restore_keep_all_records(self):
        self.store.record(self.event(), self.now)
        backup = Path(self.temporary.name) / "backup" / "snapshot.sqlite3"
        self.store.backup(backup)
        restored = VisitStore(Path(self.temporary.name) / "restored")
        restored.directory.mkdir()
        shutil.copy2(backup, restored.path)
        self.assertEqual(restored.summary(now=self.now), self.store.summary(now=self.now))
        with sqlite3.connect(backup) as connection:
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_concurrent_writes_do_not_lose_events(self):
        events = [self.event() for _ in range(20)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda event: self.store.record(event, self.now), events))
        self.assertEqual(self.store.summary(now=self.now)["total"]["pageviews"], 7490)

    def test_historical_baseline_is_imported_once_and_countries_continue(self):
        self.assertEqual(self.store.summary(now=self.now)["total"]["pageviews"], 7470)
        self.store.record(self.event(), self.now, country="CN")
        self.store.record(self.event(), self.now, country="US")
        summary = VisitStore(self.store.directory).summary(now=self.now)
        self.assertEqual(summary["total"]["pageviews"], 7472)
        self.assertEqual(summary["historical"]["pageviews"], 7470)
        countries = {country["code"]: country for country in summary["countries"]}
        self.assertEqual(countries["CN"], {"code": "CN", "historical": 796, "recorded": 1, "count": 797})
        self.assertEqual(countries["US"]["count"], 122)
        self.assertEqual(summary["today"]["pageviews"], 2)
        with patch.dict(os.environ, {"RAMANCLOUD_ANALYTICS_IMPORT_V1": "0"}):
            self.assertEqual(self.store.summary(now=self.now)["total"]["pageviews"], 7472)

    def test_fresh_deployments_can_disable_the_ramancloud_baseline(self):
        with patch.dict(os.environ, {"RAMANCLOUD_ANALYTICS_IMPORT_V1": "0"}):
            self.assertEqual(self.store.summary(now=self.now)["total"]["pageviews"], 0)

    def test_snapshot_correction_preserves_counts_and_events(self):
        self.store.record(self.event(), self.now, country='CN')
        with self.store.connect() as connection:
            old = json.loads(connection.execute("SELECT value FROM metadata WHERE key='historical_baseline'").fetchone()[0])
            old['source'] = 'Owner-provided ClustrMaps screenshots'
            old.pop('snapshot_month', None)
            connection.execute("UPDATE metadata SET value=? WHERE key='historical_baseline'", (json.dumps(old),))
        for _ in range(2):
            result = self.store.summary(now=self.now)
            self.assertEqual(result['historical']['snapshot_month'], '2026-05')
            self.assertIn('MapMyVisitors', result['historical']['source'])
            self.assertEqual(result['recorded']['pageviews'], 1)
            self.assertEqual(result['total']['pageviews'], 7471)
            self.assertEqual(result['historical']['countries'], old['countries'])

    def test_existing_database_migration_keeps_records(self):
        self.store.directory.mkdir()
        with sqlite3.connect(self.store.path) as connection:
            connection.execute("CREATE TABLE pageviews (event_id TEXT PRIMARY KEY, session_hash TEXT NOT NULL, path TEXT NOT NULL, occurred_at TEXT NOT NULL, day TEXT NOT NULL)")
            connection.execute("INSERT INTO pageviews VALUES (?, ?, ?, ?, ?)", (str(uuid4()), "old-session", "/", self.now.isoformat(), self.now.date().isoformat()))
        summary = self.store.summary(now=self.now)
        self.assertEqual(summary["total"]["pageviews"], 7471)
        unknown = next(country for country in summary["countries"] if country["code"] == "ZZ")
        self.assertEqual(unknown["count"], 1)

    def test_forwarded_addresses_are_only_accepted_from_trusted_peers(self):
        def request(peer, forwarded):
            return Request({"type": "http", "client": (peer, 1234), "headers": [(b"x-forwarded-for", forwarded.encode())]})
        self.assertEqual(str(client_address(request("8.8.8.8", "1.1.1.1"))), "8.8.8.8")
        self.assertEqual(str(client_address(request("127.0.0.1", "1.1.1.1, 8.8.8.8"))), "8.8.8.8")
        self.assertEqual(str(client_address(request("127.0.0.1", "8.8.8.8, 127.0.0.1"))), "8.8.8.8")
        self.assertIsNone(client_address(request("127.0.0.1", "malformed")))
        self.assertEqual(CountryLookup(self.store.directory).lookup(request("127.0.0.1", "")), "ZZ")

    def test_daily_backup_retention_and_failed_backup(self):
        self.store.record(self.event(), self.now)
        directory = self.store.directory / "backups"
        directory.mkdir()
        for day in range(1, 32):
            (directory / f"visits-2025-01-{day:02d}.sqlite3").touch()
        with patch.object(backup_visits, "store", self.store), patch.object(backup_visits, "DATA_DIR", self.store.directory):
            with patch.object(self.store, "backup", side_effect=RuntimeError("disk unavailable")):
                with self.assertRaises(RuntimeError):
                    backup_visits.main()
            self.assertEqual(len(list(directory.glob("*.sqlite3"))), 31)
            backup_visits.main()
            self.assertEqual(len(list(directory.glob("*.sqlite3"))), 30)
            newest = sorted(directory.glob("*.sqlite3"))[-1]
            with sqlite3.connect(newest) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM pageviews").fetchone()[0], 1)

    def test_storage_errors_return_unavailable_not_fake_success(self):
        with patch("visit_statistics.store.record", side_effect=sqlite3.OperationalError("disk unavailable")):
            with self.assertLogs("visit_statistics", level="ERROR"):
                with self.assertRaises(HTTPException) as error:
                    record_pageview(self.event(), self.request(origin="https://ramancloud.xmu.edu.cn"))
            self.assertEqual(error.exception.status_code, 503)

    def test_rate_limit(self):
        for _ in range(240):
            self.store.record(self.event(), self.now)
        with self.assertRaises(HTTPException) as error:
            self.store.record(self.event(), self.now)
        self.assertEqual(error.exception.status_code, 429)

    def test_validation_rejects_unknown_paths_and_bad_identifiers(self):
        for fields in ({"path": "/uploaded/private-file.txt", "event_id": uuid4(), "session_id": uuid4()},
                       {"path": "/", "event_id": "invalid", "session_id": uuid4()}):
            with self.assertRaises(ValidationError):
                Pageview(**fields)

    def test_unknown_origin_and_privacy_headers(self):
        with patch("visit_statistics.store", self.store):
            with self.assertRaises(HTTPException) as error:
                record_pageview(self.event(), self.request(origin="https://other.example"))
            self.assertEqual(error.exception.status_code, 403)
            for header in ("dnt", "sec-gpc"):
                self.assertEqual(record_pageview(self.event(), self.request(origin="https://ramancloud.xmu.edu.cn", **{header: "1"})), {"recorded": False})
            self.assertEqual(self.store.summary(now=self.now)["recorded"]["pageviews"], 0)


if __name__ == "__main__":
    unittest.main()
