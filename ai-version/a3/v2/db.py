"""
All SQL for the To-Do API lives in this module. main.py must never contain
raw SQL - it only calls the functions defined here.
"""

import os
import time
from typing import Optional

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get("DATABASE_URL")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE
);
"""

COUNT_TASKS_SQL = "SELECT COUNT(*) AS count FROM tasks;"

SEED_TASKS_SQL = "INSERT INTO tasks (title, done) VALUES (%s, %s);"

SEED_DATA = [
    ("Buy groceries", False),
    ("Write project report", False),
    ("Walk the dog", True),
]

SELECT_ALL_SQL = "SELECT id, title, done FROM tasks ORDER BY id;"

SELECT_ONE_SQL = "SELECT id, title, done FROM tasks WHERE id = %s;"

INSERT_TASK_SQL = (
    "INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING id, title, done;"
)

UPDATE_TASK_SQL = (
    "UPDATE tasks SET title = %s, done = %s WHERE id = %s "
    "RETURNING id, title, done;"
)

DELETE_TASK_SQL = "DELETE FROM tasks WHERE id = %s;"


def get_connection() -> psycopg.Connection:
    """Open a new connection to the database."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def wait_for_database(max_attempts: int = 30, delay_seconds: float = 1.0) -> None:
    """
    Retry the first connection until Postgres is actually accepting
    connections. depends_on / healthchecks only cover the container in
    Docker Compose - this makes startup robust outside compose too
    (e.g. running the app directly against a db that is still booting).
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            with get_connection() as conn:
                conn.execute("SELECT 1;")
            return
        except Exception as exc:  # psycopg.OperationalError, etc.
            last_error = exc
            time.sleep(delay_seconds)
    raise RuntimeError(
        f"Could not connect to the database after {max_attempts} attempts"
    ) from last_error


def init_db() -> None:
    """Create the tasks table if needed and seed it if it is empty."""
    with get_connection() as conn:
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()

        row = conn.execute(COUNT_TASKS_SQL).fetchone()
        if row["count"] == 0:
            with conn.cursor() as cur:
                cur.executemany(SEED_TASKS_SQL, SEED_DATA)
            conn.commit()


def list_tasks() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(SELECT_ALL_SQL).fetchall()
        return list(rows)


def get_task(task_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(SELECT_ONE_SQL, (task_id,)).fetchone()
        return row


def create_task(title: str) -> dict:
    with get_connection() as conn:
        row = conn.execute(INSERT_TASK_SQL, (title, False)).fetchone()
        conn.commit()
        return row


def update_task(task_id: int, title: str, done: bool) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(UPDATE_TASK_SQL, (title, done, task_id)).fetchone()
        conn.commit()
        return row


def delete_task(task_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(DELETE_TASK_SQL, (task_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
