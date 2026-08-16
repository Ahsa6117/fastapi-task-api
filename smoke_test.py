"""The Assignment 1 endpoint checks, run against the Postgres version.

These are the same requests and the same expected responses as when tasks
lived in a Python list (A1) and in a tasks.db file (A2). They pass
unchanged against a third storage engine, which is the proof that storage
is an implementation detail: the contract lives in the routes, not in the
database.

The checks run against a throwaway database (tasks_test) that is dropped
and recreated each run, so your real tasks are never touched.

Run with:  python smoke_test.py
(the Postgres container must be up -- docker compose up -d db)
"""

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

TEST_DB = "tasks_test"


def build_test_database() -> str:
    """Drop and recreate tasks_test, and return its connection string."""
    url = os.getenv("DATABASE_URL")

    if not url:
        raise SystemExit(
            "DATABASE_URL is not set. Copy .env.example to .env first."
        )

    # Connect to the built-in "postgres" database, because you cannot drop
    # or create a database while you are connected to it.
    admin_url = url.rsplit("/", 1)[0] + "/postgres"

    # autocommit: CREATE DATABASE is not allowed inside a transaction.
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        connection.execute(f"CREATE DATABASE {TEST_DB}")

    return url.rsplit("/", 1)[0] + "/" + TEST_DB


# Redirect the app at the throwaway database *before* importing it.
os.environ["DATABASE_URL"] = build_test_database()

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402  (imported after DATABASE_URL is redirected)

checks_run = 0


def check(label: str, actual, expected) -> None:
    global checks_run
    assert actual == expected, f"{label}: expected {expected!r}, got {actual!r}"
    checks_run += 1
    print(f"  ok  {label}")


with TestClient(main.app) as client:
    print("Seeding")
    response = client.get("/tasks")
    check("GET /tasks -> 200", response.status_code, 200)
    check("seeds exactly three tasks", len(response.json()), 3)

    print("Health")
    response = client.get("/health")
    check("GET /health -> 200", response.status_code, 200)
    check("health reports the database", response.json()["db"], "ok")

    print("Read")
    response = client.get("/tasks/1")
    check("GET /tasks/1 -> 200", response.status_code, 200)
    check("returns the right task", response.json()["id"], 1)

    response = client.get("/tasks/999")
    check("GET /tasks/999 -> 404", response.status_code, 404)
    check("404 body has an error key", "error" in response.json(), True)

    print("Create")
    response = client.post("/tasks", json={"title": "Buy milk"})
    check("POST /tasks -> 201", response.status_code, 201)
    created = response.json()
    check("new task is not done", created["done"], False)
    check("database assigned an id", created["id"] > 0, True)

    check(
        "POST with empty title -> 400",
        client.post("/tasks", json={"title": "   "}).status_code,
        400,
    )
    check(
        "POST with no title -> 400",
        client.post("/tasks", json={}).status_code,
        400,
    )

    print("Parameterized queries")
    # If the title were glued into the SQL text this would drop the table
    # and every check after it would fail. It is stored as plain text.
    injection = "'); DROP TABLE tasks; --"
    response = client.post("/tasks", json={"title": injection})
    check("a SQL-looking title is stored as text", response.json()["title"], injection)
    check("the table is still there", client.get("/tasks").status_code, 200)
    client.delete(f"/tasks/{response.json()['id']}")

    print("Update")
    task_id = created["id"]
    response = client.put(f"/tasks/{task_id}", json={"done": True})
    check("PUT -> 200", response.status_code, 200)
    check("task is now done", response.json()["done"], True)
    check("title was left alone", response.json()["title"], "Buy milk")

    check(
        "PUT unknown id -> 404",
        client.put("/tasks/999", json={"done": True}).status_code,
        404,
    )
    check(
        "PUT with empty body -> 400",
        client.put(f"/tasks/{task_id}", json={}).status_code,
        400,
    )

    print("Delete")
    check(
        "DELETE -> 204",
        client.delete(f"/tasks/{task_id}").status_code,
        204,
    )
    check(
        "the task is gone",
        client.get(f"/tasks/{task_id}").status_code,
        404,
    )
    check(
        "DELETE unknown id -> 404",
        client.delete("/tasks/999").status_code,
        404,
    )

print("\nPersistence")
# A second client is a second startup against the same database.
with TestClient(main.app) as client:
    check(
        "seed did not run twice",
        len(client.get("/tasks").json()),
        3,
    )

print(f"\nAll {checks_run} checks passed.")
