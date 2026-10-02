# Visit Statistics

RamanCloud records first-party pageviews in SQLite and displays cumulative counts,
daily counts, anonymous sessions, country/region counts and page totals. The total
continues from V1's 7,470 historical pageviews. No third-party tracker is needed.

## Data and Privacy

- The default database is `~/.local/share/ramancloud/analytics/visits.sqlite3` under the backend service user's home directory (or `$XDG_DATA_HOME/ramancloud/analytics/visits.sqlite3`). It lives outside the application repository and frontend build assets, so replacing application code does not replace statistics.
- Set `RAMANCLOUD_ANALYTICS_DIR` to a persistent directory or mounted volume when deploying containers. Never replace or delete this directory during an application release.
- A pageview is a browser page load or navigation to a supported application page. Processing requests and health checks do not count. Retries share an event ID and are deduplicated.
- Sessions are random identifiers stored in the browser tab, renewed after 30 minutes of inactivity. They are not unique people. Only hashed session identifiers, event IDs, known route paths, country codes and UTC timestamps are stored.
- Raw IPs, user agents, query strings, uploaded filenames and spectral data are not collected. Do Not Track and Global Privacy Control are respected.
- These are browser-reported statistics, not authenticated audit records. Disabled JavaScript, failed requests or forged events can affect counts. Failed requests are retried twice without blocking processing.
- Aggregate counts are public. No event-level API or public database download is exposed.
- For a different deployment URL, set `RAMANCLOUD_ANALYTICS_ORIGINS` to comma-separated exact origins, such as `https://example.org,http://localhost:5173`. The API, UI and database must belong to the same deployment.

## Historical Baseline

The baseline of 7,470 pageviews since December 11, 2023 and the 20 screenshot
country/region counts are imported **once** into SQLite metadata. Cumulative
pageviews equal this baseline plus recorded new pageviews. Country counts likewise
continue from their respective screenshot numbers. Restarting, changing code or
restoring a backup never repeats the import. Backups include this metadata.

The owner recorded the historical pageview total in May 2026 from MapMyVisitors.
The exact day and country-chart period are unknown. Country counts
are partial, use a different historical metric/window, and do not add up to 7,470;
no missing country distribution or historical individual events are fabricated.
The screenshot's separate 5,933 map visits are not added to cumulative pageviews.
New daily trends, sessions and page breakdowns contain only observed events.
The gap after the historical snapshot is not reconstructed. A new MapMyVisitors
counter starts independently; no logged-in MapMyVisitors data is scraped or imported.
V1's historical counts continue in V2; new V1 visits are not automatically collected
until V1 is explicitly integrated with this first-party tracker too.

For a fresh deployment of a different site, set `RAMANCLOUD_ANALYTICS_IMPORT_V1=0`
before the database is first created. This starts from zero. The flag does not
overwrite the baseline in an existing database.
Original screenshots are kept locally in the analytics `legacy/` archive, not published with browser UI or bookmarks.

## 3D Globe

The homepage globe uses Three.js and locally served Natural Earth map geometry.
Its New V2 and May 2026 archive views are separate. Only country/region aggregates
are mapped, at Natural Earth representative label positions. They are not city
coordinates or precise IP locations. Unknown regions are listed but never plotted
at invented coordinates. Raw IP addresses are not stored or exposed.

The globe supports rotation, pause, zoom, and region selection, with a count list
available when WebGL fails. It loads near the viewport and stops rendering offscreen.
The Natural Earth source and public-domain terms are recorded in
`frontend/public/data/NOTICE.txt`; `frontend/scripts/prepare-globe-map.mjs` regenerates
the display geometry from the upstream 1:50m GeoJSON.

## Offline Country Lookup

Install the backend requirements, then place a country MMDB database at
`<analytics directory>/geo/country.mmdb`, or set `RAMANCLOUD_GEOIP_DATABASE`.
The current installation uses [DB-IP Country Lite](https://db-ip.com/db/download/ip-to-country-lite)
under CC BY 4.0; the public statistics section includes its required attribution.
Download a current MMDB release, decompress it, verify its published checksum,
and atomically replace the local file when updating. The database is monthly and
has approximate coverage; it is not an exact location or identity service.

Lookup happens locally using the request's IP; only the resulting country code is
stored. Raw IPs are never sent to a geolocation API. Private addresses, missing
databases and unsuccessful lookups become `ZZ` (Unknown) without dropping visits.
Make sure your reverse proxy supplies the actual client address. Forwarded headers
are accepted only from configured trusted proxies; set
`RAMANCLOUD_ANALYTICS_TRUSTED_PROXIES` to comma-separated known proxy IP/CIDRs
when necessary. Never use a blanket trust-all setting on a public backend.

## Backup

From the backend directory, using the same environment and data directory as the API:

```bash
.venv/bin/python backup_visits.py
.venv/bin/python visit_statistics.py export visit-summary.json
```

`backup_visits.py` uses SQLite's online backup API, checks database integrity, and
keeps the latest 30 daily snapshots in `backups/`. It works while the API is running;
do not copy the live database file without its WAL journal.

For the example systemd deployment, adjust the user, paths and optional
`Environment=RAMANCLOUD_ANALYTICS_DIR=...` to match your backend, then install:

```bash
sudo cp deploy/ramancloud-analytics-backup.service deploy/ramancloud-analytics-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ramancloud-analytics-backup.timer
systemctl list-timers ramancloud-analytics-backup.timer
```

The timer runs daily around 03:15 UTC and catches missed runs. Review failures with
`journalctl -u ramancloud-analytics-backup.service`. Copy verified backups to a
separate disk or off-site storage too: backups on the same disk do not protect
against disk loss. No off-site destination is configured automatically.

## Restore

Stop the backend before restoring. Check a snapshot with `PRAGMA integrity_check`
and confirm that its `pageviews` and `metadata` tables exist. Keep the entire old
data directory as a rollback copy. Restore the verified snapshot as
`visits.sqlite3` in a new, empty data directory; do not leave old `-wal` or `-shm`
files alongside it. Give the backend user ownership and permissions of 0700 for
the directory and 0600 for the database, then start the backend again. Verify
the aggregate counts before discarding the rollback copy.
