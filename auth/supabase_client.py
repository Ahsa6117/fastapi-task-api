"""The one place this project talks to Supabase.

Supabase is the Identity Provider: it stores the user accounts, hashes
the passwords, and signs the JSON Web Tokens. This project never does
any of those three things itself -- writing your own password hashing or
token signing is how security incidents happen.

Everything here needs two secrets, read from a git-ignored .env:

    SUPABASE_URL   the Project URL from Project Settings -> API
    SUPABASE_KEY   the *anon* (public) key from the same page

The anon key is the one that is safe to hand to an application. The
service_role key on that same dashboard page bypasses every security
rule Supabase has, so it must never appear in this project, in .env, or
in any log line.
"""

import os

from dotenv import load_dotenv
from supabase import Client, create_client

# Read .env into the environment. Real environment variables win, so a
# container or CI job can override these without editing any file.
load_dotenv()

# Cached so that every request reuses one client instead of building a
# fresh one (and a fresh connection pool) each time.
_client: Client | None = None


def get_settings() -> tuple[str, str]:
    """Return (url, anon key), failing loudly if either is missing.

    Crashing at startup with a readable message beats booting a server
    that looks healthy and then 500s on the first login attempt.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    missing = [
        name
        for name, value in (("SUPABASE_URL", url), ("SUPABASE_KEY", key))
        if not value
    ]

    if missing:
        raise RuntimeError(
            f"{' and '.join(missing)} not set. Copy .env.example to .env "
            "(cp .env.example .env) and paste the Project URL and anon "
            "key from your Supabase dashboard -> Project Settings -> API."
        )

    return url, key


def get_client() -> Client:
    """Return the shared Supabase client, building it on first use."""
    global _client

    if _client is None:
        url, key = get_settings()
        _client = create_client(url, key)

    return _client
