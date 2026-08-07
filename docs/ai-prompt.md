# Stage 6 — the prompt

## Version 1

Written from memory, before looking back at `db.py` or the assignment brief.

> I have a FastAPI to-do API that keeps its tasks in a Python list in memory.
> Move the storage to SQLite using Python's built-in `sqlite3` module.
>
> - The database file should be called `tasks.db` and be created automatically
>   if it does not exist.
> - Create a table called `tasks` if it is missing, with columns: `id`
>   (integer, primary key, assigned by the database), `title` (text), and
>   `done` (boolean stored as 0 or 1).
> - Seed three example tasks, but only if the table is empty.
> - Keep the same five endpoints with the same behaviour: `GET /tasks`,
>   `GET /tasks/{id}`, `POST /tasks`, `PUT /tasks/{id}`, `DELETE /tasks/{id}`.
> - A missing or empty title returns 400. An unknown id returns 404. Creating
>   returns 201, deleting returns 204.
> - Use parameterized queries, never string formatting, for anything that
>   comes from a request.
>
> Give me the full file.

## What version 1 left unsaid

Found by running the result and diffing it, not by reading it:

1. **The shape of the error body.** The prompt says "returns 404" but never
   says what the JSON looks like. A1 returns `{"error": "..."}`.
2. **How `done` is serialised.** SQLite stores `0`/`1`. The prompt never says
   the API must return JSON `true`/`false`.
3. **Whether `PUT` is a partial update.** A1 accepts `{"done": true}` on its
   own and leaves the title alone.
4. **What "empty title" means.** A1 strips whitespace, so `"   "` is empty.
5. **The order rows come back in.**
6. **What an empty `PUT` body should do.** A1 returns 400.

## Version 2

Version 1 plus the six points above, stated explicitly:

> ...as above, and additionally:
>
> - Every error response must have the body `{"error": "<message>"}` — not
>   FastAPI's default `{"detail": ...}`. This includes validation failures:
>   a request body that fails validation must return **400**, not FastAPI's
>   default 422.
> - `done` must be returned in JSON as `true`/`false`, never as `0`/`1`,
>   even though SQLite stores it as an integer.
> - `PUT` is a partial update: the body may contain `title`, `done`, or both.
>   Whichever is absent keeps its current value. A body containing neither
>   returns 400.
> - Titles are stripped of surrounding whitespace before validating and
>   storing, so a title of `"   "` counts as empty and returns 400.
> - `GET /tasks` returns rows ordered by `id`.
> - Keep all SQL in a separate module from the route handlers.
