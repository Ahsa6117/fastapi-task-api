"""AI-generated routes from prompt v2. Quarantined — not the submission."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Task API (AI v2)", lifespan=lifespan)


class Task(BaseModel):
    id: int
    title: str
    done: bool


class TaskCreate(BaseModel):
    title: str


class TaskUpdate(BaseModel):
    title: str | None = None
    done: bool | None = None


def error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return error(status.HTTP_400_BAD_REQUEST, "Invalid request body")


@app.get("/tasks", response_model=list[Task])
def list_tasks():
    return db.list_tasks()


@app.get("/tasks/{task_id}", response_model=Task)
def get_task(task_id: int):
    task = db.get_task(task_id)
    if task is None:
        return error(status.HTTP_404_NOT_FOUND, f"Task {task_id} not found")
    return task


@app.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate):
    title = payload.title.strip()
    if not title:
        return error(
            status.HTTP_400_BAD_REQUEST, "Title is required and cannot be empty"
        )
    return db.create_task(title)


@app.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: int, payload: TaskUpdate):
    task = db.get_task(task_id)
    if task is None:
        return error(status.HTTP_404_NOT_FOUND, f"Task {task_id} not found")

    if payload.title is None and payload.done is None:
        return error(status.HTTP_400_BAD_REQUEST, "Provide title, done, or both")

    title = task["title"]
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            return error(status.HTTP_400_BAD_REQUEST, "Title cannot be empty")

    done = task["done"] if payload.done is None else payload.done

    return db.update_task(task_id, title, done)


@app.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_task(task_id: int):
    if not db.delete_task(task_id):
        return error(status.HTTP_404_NOT_FOUND, f"Task {task_id} not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
