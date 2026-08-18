"""A secured API: sign up, log in, log out, and guarded routes.

Assignment A4. The whole security model is the trust triangle:

    1. the client sends credentials to Supabase (through this API)
    2. Supabase verifies them and signs a JWT access token
    3. the client sends that token back as "Authorization: Bearer <jwt>"
    4. this server asks Supabase whether the token is genuine

Step 4 is the only part that decides whether a door opens.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from auth import supabase_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the Supabase client once, at startup. If the .env values are
    # missing this raises here -- before the server starts accepting
    # traffic -- rather than on somebody's first login.
    supabase_client.get_client()
    url, _ = supabase_client.get_settings()
    print(f"Server running and connected to Supabase at {url}")
    yield


app = FastAPI(
    title="Auth API",
    version="4.0",
    description=(
        "A secured API using Supabase Auth as its Identity Provider. "
        "Sign up, log in, log out, and reach protected routes with a "
        "verified bearer token."
    ),
    lifespan=lifespan,
)


@app.get("/", summary="Describe the API")
def read_root():
    return {
        "name": "Auth API",
        "version": "4.0",
        "identity_provider": "Supabase Auth",
        "docs": "/docs",
    }
