"""
All SQL for the to-do API lives in this module. main.py must never
build or execute SQL directly - it only calls the functions below.
"""

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ["DATABASE_URL"]


@contextmanager
def get_conn():
    """Yield a psycopg connection with dict-style rows, committing on success."""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


def init_db() -> None:
    """Create the tasks table if it doesn't exist, and seed it if empty."""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                done BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )

        row = conn.execute("SELECT COUNT(*) AS count FROM tasks").fetchone()
        if row["count"] == 0:
            conn.execute(
                """
                INSERT INTO tasks (title, done) VALUES
                    (%s, %s),
                    (%s, %s),
                    (%s, %s)
                """,
                (
                    "Buy groceries", False,
                    "Write report", False,
                    "Walk the dog", True,
                ),
            )


def list_tasks() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, done FROM tasks ORDER BY id"
        ).fetchall()
        return rows


def get_task(task_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, done FROM tasks WHERE id = %s",
            (task_id,),
        ).fetchone()
        return row


def create_task(title: str, done: bool = False) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO tasks (title, done)
            VALUES (%s, %s)
            RETURNING id, title, done
            """,
            (title, done),
        ).fetchone()
        return row


def update_task(task_id: int, title: str, done: bool) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE tasks
            SET title = %s, done = %s
            WHERE id = %s
            RETURNING id, title, done
            """,
            (title, done, task_id),
        ).fetchone()
        return row


def delete_task(task_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "DELETE FROM tasks WHERE id = %s RETURNING id",
            (task_id,),
        ).fetchone()
        return row is not None
