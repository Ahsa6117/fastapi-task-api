"""AI-generated migration from prompt v1. Quarantined — not the submission.

Generated from docs/ai-prompt.md version 1 without reference to db.py.
Kept exactly as produced so the diff and the review below stay honest.
"""

import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

DB_PATH = "tasks.db"

# One shared connection for the whole app. check_same_thread=False is needed
# because FastAPI runs sync endpoints on a thread pool.
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row


def init_db():
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    if count == 0:
        conn.executemany(
            "INSERT INTO tasks (title, done) VALUES (?, ?)",
            [
                ("Learn FastAPI", 0),
                ("Build CRUD API", 0),
                ("Publish to GitHub", 0),
            ],
        )

    conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    conn.close()


app = FastAPI(title="Task API (SQLite)", lifespan=lifespan)


class TaskIn(BaseModel):
    title: str
    done: bool = False


class TaskOut(BaseModel):
    id: int
    title: str
    done: bool


@app.get("/tasks", response_model=list[TaskOut])
def list_tasks():
    rows = conn.execute("SELECT id, title, done FROM tasks").fetchall()
    return [dict(row) for row in rows]


@app.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int):
    row = conn.execute(
        "SELECT id, title, done FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return dict(row)


@app.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(task: TaskIn):
    if not task.title:
        raise HTTPException(status_code=400, detail="Title is required")

    row = conn.execute(
        "INSERT INTO tasks (title, done) VALUES (?, ?) RETURNING id, title, done",
        (task.title, int(task.done)),
    ).fetchone()
    conn.commit()

    return dict(row)


@app.put("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, task: TaskIn):
    if not task.title:
        raise HTTPException(status_code=400, detail="Title is required")

    row = conn.execute(
        "UPDATE tasks SET title = ?, done = ? WHERE id = ? RETURNING id, title, done",
        (task.title, int(task.done), task_id),
    ).fetchone()
    conn.commit()

    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return dict(row)


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Task not found")
