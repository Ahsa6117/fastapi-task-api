"""Every checkpoint in Assignment A4, run in one go.

This is the curl sequence from the assignment turned into a script, so
the whole flow can be re-proved after any change instead of re-typing
six commands and pasting a token by hand:

    signup -> login -> valid token 200 -> tampered token 401

It talks to the real Supabase project named in .env, because that is the
only way to prove the guard works: a fake token is only convincing when
something real is doing the rejecting.

It signs up a throwaway address each run (smoke-<random>@example.com),
so it never touches an account you care about. Supabase keeps those
users; delete them from Authentication -> Users when they pile up.

Run with:  python -m auth.smoke_test
"""

import os
import uuid

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from auth.main import app

load_dotenv()

# Supabase enforces a minimum password length (6 by default).
EMAIL = f"smoke-{uuid.uuid4().hex[:12]}@{os.getenv('SMOKE_EMAIL_DOMAIN', 'example.com')}"
PASSWORD = "password123"

checks_run = 0


def check(label: str, actual, expected) -> None:
    global checks_run
    assert actual == expected, f"{label}: expected {expected!r}, got {actual!r}"
    checks_run += 1
    print(f"  ok  {label}")


def tamper(token: str) -> str:
    """Change one character of the payload, leaving the shape intact.

    The result is still a well-formed three-part JWT -- it just no longer
    matches its own signature. That is the forgery the guard has to
    catch, and a truncated or garbage string would not test the same
    thing.
    """
    head, payload, signature = token.split(".")
    swapped = "B" if payload[5] != "B" else "C"

    return f"{head}.{payload[:5]}{swapped}{payload[6:]}.{signature}"


with TestClient(app) as client:
    print("Public routes (Stage 2)")
    response = client.get("/public/info")
    check("GET /public/info -> 200", response.status_code, 200)
    check(
        "the lobby is open to strangers",
        response.json()["message"],
        "Welcome stranger! This info is public.",
    )

    print("Validation (Stage 1)")
    check(
        "signup with no password -> 400",
        client.post("/auth/signup", json={"email": EMAIL}).status_code,
        400,
    )
    check(
        "login with no email -> 400",
        client.post("/auth/login", json={"password": PASSWORD}).status_code,
        400,
    )

    print("Sign up (Stage 1)")
    response = client.post(
        "/auth/signup", json={"email": EMAIL, "password": PASSWORD}
    )
    check("POST /auth/signup -> 201", response.status_code, 201)
    check("the account is the one asked for", response.json()["user"]["email"], EMAIL)
    check("no token is handed out at signup", "access_token" in response.json(), False)

    print("Log in (Stage 1)")
    response = client.post(
        "/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    check("POST /auth/login -> 200", response.status_code, 200)

    body = response.json()
    token = body["access_token"]
    check("an access token comes back", isinstance(token, str) and len(token) > 20, True)
    refresh_token = body["refresh_token"]
    check("a refresh token comes back", isinstance(refresh_token, str), True)
    check("a JWT has three parts", len(token.split(".")), 3)

    check(
        "the wrong password -> 401",
        client.post(
            "/auth/login", json={"email": EMAIL, "password": "not-it-at-all"}
        ).status_code,
        401,
    )

    print("The guard (Stages 3 and 4)")
    good = {"Authorization": f"Bearer {token}"}

    for route in ("/protected/profile", "/protected/dashboard"):
        check(f"{route} with no header -> 401", client.get(route).status_code, 401)
        check(
            f"{route} with no scheme -> 401",
            client.get(route, headers={"Authorization": token}).status_code,
            401,
        )
        check(
            f"{route} with a tampered token -> 401",
            client.get(
                route, headers={"Authorization": f"Bearer {tamper(token)}"}
            ).status_code,
            401,
        )
        check(f"{route} with a real token -> 200", client.get(route, headers=good).status_code, 200)

    response = client.get("/protected/profile", headers=good)
    check("the profile is the logged-in user", response.json()["user"]["email"], EMAIL)
    check(
        "the access token is not echoed back",
        "access_token" in response.json()["user"],
        False,
    )

    print("Refresh (extras)")
    # Proven *before* logout, so that the same call failing afterwards
    # means something. A check that only ever fails is not evidence.
    response = client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    check("POST /auth/refresh -> 200", response.status_code, 200)

    fresh = response.json()
    check("a new access token comes back", fresh["access_token"] != token, True)
    check(
        "the new token opens a locked door",
        client.get(
            "/protected/profile",
            headers={"Authorization": f"Bearer {fresh['access_token']}"},
        ).status_code,
        200,
    )

    print("Log out (Stage 4)")
    check(
        "POST /auth/logout with no token -> 401",
        client.post("/auth/logout").status_code,
        401,
    )
    check(
        "POST /auth/logout -> 204",
        client.post("/auth/logout", headers=good).status_code,
        204,
    )

    # The check that actually proves the logout happened.
    #
    # A 204 from this API only says our own route reached its last line.
    # It could have reached it over a failure Supabase reported -- which
    # is exactly the bug this exists to catch. So ask Supabase itself:
    # the session's refresh token must now be dead. Nothing this server
    # believes can fake that answer.
    check(
        "the revoked refresh token is refused -> 401",
        client.post(
            "/auth/refresh", json={"refresh_token": fresh["refresh_token"]}
        ).status_code,
        401,
    )
    check(
        "the original refresh token is refused too -> 401",
        client.post(
            "/auth/refresh", json={"refresh_token": refresh_token}
        ).status_code,
        401,
    )

    # Not asserted: that the access token stops verifying. It does not.
    # A JWT is stateless and stays valid until it expires -- revoking the
    # refresh token is what ends the session, and claiming otherwise
    # would be the same kind of comfortable lie as a 204 over a failure.

print(f"\nAll {checks_run} checks passed against {os.getenv('SUPABASE_URL')}.")
