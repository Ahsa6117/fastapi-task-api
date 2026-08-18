"""The guard: one reusable token check, applied to every locked door.

Stage 3 verified the token inside the profile route. That does not
scale, and it is not safe: the check would have to be pasted into every
protected route, and the first one somebody forgets is an unguarded
door that nothing about the code makes obvious.

So the check lives here once, as a FastAPI dependency. FastAPI's
Depends() is this framework's middleware for a route: the function runs
before the handler, can stop the request early, and injects its result
into the handler. A route body only ever runs once the caller is a
verified user -- and that user arrives as an argument.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import AuthApiError, AuthError, AuthRetryableError

from auth import supabase_client

# auto_error=False matters. Left at its default, HTTPBearer answers a
# missing header itself, with a 403 and FastAPI's own body -- neither
# the status code nor the JSON shape this API promises. Turning it off
# lets the header arrive as None so the checks below own every failure.
bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Paste the access_token returned by POST /auth/login.",
)


def unauthorized(message: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail=message)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Verify the bearer token and return the user behind it.

    Any route that depends on this is protected. Any route that does not
    is public. There is no third state, and no way to half-apply it.
    """
    if credentials is None:
        # No Authorization header, or one that is not a bearer header.
        # HTTPBearer already rejects a wrong scheme and an empty token.
        raise unauthorized("Access token required")

    token = (credentials.credentials or "").strip()

    if not token:
        raise unauthorized("Access token required")

    try:
        result = supabase_client.get_client().auth.get_user(token)
    except AuthRetryableError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not reach the identity provider",
        )
    except (AuthApiError, AuthError):
        raise unauthorized("Invalid or expired token")

    # Checked as well as the exception: an SDK that answers with an
    # empty user instead of raising must not be read as "logged in".
    if result is None or result.user is None:
        raise unauthorized("Invalid or expired token")

    user = result.user

    return {
        "id": str(user.id),
        "email": user.email,
        "created_at": str(user.created_at),
        # Kept so a route like logout can act on the caller's own
        # session without asking them to send the token twice.
        "access_token": token,
        # Supabase puts custom claims here. Empty for an ordinary user.
        "app_metadata": dict(user.app_metadata or {}),
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Authorization, not authentication -- the 401 vs 403 difference.

    get_current_user answers "who are you?". This answers "and may you?"
    A caller who reaches here has already proved who they are, so
    refusing them is a 403 ("I know you, and no"), never a 401 ("I don't
    know you"). Sending 401 here would tell an ordinary logged-in user
    their perfectly good token was bad, and they would try logging in
    again forever.

    The role is read from app_metadata because Supabase lets only the
    server set that. user_metadata is writable by the user themselves,
    so trusting a role from there would let anyone promote themselves to
    admin at signup.
    """
    if user["app_metadata"].get("role") != "admin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    return user
