"""The Assignment 1 endpoint checks, run against the SQLite version.

These are the same requests and the same expected responses as before the
storage layer moved from a Python list to tasks.db. They pass unchanged,
which is the proof that storage is an implementation detail.

Run with:  python smoke_test.py
"""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

import db

# Use a throwaway database so running the checks never touches tasks.db.
db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"

import main  # noqa: E402  (imported after DB_PATH is redirected)

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
# A second client is a second startup against the same database file.
with TestClient(main.app) as client:
    check(
        "seed did not run twice",
        len(client.get("/tasks").json()),
        3,
    )

print(f"\nAll {checks_run} checks passed.")
