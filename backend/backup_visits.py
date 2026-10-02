"""Daily verified snapshots; keep the most recent 30 daily backups."""

from datetime import datetime, timezone
from pathlib import Path

from visit_statistics import DATA_DIR, store


def main():
    if not store.path.exists():
        print("No visit database exists yet; no backup created.")
        return
    backup_dir = Path(DATA_DIR) / "backups"
    name = datetime.now(timezone.utc).strftime("visits-%Y-%m-%d.sqlite3")
    store.backup(backup_dir / name)
    # Prune only after a new integrity-checked backup was written successfully.
    for old in sorted(backup_dir.glob("visits-????-??-??.sqlite3"), reverse=True)[30:]:
        old.unlink()
    print(f"Verified visit statistics backup: {backup_dir / name}")


if __name__ == "__main__":
    main()
