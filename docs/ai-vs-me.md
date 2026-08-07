# Stage 6 — AI vs me

The prompt is in [ai-prompt.md](ai-prompt.md). The generated code is in
[`ai-version/`](../ai-version/) and was never merged into the submission —
`main.py` and `db.py` in the project root are hand-built.

**An honest caveat:** the same model wrote both the hand-built version and the
AI version, so this is a weaker rematch than one run against a different
assistant. What makes it worth keeping is that the AI version was generated
from the prompt alone, and the findings below all come from *running* it, not
from reading it.

## Did it run?

Yes, first try. It created `tasks.db`, created the table, seeded exactly three
tasks, and restarting it twice did **not** multiply the seed — it counted rows
first, as the prompt asked. Data survived a restart: a task marked done through
`PUT` was still done after the server was stopped and started.

So the headline feature works. Everything below is about the details the prompt
did not pin down.

## What it did better

**`INSERT ... RETURNING`.** My `create_task` inserts, grabs `cursor.lastrowid`,
and then builds the response dict in Python from values I already had:

```python
cursor = connection.execute("INSERT INTO tasks (title, done) VALUES (?, ?)", (title, 0))
new_id = cursor.lastrowid
return {"id": new_id, "title": title, "done": False}
```

The AI used SQLite's `RETURNING` clause instead, so the insert hands back the
row it actually wrote:

```sql
INSERT INTO tasks (title, done) VALUES (?, ?) RETURNING id, title, done
```

This is genuinely better and I can explain why: my version *assumes* the stored
row matches what I sent. If the schema had a default, a trigger, or a type
conversion that changed a value on the way in, my response would describe a row
that does not exist in the database. `RETURNING` reports what was really
written, in one statement, with no second query. It applies the same way to
`UPDATE`, where it also removes my separate "does this id exist?" lookup.

**`RETURNING` on `UPDATE` replaces a read.** My `update_task` does a `SELECT`
to check for a 404 and then an `UPDATE` — two round trips, and in principle the
row could be deleted between them. The AI's single `UPDATE ... RETURNING`
returns `None` when no row matched, which answers both questions at once.

## What it got wrong or quietly ignored

**1. It changed the error body.** The prompt said "returns 404" and never said
what the JSON should look like, so it reached for FastAPI's `HTTPException`:

```
GET /tasks/999  ->  {"detail": "Task not found"}
```

A1 returns `{"error": "Task 999 not found"}`. Any client checking
`response.error` breaks. This is the most dangerous kind of difference: the
status code is right, so a quick test passes and the bug ships.

**2. Invalid bodies return 422, not 400.** `POST /tasks` with `{}` returned
`422 Unprocessable Content` — FastAPI's default for a validation failure. The
requirement is 400. The prompt did say "a missing title returns 400", and it
still got this wrong, because overriding that default takes a deliberate
exception handler and the model treated pydantic's default as good enough.

**3. `PUT` stopped being a partial update.** It typed the body as a model
requiring both `title` and `done`, so `{"done": true}` — the most common real
request, "mark this task finished" — returned 422 instead of 200. The prompt
said "keep the same behaviour" without describing what that behaviour was, and
"same" turned out to mean nothing on its own.

**4. A whitespace-only title was accepted.** `{"title": "   "}` returned
**201 Created** and wrote a blank-looking task to the database. It never
stripped the string, so `if not task.title` was False. A1 strips first. Prompt
said "empty title"; the AI and I disagreed on what empty means.

**5. The database path is relative.** `DB_PATH = "tasks.db"` resolves against
the *working directory*, not the code. I started the app from a different
folder and it created a brand new, freshly seeded database there — from the
user's point of view, every task they had ever created was gone. My version
uses `Path(__file__).parent / "tasks.db"`, which is the same file no matter
where you launch from. This is the one I would call a real bug rather than a
mismatch, and the prompt never mentioned it because I did not think of it
either.

**6. One shared connection with `check_same_thread=False`.** A defensible
choice, and the AI even commented on why — but it is a trade-off it made
silently on my behalf. FastAPI runs sync endpoints on a thread pool, so several
requests share that one connection concurrently. My version opens a connection
per operation, which is slower and completely uncontended.

**7. No `ORDER BY`.** `SELECT * FROM tasks` returns rows in whatever order
SQLite finds convenient. Today that looks like id order and everything seems
fine; after enough deletes and inserts it may not, and the ordering would drift
with no code change to blame.

## What my prompt forgot to specify

Every single item above traces back to a gap in the prompt, not to the model
being careless:

| The AI decided | Because my prompt never said |
| --- | --- |
| `{"detail": ...}` error bodies | what an error response looks like |
| 422 for invalid bodies | that *all* validation failures must be 400 |
| `PUT` requires every field | that `PUT` is a partial update |
| `"   "` is a valid title | that titles are stripped before validating |
| `tasks.db` relative to the CWD | where the file must live |
| one shared connection | anything about connection handling |
| unordered results | that rows come back ordered by id |

I wrote a prompt describing the **schema** in detail and the **behaviour** in
slogans — "keep the same endpoints", "same behaviour". The schema came back
perfect. The behaviour came back as the model's best guess. "Same as before"
means nothing to something that cannot see the before.

The reason I could find all seven in about ten minutes is that I had already
made all seven decisions myself, by hand, over the previous five stages. I was
not comparing the output against the prompt — I was comparing it against a
version I understood.

## The rematch

Prompt v2 adds the seven points above as explicit requirements, plus "keep all
SQL in a separate module from the route handlers".

**What changed in one sentence:** every one of the seven differences
disappeared — the regenerated version returns `{"error": ...}` bodies, 400 for
invalid input, supports partial `PUT`, rejects whitespace titles, anchors the
database next to the code, and orders by id — and it passes all 20 checks in
`smoke_test.py` unmodified, which the first version could not even be run
against because it had no separate storage module to point the tests at.

It also *kept* the `RETURNING` trick, so the second version is a genuine
improvement on my hand-built code rather than a copy of it. That is the part
worth remembering: the AI was never the bottleneck. My specification was.
