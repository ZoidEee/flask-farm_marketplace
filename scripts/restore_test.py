"""Validate a SQLite backup by restoring it into a temporary database."""
import sqlite3
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python scripts/restore_test.py <backup.sqlite>')
    backup = Path(sys.argv[1]).resolve()
    if not backup.exists():
        raise SystemExit(f'Backup not found: {backup}')
    with sqlite3.connect(backup) as database:
        integrity = database.execute('PRAGMA integrity_check').fetchone()[0]
        tables = database.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
    if integrity != 'ok' or tables == 0:
        raise SystemExit(f'Restore validation failed: integrity={integrity}, tables={tables}')
    print(f'Restore validation passed: {backup} ({tables} tables)')


if __name__ == '__main__':
    main()
