"""A secured API: sign up, log in, log out, and guarded routes.

Assignment A4. The whole security model is the trust triangle:

    1. the client sends credentials to Supabase (through this API)
    2. Supabase verifies them and signs a JWT access token
    3. the client sends that token back as "Authorization: Bearer <jwt>"
    4. this server asks Supabase whether the token is genuine

Step 4 is the only part that decides whether a door opens.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from supabase import AuthApiError, AuthError, AuthRetryableError

from auth import supabase_client
from auth.security import get_current_user, require_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the Supabase client once, at startup. If the .env values are
    # missing this raises here -- before the server starts accepting
    # traffic -- rather than on somebody's first login.
    supabase_client.get_client()
    url, _ = supabase_client.get_settings()
    print(f"Server running and connected to Supabase at {url}")
    yield


# Swagger UI groups the routes under these headings, in this order.
TAGS = [
    {
        "name": "auth",
        "description": (
            "Sign up, log in, log out. Supabase owns the accounts and "
            "the passwords; this API never stores either."
        ),
    },
    {
        "name": "public",
        "description": "Open routes. No token, no header, no questions.",
    },
    {
        "name": "protected",
        "description": (
            "Locked routes. Log in, click **Authorize** above, paste "
            "the access_token, and these answer 200 instead of 401."
        ),
    },
]

app = FastAPI(
    title="Auth API",
    version="4.0",
    description=(
        "A secured API using **Supabase Auth** as its Identity "
        "Provider.\n\n"
        "**How to use this page**\n\n"
        "1. `POST /auth/signup` with an email and a password.\n"
        "2. `POST /auth/login` with the same pair, and copy the "
        "`access_token` out of the response.\n"
        "3. Click the **Authorize** padlock at the top right and "
        "paste that token.\n"
        "4. Every route with a padlock now answers 200. Click "
        "Authorize -> Logout, or change one character of the "
        "token, and they answer 401 again.\n\n"
        "Errors always come back as `{\"error\": ...}`."
    ),
    openapi_tags=TAGS,
    lifespan=lifespan,
)


# Reusable Swagger response documentation. Written once here rather than
# spelled out on every route, so the documented failures cannot drift
# apart from each other.
UNAUTHORIZED_RESPONSE = {
    "description": "Missing, malformed, or invalid/expired token",
    "content": {
        "application/json": {
            "example": {"error": "Invalid or expired token"}
        }
    },
}
BAD_REQUEST_RESPONSE = {
    "description": "Missing email or password",
    "content": {
        "application/json": {"example": {"error": "Email is required"}}
    },
}
UNAVAILABLE_RESPONSE = {
    "description": "Supabase could not be reached",
    "content": {
        "application/json": {
            "example": {"error": "Could not reach the identity provider"}
        }
    },
}


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


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    # FastAPI's own body is {"detail": ...}. The guard in auth/security.py
    # raises HTTPException, so without this one handler a 401 from the
    # guard would answer in a different shape from every other error the
    # API returns.
    return error(exc.status_code, str(exc.detail))


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
    """Pick the handful of Supabase user fields that are safe to send.

    Supabase's user object carries more than a client needs. Returning a
    deliberate subset means a future Supabase field cannot accidentally
    start leaking through this API.
    """
    return {
        "id": str(user.id),
        "email": user.email,
        "created_at": str(user.created_at),
    }


def public_fields(user: dict) -> dict:
    """Trim the dict the guard built down to what a client may see.

    The guard keeps the caller's access token on the user dict so routes
    like logout can act on their session. That token must never travel
    back out in a response body.
    """
    return {key: user[key] for key in ("id", "email", "created_at")}


# -------------------------
# Swagger UI
# -------------------------
#
# FastAPI serves Swagger UI at /docs for free. The padlocks come from
# the HTTPBearer dependency in auth/security.py: because the guard is a
# dependency, the routes it protects are the routes marked locked here,
# and the two can never drift apart.

def custom_openapi() -> dict:
    """The generated schema, minus a status code this API never sends.

    FastAPI documents a 422 on any route with a request body. This API
    turns validation failures into 400s (see the handler above), so a
    documented 422 would be a promise the code does not keep. Stripping
    it here rather than hand-writing the schema keeps the docs
    generated-from-code, which is the reason they stay honest.
    """
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        tags=app.openapi_tags,
        routes=app.routes,
    )

    for operations in schema["paths"].values():
        for operation in operations.values():
            operation.get("responses", {}).pop("422", None)

    app.openapi_schema = schema

    return schema


app.openapi = custom_openapi


# -------------------------
# General endpoints
# -------------------------

@app.get("/", tags=["public"], summary="Describe the API")
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
    tags=["auth"],
    summary="Create a new user account",
    responses={
        201: {
            "description": "Account created",
            "content": {
                "application/json": {
                    "example": {
                        "message": "User created",
                        "user": {
                            "id": "8f14e45f-ceea-467a-9f8c-1b2c3d4e5f60",
                            "email": "test@example.com",
                            "created_at": "2026-08-18 10:00:00+00:00",
                        },
                    }
                }
            },
        },
        400: BAD_REQUEST_RESPONSE,
        503: UNAVAILABLE_RESPONSE,
    },
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


@app.post(
    "/auth/login",
    tags=["auth"],
    summary="Authenticate and receive a JWT",
    responses={
        200: {
            "description": "Signed in",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIs...",
                        "refresh_token": "v1v2h3k4...",
                        "token_type": "bearer",
                        "expires_in": 3600,
                        "user": {
                            "id": "8f14e45f-ceea-467a-9f8c-1b2c3d4e5f60",
                            "email": "test@example.com",
                            "created_at": "2026-08-18 10:00:00+00:00",
                        },
                    }
                }
            },
        },
        400: BAD_REQUEST_RESPONSE,
        401: {
            "description": "Wrong email or password",
            "content": {
                "application/json": {
                    "example": {"error": "Invalid login credentials"}
                }
            },
        },
        503: UNAVAILABLE_RESPONSE,
    },
)
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


# -------------------------
# Public endpoint
# -------------------------

@app.get(
    "/public/info",
    tags=["public"],
    summary="Read public, open data",
)
def public_info():
    """The lobby. No token, no header, no questions asked."""
    return {"message": "Welcome stranger! This info is public."}


# -------------------------
# Protected endpoints
# -------------------------
#
# Every route below is protected by exactly one thing: the
# get_current_user dependency. None of them contain a line of auth code
# of their own -- adding a locked door is now one argument long.

@app.get(
    "/protected/profile",
    tags=["protected"],
    summary="Read private profile data",
    responses={401: UNAUTHORIZED_RESPONSE, 503: UNAVAILABLE_RESPONSE},
)
def protected_profile(user: dict = Depends(get_current_user)):
    return {"user": public_fields(user)}


@app.get(
    "/protected/dashboard",
    tags=["protected"],
    summary="Read the user's dashboard",
    responses={401: UNAUTHORIZED_RESPONSE, 503: UNAVAILABLE_RESPONSE},
)
def protected_dashboard(user: dict = Depends(get_current_user)):
    """The proof that the guard is reusable.

    This route was added with no new auth code: one dependency, and it
    already rejects a missing token, a malformed header, and a tampered
    token exactly the way /protected/profile does.
    """
    return {
        "message": f"Welcome back, {user['email']}!",
        "user_id": user["id"],
        "items": ["Your private dashboard is empty for now."],
    }


@app.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    tags=["auth"],
    summary="End the user's session",
    responses={
        204: {"description": "Signed out, or already signed out"},
        401: UNAUTHORIZED_RESPONSE,
        502: {
            "description": "Supabase refused the logout; the session may still be alive",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Logout was refused by the identity provider"
                    }
                }
            },
        },
        503: UNAVAILABLE_RESPONSE,
    },
)
def logout(user: dict = Depends(get_current_user)):
    """Revoke the caller's session at Supabase.

    Worth being honest about what this can and cannot do. It revokes the
    refresh token, so the session cannot be extended and the client is
    logged out for good. It cannot make the *access* token stop
    verifying: a JWT is stateless and stays valid until it expires,
    which is exactly why access tokens are short-lived (an hour here).

    Two things this route does *not* do, both deliberate:

    It does not call auth.sign_out(). That method reads the token from
    the client's own stored session, so using it would mean calling
    set_session() first -- and one shared Supabase client serves every
    request here, so one caller's logout could land on another caller's
    session. Reading the SDK source settles what is lost by avoiding it:
    sign_out() is a wrapper that ends up at
    admin.sign_out(access_token, scope), the identical HTTP call this
    makes. The name "admin" is about the namespace, not the credential:
    that endpoint authenticates as the *user*, with the user's own JWT,
    which is why the SDK's own docstring describes passing "a user's JWT
    through to admin.sign_out". The service_role key is needed for admin
    calls that act on *other* users, and none happen here.

    It does not report success it did not get. Supabase refusing the
    logout used to be swallowed, which meant this route could answer 204
    while the session was still alive at the identity provider -- the
    worst kind of bug, because every test and every user sees "logged
    out" and believes it.
    """
    try:
        supabase_client.get_client().auth.admin.sign_out(
            user["access_token"], "global"
        )
    except AuthRetryableError:
        return error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not reach the identity provider",
        )
    except AuthApiError as exc:
        # The one refusal that really is success: the session is already
        # gone. Logging out twice should be a no-op, not an error.
        already_gone = exc.code == "session_not_found" or exc.status == 404

        if not already_gone:
            # Anything else means the session may still be alive. Say so
            # instead of returning 204 over the top of it.
            return error(
                status.HTTP_502_BAD_GATEWAY,
                "Logout was refused by the identity provider",
            )
    except AuthError:
        return error(
            status.HTTP_502_BAD_GATEWAY,
            "Logout was refused by the identity provider",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------
# Extras
# -------------------------

@app.get(
    "/protected/admin",
    tags=["protected"],
    summary="A route only an admin may use",
    responses={
        401: UNAUTHORIZED_RESPONSE,
        403: {
            "description": "Logged in, but not an admin",
            "content": {
                "application/json": {"example": {"error": "Admin role required"}}
            },
        },
        503: UNAVAILABLE_RESPONSE,
    },
)
def protected_admin(user: dict = Depends(require_admin)):
    """The difference between 401 and 403, as a route.

    An ordinary logged-in user reaching this gets 403, not 401. The
    distinction is not pedantry: 401 means "I do not know who you are",
    so a client that receives it will sensibly try logging in again --
    forever, if the real answer was "I know exactly who you are, and you
    still may not."

    Grant the role from the Supabase dashboard or a server-side call:
    app_metadata = {"role": "admin"}. It deliberately is not readable
    from user_metadata, which users can write themselves -- a role
    trusted from there is a role anyone can grant themselves at signup.
    """
    return {
        "message": f"Welcome, admin {user['email']}.",
        "secret": "The admin-only data lives here.",
    }


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


@app.post(
    "/auth/refresh",
    tags=["auth"],
    summary="Exchange a refresh token for a new access token",
    responses={
        200: {"description": "A fresh access token"},
        400: {
            "description": "No refresh token supplied",
            "content": {
                "application/json": {
                    "example": {"error": "Refresh token is required"}
                }
            },
        },
        401: {
            "description": "The refresh token is invalid or already used",
            "content": {
                "application/json": {
                    "example": {"error": "Invalid or expired refresh token"}
                }
            },
        },
        503: UNAVAILABLE_RESPONSE,
    },
)
def refresh(body: RefreshRequest):
    """Get a new access token without asking for the password again.

    This is the other half of why access tokens expire after an hour.
    Short-lived access tokens limit the damage of a leaked one -- a
    stolen token is useless within the hour, and nothing can revoke it
    before then because it is stateless. The refresh token, which *can*
    be revoked, is what keeps the user from having to log in hourly.
    """
    token = (body.refresh_token or "").strip()

    if not token:
        return error(
            status.HTTP_400_BAD_REQUEST, "Refresh token is required"
        )

    try:
        result = supabase_client.get_client().auth.refresh_session(token)
    except AuthRetryableError:
        return error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Could not reach the identity provider",
        )
    except (AuthApiError, AuthError):
        return error(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token"
        )

    session = result.session if result else None

    if session is None:
        return error(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token"
        )

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "expires_in": session.expires_in,
    }
