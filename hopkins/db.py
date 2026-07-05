"""Database layer: a single connection helper plus schema creation / ordered migrations.

Every route goes through get_db() instead of opening its own sqlite3 connection, so the
connection is always committed on success, rolled back on error, and closed in all cases."""
import sqlite3
from contextlib import contextmanager

from flask import current_app


@contextmanager
def get_db():
    """Claude_get_db: yield a sqlite3 connection bound to the configured DB.
    Commits on clean exit, rolls back on exception, and always closes."""
    conn = sqlite3.connect(current_app.config['DB_PATH'])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _column_exists(cursor, table, column):
    """Claude__column_exists: True if `column` is already present on `table`."""
    cursor.execute("PRAGMA table_info(%s)" % table)
    return any(row[1] == column for row in cursor.fetchall())


def init_db(db_path):
    """Claude_init_db: create the base schema if missing, then apply ordered, idempotent
    migrations (guarded by PRAGMA checks rather than swallowing every exception)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id_user INTEGER PRIMARY KEY,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            status TEXT NOT NULL,
            credit INTEGER NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id_analysis INTEGER PRIMARY KEY,
            id_user INTEGER NOT NULL,
            title TEXT,
            length INTEGER,
            distance NUMBER,
            day DATE,
            avg_pwr NUMBER,
            avg_speed NUMBER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS segments (
            id_segments INTEGER PRIMARY KEY,
            id_analysis INTEGER NOT NULL,
            start_pt INTEGER NOT NULL,
            end_pt INTEGER NOT NULL,
            parameters TEXT,
            cda NUMBER,
            title TEXT,
            comment TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gpx (
            id_route INTEGER PRIMARY KEY,
            id_user INTEGER NOT NULL,
            title TEXT,
            length INTEGER,
            distance NUMBER
        )
    ''')

    # Ordered, idempotent migrations (replaces the old try/except: pass ALTERs).
    if not _column_exists(cursor, 'segments', 'cda_data'):
        cursor.execute('ALTER TABLE segments ADD COLUMN cda_data TEXT')
    if not _column_exists(cursor, 'users', 'verified'):
        cursor.execute('ALTER TABLE users ADD COLUMN verified INTEGER DEFAULT 1')

    # Emails must be unique or login resolves to an arbitrary duplicate. Fails (and is
    # skipped with a warning) only if a pre-existing DB already holds duplicates.
    try:
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)')
    except sqlite3.IntegrityError:
        print('WARNING: duplicate emails in users table; unique index not created. '
              'Deduplicate users(email) manually.')

    conn.commit()
    conn.close()
