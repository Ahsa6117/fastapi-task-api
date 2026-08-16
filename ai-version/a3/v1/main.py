"""
FastAPI to-do API. All persistence logic lives in db.py - this module
only defines routes, validates input, and shapes HTTP responses.
"""

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

import db
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class TaskIn(BaseModel):
    title: str
    done: bool = False


class Task(BaseModel):
    id: int
    title: str
    done: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Task API", lifespan=lifespan)


@app.get("/tasks", response_model=list[Task])
def read_tasks():
    return db.list_tasks()


@app.get("/tasks/{task_id}", response_model=Task)
def read_task(task_id: int):
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/tasks", response_model=Task, status_code=201)
def create_task(task: TaskIn):
    return db.create_task(task.title, task.done)


@app.put("/tasks/{task_id}", response_model=Task)
def update_task(task_id: int, task: TaskIn):
    updated = db.update_task(task_id, task.title, task.done)
    if updated is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return updated


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    deleted = db.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return None
