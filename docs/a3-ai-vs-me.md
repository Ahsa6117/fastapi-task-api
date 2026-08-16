# AI vs me — Assignment A3 (containerize the stack)

I built Stages 0–5 by hand first. Only then did I write a prompt, from memory,
and hand the same job to an AI. That order matters: everything below is a code
review, and I could only review it because I had already made every one of these
decisions myself.

The generated code is quarantined in [`ai-version/a3/`](../ai-version/a3/) and
was never merged. The submission is the hand-built stack in the repo root.

**Fairness caveat, same as the A2 round:** the AI was given the prompt and
nothing else — it was explicitly blocked from reading my hand-built files — but
it is the same model family that helped me write mine. This is a softer test
than handing it to a different assistant.

Both prompts are in [a3-ai-prompt.md](a3-ai-prompt.md).

**How much of this is verified.** Every finding below comes from reading the
generated code line by line and from parsing all three `compose.yaml` files to
compare them mechanically. Docker is not yet installed on this machine, so
neither AI stack has been *run* — the "it works first try" claims are about
structure, not observed behaviour, and they are marked as such. The runtime
comparison lands once the stack is up.

---

## Round 1 — what came back

The headline result: **v1's stack is structurally correct.** The compose file
declares both services, gives Postgres a named volume, defines a `pg_isready`
healthcheck and makes `api` wait on `service_healthy`; the app creates the table,
seeds three tasks only when the count is zero, and does all five CRUD operations
with `%s` placeholders throughout. The container part of the assignment — the
genuinely new part — it got right.

(Not yet run — see the caveat above. Structure reviewed and compose parsed;
runtime behaviour unconfirmed.)

Everything I found is in the parts my prompt described in slogans rather than in
detail. That is the same lesson as the A2 round, arriving in a new costume.

### What it did better than me

Three of these I am adopting the reasoning from, even though I am not merging
the code.

1. **It did not run the app as the Postgres superuser.** Its compose sets
   `POSTGRES_USER: ${POSTGRES_USER}` and its `.env.example` uses `taskapi`. Mine
   connects as `postgres`, the superuser, because that is what the assignment's
   example command does and I never questioned it. An app that only ever needs
   `SELECT/INSERT/UPDATE/DELETE` on one table should not hold an account that
   can drop every database on the server. Its healthcheck is parameterized to
   match (`pg_isready -U ${POSTGRES_USER}`); mine hardcodes `postgres`.

2. **`DELETE ... RETURNING id` instead of checking `rowcount`.** It asks the
   database to hand back what it deleted, so "was there a row?" is answered by
   the presence of a returned row rather than by a driver-level counter. Same
   result here, but it is the same statement doing both jobs.

3. **The Dockerfile copies `main.py db.py`, not `COPY . .`** — an allowlist
   instead of a denylist. Mine copies everything and relies on `.dockerignore`
   to subtract the secrets. Its version cannot leak a file it was never told to
   include. Mine is more convenient as the project grows; its version is safer.

### What it got wrong

1. **Error bodies are `{"detail": "Task not found"}`, not `{"error": ...}`.**
   The status code is right, so a careless test passes and every existing client
   breaks. This is the *exact* mistake from the A2 round, in a prompt I wrote
   after having already been burned by it.

2. **Invalid bodies return 422, not 400.** No `RequestValidationError` handler,
   so FastAPI's default leaks through.

3. **`PUT` is not a partial update.** It types the body as `TaskIn`, which
   requires `title`, so `{"done": true}` — the single most common update a to-do
   app makes — returns 422.

4. **`POST /tasks` accepts a `done` field.** `TaskIn` has `done: bool = False`,
   so a client can create a task that is already finished. Small, but it is an
   API surface I never agreed to.

5. **A whitespace-only title returns 201 and stores a blank task.** It never
   strips or checks the string. Also the same finding as the A2 round.

6. **One `DATABASE_URL` hardcoded to host `db`.** This is the interesting one,
   and it is a design flaw rather than a slip. Its `.env` contains
   `postgresql://taskapi:changeme@db:5432/taskapi`, and compose passes that
   variable straight through. `db` is only a valid hostname *inside* the compose
   network — so running the app directly on your machine, or pointing `psql` at
   it, or running the test suite, requires editing `.env` first and remembering
   to edit it back. My version keeps `.env` pointing at `localhost` and has
   compose *override* `DATABASE_URL` with the `db` host, so both ways of running
   work from the same untouched file.

7. **It wrote a real `.env` file, unprompted.** I asked for `.env.example`; it
   produced both, with a working password in the committed-looking one. The
   value is a placeholder so nothing leaked, and it did add `.env` to the
   gitignore — but a tool that creates secret files on its own initiative is a
   habit worth noticing before it does it in a repo where the password is real.

