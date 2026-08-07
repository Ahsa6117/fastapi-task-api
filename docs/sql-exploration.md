# Stage 4 — Exploring the database by hand

These queries were run directly against `tasks.db` (DB Browser for SQLite's
"Execute SQL" tab, or any SQLite client) while the API server was still
running. Nothing was restarted between the queries and the API calls below.

## The queries

```sql
SELECT * FROM tasks;                 -- list every task
SELECT * FROM tasks WHERE done = 1;  -- only completed tasks
SELECT COUNT(*) FROM tasks;          -- how many tasks are there?
UPDATE tasks SET done = 1 WHERE id = 2;
DELETE FROM tasks WHERE done = 1;    -- delete all completed tasks
```

## What came back

| Query | Result |
| ----- | ------ |
| `SELECT * FROM tasks;` | 5 rows: the 3 seeded tasks plus "Buy milk" and "Write README" |
| `SELECT * FROM tasks WHERE done = 1;` | 0 rows — nothing was completed yet |
| `SELECT COUNT(*) FROM tasks;` | `5` |
| `UPDATE tasks SET done = 1 WHERE id = 2;` | 1 row changed |
| `DELETE FROM tasks WHERE done = 1;` | 1 row deleted |

## The part that matters

After `UPDATE tasks SET done = 1 WHERE id = 2`, calling `GET /tasks/2` on the
already-running server returned:

```json
{ "id": 2, "title": "Build CRUD API", "done": true }
```

Then after `DELETE FROM tasks WHERE done = 1`, task 2 was gone from
`GET /tasks` as well — again with no restart.

The API never had a copy of the data to keep in sync. It reads `tasks.db`
on every request, and the SQL client writes to that same file, so there is
exactly one source of truth. This is the difference from Assignment 1: back
then the list lived inside the running process, and nothing outside that
process could see or change it.

## A note on `WHERE`

`UPDATE tasks SET done = 1;` with no `WHERE` clause would have marked *every*
task completed, and `DELETE FROM tasks;` would empty the table. A missing
`WHERE` is the classic way to lose a table's worth of data — the endpoints in
this project always pass an id as a `?` parameter for exactly that reason.
