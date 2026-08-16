# The prompts I gave the AI (Assignment A3)

Written from memory after building Stages 0–5 by hand, without looking back at
the assignment brief. That is the point of the exercise: the prompt is a
specification, and what I forgot to say is the finding.

---

## Prompt v1

> I have a FastAPI to-do API in Python. Right now it stores its tasks in a
> SQLite file. Move it to PostgreSQL running in Docker, and make the whole
> thing start with one command.
>
> **Database access**
> - Use `psycopg` (version 3) as the driver. No ORM.
> - Keep every line of SQL in one module, `db.py`. The routes in `main.py`
>   must not contain SQL.
> - Use parameterized queries (`%s` placeholders) for anything that comes from
>   a request. Never build SQL with f-strings.
>
> **Table and seed**
> - A table called `tasks` with `id` (serial primary key), `title` (text, not
>   null), and `done` (boolean, default false).
> - Create the table on startup if it does not exist.
> - Insert three example tasks, but only if the table is empty — restarting
>   the app must not add them a second time.
>
> **Endpoints** — five of them, behaving exactly as they do now:
> `GET /tasks`, `GET /tasks/{id}`, `POST /tasks`, `PUT /tasks/{id}`,
> `DELETE /tasks/{id}`.
>
> **Secrets**
> - The connection string comes from a `DATABASE_URL` environment variable,
>   loaded from a `.env` file. The password must not appear in any committed
>   file. Add `.env` to `.gitignore` and commit a `.env.example` with
>   placeholder values.
>
> **Docker**
> - A `Dockerfile` for the app.
> - A `compose.yaml` with two services: `api` (built from the Dockerfile) and
>   `db` (the official `postgres` image).
> - Give the database a named volume so the tasks survive
>   `docker compose down` followed by `docker compose up`.
> - `docker compose up` must be the only command needed.
>
> Give me every file.

---

## Prompt v2 (the rematch)

Same as v1, with these paragraphs added — each one is a thing v1 left to the
model's imagination and got wrong:

> **Exact response behaviour.** "Same as now" is not enough, so here it is
> spelled out:
> - Every error body is `{"error": "<message>"}`. Not FastAPI's default
>   `{"detail": ...}`.
> - An invalid or malformed request body returns **400**, not FastAPI's
>   default 422. Override the `RequestValidationError` handler to do this.
> - `POST /tasks` takes `{"title": "..."}` only. Strip the title; if it is
>   missing or whitespace-only, return 400. Success returns **201** and the
>   created task including the id the database assigned.
> - `PUT /tasks/{id}` is a **partial** update: the body may contain `title`,
>   `done`, or both, and omitted fields keep their current value. A body with
>   neither returns 400. An unknown id returns 404. Success returns 200.
> - `DELETE /tasks/{id}` returns **204 with a completely empty body**, and 404
>   for an unknown id.
> - `GET /tasks` always returns rows in a defined order — `ORDER BY id`.
> - Task JSON is exactly `{"id": int, "title": str, "done": bool}`. `done` is a
>   real JSON boolean.
>
> **Starting up against a container that is not ready.** `depends_on` waits for
> the db *container*, not for Postgres inside it, which needs several more
> seconds before it accepts connections. Handle this properly: give the `db`
> service a `pg_isready` healthcheck and make `api` use
> `depends_on: {db: {condition: service_healthy}}`, **and** retry the first
> connection in the app so it also works outside compose.
>
> **Inside the compose network the database host is `db`, not `localhost`.**
> A container's `localhost` is itself. The `api` service's `DATABASE_URL` must
> use the service name.
>
> **No secrets in `compose.yaml` either.** Read the password from `.env` with
> `${POSTGRES_PASSWORD}` substitution rather than typing it into the file.
>
> **Add a `.dockerignore`** that excludes `.env`, `.git`, `.venv`, and
> `__pycache__`, so the secret is never baked into the image.
