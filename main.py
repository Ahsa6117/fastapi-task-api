from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts: creates tasks.db, the tasks
    # table, and the three example tasks if the table is still empty.
    db.init_db()
    yield


app = FastAPI(
    title="Task API",
    version="2.0",
    description="A small CRUD API for managing to-do tasks, stored in SQLite.",
    lifespan=lifespan,
)


# -------------------------
# Data models
# -------------------------

class Task(BaseModel):
    id: int
    title: str
    done: bool


class TaskCreate(BaseModel):
    title: str


class TaskUpdate(BaseModel):
    title: str | None = None
    done: bool | None = None


# -------------------------
# Error handling
# -------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Invalid request body"},
    )


# -------------------------
# General endpoints
# -------------------------

@app.get("/", summary="Describe the API")
def read_root():
    return {
        "name": "Task API",
        "version": "2.0",
        "endpoints": ["/tasks", "/stats"],
    }


@app.get("/health", summary="Check server health")
def health_check():
    return {"status": "ok"}


# -------------------------
# Read endpoints
# -------------------------

@app.get(
    "/tasks",
    response_model=list[Task],
    summary="List all tasks",
)
def list_tasks(
    search: str | None = Query(
        default=None,
        description="Only tasks whose title contains this text",
    ),
    done: bool | None = Query(
        default=None,
        description="Filter by completion status",
    ),
    sort: Literal["id", "title"] = Query(
        default="id",
        description="Sort by id (default) or alphabetically by title",
    ),
):
    return db.list_tasks(search=search, done=done, sort=sort)


@app.get("/stats", summary="Count tasks")
def read_stats():
    return db.get_stats()


@app.get(
    "/tasks/{task_id}",
    response_model=Task,
    summary="Get one task",
)
def get_task(task_id: int):
    task = db.get_task(task_id)

    if task is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Task {task_id} not found"},
        )

    return task


# -------------------------
# Create endpoint
# -------------------------

@app.post(
    "/tasks",
    response_model=Task,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
)
def create_task(task_data: TaskCreate):
    title = task_data.title.strip()

    if not title:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Title is required and cannot be empty"
            },
        )

    return db.create_task(title)


# -------------------------
# Update endpoint
# -------------------------

@app.put(
    "/tasks/{task_id}",
    response_model=Task,
    summary="Update a task",
)
def update_task(task_id: int, task_data: TaskUpdate):
    task = db.get_task(task_id)

    if task is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Task {task_id} not found"},
        )

    if task_data.title is None and task_data.done is None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Provide title, done, or both"},
        )

    if task_data.title is not None:
        title = task_data.title.strip()

        if not title:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Title cannot be empty"},
            )

        task["title"] = title

    if task_data.done is not None:
        task["done"] = task_data.done

    return db.update_task(task_id, task["title"], task["done"])


# -------------------------
# Delete endpoint
# -------------------------

@app.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a task",
)
def delete_task(task_id: int):
    if not db.delete_task(task_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Task {task_id} not found"},
        )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )
