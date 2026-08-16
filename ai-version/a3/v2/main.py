"""
FastAPI To-Do API backed by PostgreSQL.

All SQL lives in db.py - this module only wires up HTTP routes and
validation. No raw SQL here.
"""

from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import db
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel


app = FastAPI(title="Task API")


@app.on_event("startup")
def on_startup() -> None:
    db.wait_for_database()
    db.init_db()


# ---------------------------------------------------------------------------
# Error handling: every error body must be {"error": "<message>"}, and any
# malformed/invalid request body must return 400, not FastAPI's default 422.
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Invalid request body"},
    )


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class TaskCreate(BaseModel):
    title: str


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/tasks")
def get_tasks():
    return db.list_tasks()


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    task = db.get_task(task_id)
    if task is None:
        return error_response(status.HTTP_404_NOT_FOUND, "Task not found")
    return task


@app.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate):
    title = payload.title.strip()
    if not title:
        return error_response(status.HTTP_400_BAD_REQUEST, "Title is required")
    task = db.create_task(title)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=task)


@app.put("/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate):
    if payload.title is None and payload.done is None:
        return error_response(
            status.HTTP_400_BAD_REQUEST, "At least one of title or done is required"
        )

    existing = db.get_task(task_id)
    if existing is None:
        return error_response(status.HTTP_404_NOT_FOUND, "Task not found")

    new_title = existing["title"]
    if payload.title is not None:
        stripped = payload.title.strip()
        if not stripped:
            return error_response(status.HTTP_400_BAD_REQUEST, "Title cannot be blank")
        new_title = stripped

    new_done = existing["done"] if payload.done is None else payload.done

    updated = db.update_task(task_id, new_title, new_done)
    return updated


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int):
    deleted = db.delete_task(task_id)
    if not deleted:
        return error_response(status.HTTP_404_NOT_FOUND, "Task not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
