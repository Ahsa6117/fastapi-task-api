"""SQLite storage layer for the Task API.

The API routes never talk to SQLite directly. They call the helpers in
this module, so swapping the storage layer never touches the endpoints.
"""

import sqlite3
from pathlib import Path

# The database is a single file next to this module. Opening a SQLite
# file that does not exist creates it, so no manual setup is needed.
DB_PATH = Path(__file__).parent / "tasks.db"

SEED_TASKS = [
    ("Learn FastAPI", 0),
    ("Build CRUD API", 0),
    ("Publish to GitHub", 0),
]


def get_connection() -> sqlite3.Connection:
    """Open a connection whose rows behave like dictionaries."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_table(connection: sqlite3.Connection) -> None:
    """Create the tasks table if it is missing."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT    NOT NULL,
            done  INTEGER NOT NULL DEFAULT 0
        )
        """
    )


def seed_if_empty(connection: sqlite3.Connection) -> None:
    """Insert the example tasks only when the table has no rows."""
    row = connection.execute("SELECT COUNT(*) AS total FROM tasks").fetchone()

    if row["total"] == 0:
        connection.executemany(
            "INSERT INTO tasks (title, done) VALUES (?, ?)",
            SEED_TASKS,
        )


def init_db() -> None:
    """Create the database file, the table, and the first-run seed data."""
    with get_connection() as connection:
        create_table(connection)
        seed_if_empty(connection)
