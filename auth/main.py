"""A secured API: sign up, log in, log out, and guarded routes.

Assignment A4. The whole security model is the trust triangle:

    1. the client sends credentials to Supabase (through this API)
    2. Supabase verifies them and signs a JWT access token
    3. the client sends that token back as "Authorization: Bearer <jwt>"
    4. this server asks Supabase whether the token is genuine

Step 4 is the only part that decides whether a door opens.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from supabase import AuthApiError, AuthError, AuthRetryableError

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


# -------------------------
# Data models
# -------------------------

class Credentials(BaseModel):
    """An email/password pair.

    Both fields are optional *to pydantic* on purpose. If they were
    required, a request missing one would be rejected by FastAPI with a
    422 before any of this code ran, and the assignment asks for a 400
    with our own JSON error. Making them optional here lets the route
    do the validating and answer in one consistent shape.
    """

    email: str | None = None
    password: str | None = None


# -------------------------
# Error handling
# -------------------------

def error(status_code: int, message: str) -> JSONResponse:
    """Every failure in this API answers with the same JSON shape."""
    return JSONResponse(status_code=status_code, content={"error": message})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    # Body that is not even JSON, or is JSON of the wrong type. FastAPI
    # would send 422; the assignment's contract is 400.
    return error(status.HTTP_400_BAD_REQUEST, "Invalid request body")


def require_credentials(body: Credentials) -> JSONResponse | None:
    """Return a 400 response if either field is missing or blank.

    The server never trusts the client: an empty password is not a
    Supabase problem to discover, it is a bad request to reject here.
    """
    if not (body.email or "").strip():
        return error(status.HTTP_400_BAD_REQUEST, "Email is required")

    if not (body.password or "").strip():
        return error(status.HTTP_400_BAD_REQUEST, "Password is required")

    return None


def safe_user(user) -> dict:
    """Pick the handful of user fields that are safe to send back.

    Supabase's user object carries more than a client needs. Returning a
    deliberate subset means a future Supabase field cannot accidentally
    start leaking through this API.
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "created_at": str(user.created_at),
    }


# -------------------------
# General endpoints
# -------------------------

@app.get("/", summary="Describe the API")
def read_root():
    return {
        "name": "Auth API",
        "version": "4.0",
        "identity_provider": "Supabase Auth",
        "docs": "/docs",
    }


# -------------------------
# Open auth endpoints
# -------------------------

@app.post(
    "/auth/signup",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
def signup(body: Credentials):
    """Register a user with Supabase.

    This project never sees a password hash and never stores a password.
    The credentials are forwarded to Supabase, which does the hashing
    and owns the account from then on.
    """
    invalid = require_credentials(body)

    if invalid is not None:
        return invalid

    try:
        result = supabase_client.get_client().auth.sign_up(
            {"email": body.email, "password": body.password}
        )
    except AuthRetryableError:
        return error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not reach the identity provider",
        )
    except (AuthApiError, AuthError) as exc:
        # Supabase rejected the signup: address already registered, a
        # password below the minimum length, a malformed email.
        return error(status.HTTP_400_BAD_REQUEST, str(exc))

    if result.user is None:
        return error(status.HTTP_400_BAD_REQUEST, "Sign up failed")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "message": "User created",
            "user": safe_user(result.user),
        },
    )


@app.post("/auth/login", summary="Authenticate and receive a JWT")
def login(body: Credentials):
    """Exchange credentials for an access token.

    The access token is the JWT the client puts in the Authorization
    header on every later request. The refresh token is the longer-lived
    one used to get a new access token when this one expires (Supabase
    expires access tokens after an hour).
    """
    invalid = require_credentials(body)

    if invalid is not None:
        return invalid

    try:
        result = supabase_client.get_client().auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except AuthRetryableError:
        return error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not reach the identity provider",
        )
    except (AuthApiError, AuthError):
        # Deliberately one flat message. Saying "no such user" versus
        # "wrong password" would tell an attacker which addresses are
        # registered.
        return error(
            status.HTTP_401_UNAUTHORIZED, "Invalid login credentials"
        )

    session = result.session

    if session is None:
        return error(
            status.HTTP_401_UNAUTHORIZED, "Invalid login credentials"
        )

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "expires_in": session.expires_in,
        "user": safe_user(result.user),
    }
