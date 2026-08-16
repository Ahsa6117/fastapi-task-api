"""PostgreSQL storage layer for the Task API.

This is the one module that talks to the database. The API routes in
main.py call these helpers and never write SQL themselves, so this is the
only file that changed when storage moved from a Python list (A1) to a
SQLite file (A2) to a Postgres server (A3). The function names, their
arguments, and the dicts they return are all identical to the SQLite
version -- which is why main.py did not need a single edit.

Two things are genuinely new here:

* The connection string comes from the DATABASE_URL environment variable
  (loaded from .env), never from a password typed into this file.
* Placeholders are %s instead of ?, because that is what psycopg uses.
  They do the same job: the value travels beside the SQL, never inside
  it, so a title like "'; DROP TABLE tasks; --" is stored as text rather
  than executed as a command.
"""

import os
import time

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

# Read .env into the environment. Values already set in the real
# environment win, which is how docker compose overrides DATABASE_URL to
# point at the "db" service instead of localhost.
load_dotenv()

SEED_TASKS = [
    ("Learn FastAPI", False),
    ("Build CRUD API", False),
    ("Publish to GitHub", False),
]


def get_database_url() -> str:
    """Read the connection string, failing loudly if nobody set it.

    Crashing here with a clear message is much kinder than falling back to
    some hardcoded default and quietly writing to the wrong database.
    """
    url = os.getenv("DATABASE_URL")

    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env "
            "(cp .env.example .env) and fill in your password."
        )

    return url


def get_connection() -> psycopg.Connection:
    """Open a connection whose rows behave like dictionaries."""
    return psycopg.connect(get_database_url(), row_factory=dict_row)


# -------------------------
# Startup
# -------------------------

def create_table(connection: psycopg.Connection) -> None:
    """Create the tasks table if it is missing.

    `serial` is the Postgres way of saying "the database fills this in and
    counts up for me" -- the equivalent of SQLite's AUTOINCREMENT. `done`
    is a real boolean here, not the 0/1 integer SQLite had to fake.
    """
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id    serial  PRIMARY KEY,
            title text    NOT NULL,
            done  boolean NOT NULL DEFAULT false
        )
        """
    )


def create_index(connection: psycopg.Connection) -> None:
    """Index the column the search and sort extras query.

    An index is a lookup structure the database keeps beside the table so
    it can find matching rows without reading every one of them.
    """
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_title ON tasks (title)"
    )


def seed_if_empty(connection: psycopg.Connection) -> None:
    """Insert the example tasks only when the table has no rows.

    This is the first-run rule from A2, unchanged: restarting the app (or
    the whole stack) must never pile up a second set of example tasks.
    """
    row = connection.execute("SELECT COUNT(*) AS total FROM tasks").fetchone()

    if row["total"] == 0:
        connection.cursor().executemany(
            "INSERT INTO tasks (title, done) VALUES (%s, %s)",
            SEED_TASKS,
        )


def wait_for_database(attempts: int = 30, delay: float = 1.0) -> None:
    """Retry the first connection until Postgres is accepting clients.

    Under docker compose the api container starts the moment the db
    container starts, but Postgres needs a few seconds after that before
    it will answer. `depends_on` only waits for the container, not for the
    database inside it, so the app has to be patient itself.
    """
    for attempt in range(1, attempts + 1):
        try:
            with psycopg.connect(get_database_url()):
                return
        except psycopg.OperationalError:
            if attempt == attempts:
                raise
            print(f"Waiting for Postgres... ({attempt}/{attempts})")
            time.sleep(delay)


def init_db() -> None:
    """Wait for the server, then create the table, index, and seed data.

    The `with` block is one transaction: if any statement fails, every
    change in it is rolled back. That keeps startup all-or-nothing, so a
    crash mid-seed can never leave one and a half example tasks behind.
    """
    wait_for_database()

    with get_connection() as connection:
        create_table(connection)
        create_index(connection)
        seed_if_empty(connection)


def ping() -> bool:
    """Run the cheapest possible query, to prove the database answers.

    SELECT 1 touches no tables; it only asks "are you there?". /health
    uses it so a failing database shows up as an unhealthy app.
    """
    try:
        with get_connection() as connection:
            connection.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


def row_to_task(row: dict) -> dict:
    """Turn a database row into the JSON shape the API has always returned."""
    return {
        "id": row["id"],
        "title": row["title"],
        "done": bool(row["done"]),
    }


# -------------------------
# Read
# -------------------------

def list_tasks(
    search: str | None = None,
    done: bool | None = None,
    sort: str = "id",
) -> list[dict]:
    """List tasks, letting the database do the filtering and sorting."""
    sql = "SELECT id, title, done FROM tasks"
    conditions: list[str] = []
    values: list = []

    if search:
        conditions.append("title ILIKE %s")
        values.append(f"%{search}%")

    if done is not None:
        conditions.append("done = %s")
        values.append(done)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    # `sort` never reaches the SQL as user text: it only picks between two
    # fixed clauses written here, so there is nothing to inject.
    sql += " ORDER BY lower(title)" if sort == "title" else " ORDER BY id"

    with get_connection() as connection:
        rows = connection.execute(sql, values).fetchall()

    return [row_to_task(row) for row in rows]


def get_stats() -> dict:
    """Count tasks in SQL rather than counting rows in Python."""
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*)                                    AS total,
                COUNT(*) FILTER (WHERE done)                AS done,
                COUNT(*) FILTER (WHERE NOT done)            AS pending
            FROM tasks
            """
        ).fetchone()

    return {"total": row["total"], "done": row["done"], "pending": row["pending"]}


def get_task(task_id: int) -> dict | None:
    with get_connection() as connection:
        # The %s placeholder keeps the id out of the SQL text itself.
        row = connection.execute(
            "SELECT id, title, done FROM tasks WHERE id = %s",
            (task_id,),
        ).fetchone()

    return row_to_task(row) if row else None


# -------------------------
# Create
# -------------------------

def create_task(title: str) -> dict:
    """Insert one task and return it with the id the database assigned.

    RETURNING is a Postgres convenience: the INSERT hands back the row it
    just wrote, id included, so there is no second SELECT to fetch it.
    """
    with get_connection() as connection:
        row = connection.execute(
            "INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING id, title, done",
            (title, False),
        ).fetchone()

    return row_to_task(row)


# -------------------------
# Update and delete
# -------------------------

def update_task(task_id: int, title: str, done: bool) -> dict:
    """Overwrite one task's title and done flag, then return the new row."""
    with get_connection() as connection:
        row = connection.execute(
            """
            UPDATE tasks
               SET title = %s, done = %s
             WHERE id = %s
            RETURNING id, title, done
            """,
            (title, done, task_id),
        ).fetchone()

    return row_to_task(row)


def delete_task(task_id: int) -> bool:
    """Delete one task. Returns False when no row had that id."""
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM tasks WHERE id = %s",
            (task_id,),
        )
        deleted = cursor.rowcount

    return deleted > 0