8. **`DATABASE_URL = os.environ["DATABASE_URL"]` at import time.** If the
   variable is missing you get a bare `KeyError` from an import statement, not a
   message telling you to copy `.env.example`. And because it is captured at
   import, nothing can point the module at a different database afterwards —
   which is precisely what my `smoke_test.py` needs to do to run against a
   throwaway `tasks_test` database.

9. **No connection retry in the app.** It leans entirely on the compose
   healthcheck. That works under compose and fails the moment you run the app
   outside it against a database that is still booting.

10. **No `.dockerignore`**, and **the `db` service publishes no port**, so
    `psql` or a GUI client on the host cannot reach the database at all.

### What my prompt forgot

Every single one of items 1–5 traces back to one phrase I wrote:

> five of them, behaving exactly as they do now

"As they do now" is meaningless to something that cannot see "now." I specified
the *schema* precisely (`serial`, `text`, `boolean`, seed-only-if-empty) and got
it back perfect. I specified the *Docker* setup precisely (named volume, service
names, one command) and got it back perfect. I specified *behaviour* in a
slogan, and got back the model's reasonable defaults — which are FastAPI's
defaults, not mine.

Items 6, 8, and 9 I did not think to specify at all, because after five stages
of building this by hand they had stopped feeling like decisions. I *knew* the
app has to retry the connection; I had written that loop an hour earlier. It
never occurred to me to say it out loud.

That is the whole shape of the lesson: the prompt is a specification, and a
specification is only as complete as your memory of which choices were choices.

---

## Round 2 — the rematch

Prompt v2 is v1 plus one paragraph spelling out the exact response behaviour,
one on the `db` hostname, one on startup readiness, and one on `.dockerignore`.

**In one sentence: every behavioural difference disappeared.** v2 returns
`{"error": ...}` everywhere, 400 for invalid bodies, a genuinely partial `PUT`
that merges against the existing row, a bare 204, and a `TaskCreate` model that
accepts only `title` and strips it. It has the `wait_for_database` retry loop,
the `.dockerignore`, and it kept the two things v1 did better than me — the
non-superuser account and `RETURNING`.

Three things survived the rematch, and they are more interesting than the fixes:

- **It regressed on something v1 got right.** v1 used the modern `lifespan`
  context manager for startup. v2 used `@app.on_event("startup")`, which FastAPI
  has deprecated. Loading the prompt with behavioural requirements pushed
  attention elsewhere, and a detail that was fine when unspecified got worse.
  Nothing in my longer prompt caused this, and nothing in it prevented it.

- **It scattered redundant `conn.commit()` calls** through `db.py`, including
  two inside `init_db()`. psycopg's `with connect(...)` already commits on a
  clean exit, so they are noise — but in `init_db` they are worse than noise:
  they break the create-then-seed sequence into separate transactions, so a
  crash between them can leave a table created and unseeded. My version keeps
  the whole of startup in one transaction precisely so that cannot happen. I
  never told it that, because "wrap startup in a transaction" was not on my list
  of things I remembered deciding.

- **`DATABASE_URL` is still captured at import time**, so v2 is still not
  testable the way `smoke_test.py` needs.

### One difference where I am not sure I am the right one

Writing checks against my own version turned up a case neither prompt covered.
For `PUT /tasks/999` with an **empty body** — two things wrong at once — the two
versions disagree:

| | My version | AI v2 |
| --- | --- | --- |
| checks first | does the task exist? | is the body empty? |
| result | **404** Task not found | **400** At least one of title or done is required |

Mine looks the row up before validating, so "unknown id" wins. v2 validates the
body before touching the database, so "empty body" wins. Both are defensible —
404-first says *the thing you addressed does not exist, nothing else matters*;
400-first says *this request was malformed before I even looked*. v2's order is
also one fewer database round-trip on a request that was always going to fail.

I kept mine, because it is the order A1 and A2 already had and the contract is
the thing I have been protecting for three assignments. But I only *discovered*
this was a decision because writing a test forced me to predict the answer and I
guessed wrong about my own code. Neither prompt specified it, so the AI was free
to pick — and it picked the cheaper one.

The pattern across both rounds: the AI's output is exactly as good as the
specification, the specification is only as good as your memory of your own
decisions, and **fixing one class of problem does not hold the others still.**
A longer prompt is not a monotonic improvement — it is a different prompt, and
it needs reviewing again from scratch.

Which is the actual takeaway. Not "AI writes bad code" — v2 is good code, and
two of its ideas are better than mine. The takeaway is that I found all of this
in about twenty minutes, and every single finding came from having built the
thing by hand first. I was never checking the output against the prompt. I was
checking it against a version I understood.
