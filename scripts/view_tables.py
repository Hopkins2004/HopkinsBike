"""Debug helper: dump every table in the Hopkins database.

Run from the repo root:  .venv/bin/python scripts/view_tables.py
"""
import os
import sqlite3

DB_PATH = os.environ.get(
    "HOPKINS_DB",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "data.db"),
)


def dump_tables():
    """Claude_dump_tables: print every row of every table in the database."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    for table in tables:
        print("###################################### This is ", table[0],
              "#######################################")
        cursor.execute("SELECT * from " + table[0])
        for element in cursor.fetchall():
            print(element)
    connection.close()


if __name__ == "__main__":
    dump_tables()
