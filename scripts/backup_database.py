"""Create a consistent SQLite backup.

Schedule this script with Task Scheduler/cron and copy the output to durable,
encrypted storage. For PostgreSQL deployments, use pg_dump instead.
"""
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    database_url = os.environ.get('DATABASE_URL', 'sqlite:///farm_marketplace.db')
    if not database_url.startswith('sqlite:///'):
        raise SystemExit('This helper supports SQLite only; use pg_dump for PostgreSQL.')
    source = Path(database_url.removeprefix('sqlite:///'))
    if not source.is_absolute():
        source = Path(__file__).resolve().parents[1] / source
    if not source.exists():
        raise SystemExit(f'Database not found: {source}')

    destination_dir = Path(os.environ.get('BACKUP_DIR', str(source.parent / 'backups')))
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f'{source.stem}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.sqlite'
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as backup_db:
        source_db.backup(backup_db)
    print(destination)


if __name__ == '__main__':
    main()
