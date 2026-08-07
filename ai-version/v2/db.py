"""AI-generated storage layer from prompt v2. Quarantined — not the submission."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "tasks.db"

SEED_TASKS = [("Learn FastAPI", 0), ("Build CRUD API", 0), ("Publish to GitHub", 0)]


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        if connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
            connection.executemany(
                "INSERT INTO tasks (title, done) VALUES (?, ?)", SEED_TASKS
            )


def to_task(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "title": row["title"], "done": bool(row["done"])}


def list_tasks() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, title, done FROM tasks ORDER BY id"
        ).fetchall()
    return [to_task(row) for row in rows]


def get_task(task_id: int) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return to_task(row) if row else None


def create_task(title: str) -> dict:
    with get_connection() as connection:
        row = connection.execute(
            "INSERT INTO tasks (title, done) VALUES (?, ?) "
            "RETURNING id, title, done",
            (title, 0),
        ).fetchone()
    return to_task(row)


def update_task(task_id: int, title: str, done: bool) -> dict | None:
    with get_connection() as connection:
        row = connection.execute(
            "UPDATE tasks SET title = ?, done = ? WHERE id = ? "
            "RETURNING id, title, done",
            (title, int(done), task_id),
        ).fetchone()
    return to_task(row) if row else None


def delete_task(task_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return cursor.rowcount > 0
