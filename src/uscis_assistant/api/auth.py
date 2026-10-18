"""Role tokens. One secret token per role, compared in constant time.

This is MVP-grade access control: a token identifies a ROLE, not a person, and an applicant
case is reachable by anyone holding the applicant token and the case id (128 random bits).
Real accounts are the next step before a public launch.
"""

import hmac
from collections.abc import Callable

from fastapi import HTTPException, Request

from uscis_assistant.config import Settings
from uscis_assistant.storage.store import ActorRole

MIN_TOKEN_LENGTH = 24


class InsecureConfiguration(Exception):
    pass


def validate_tokens(settings: Settings) -> tuple[str, str]:
    applicant, lawyer = settings.applicant_token, settings.lawyer_token
    if applicant is None or lawyer is None:
        raise InsecureConfiguration("APPLICANT_TOKEN and LAWYER_TOKEN must both be set")
    a, b = applicant.get_secret_value(), lawyer.get_secret_value()
    if len(a) < MIN_TOKEN_LENGTH or len(b) < MIN_TOKEN_LENGTH:
        raise InsecureConfiguration(f"tokens must be at least {MIN_TOKEN_LENGTH} characters")
    if hmac.compare_digest(a.encode(), b.encode()):
        raise InsecureConfiguration("the two tokens must differ")
    return a, b


def role_from_header(header: str | None, applicant: str, lawyer: str) -> ActorRole | None:
    if not header or not header.startswith("Bearer "):
        return None
    given = header.removeprefix("Bearer ").strip().encode()
    # Compare against both tokens every time so timing does not reveal which one matched.
    is_applicant = hmac.compare_digest(given, applicant.encode())
    is_lawyer = hmac.compare_digest(given, lawyer.encode())
    if is_lawyer:
        return ActorRole.LAWYER
    if is_applicant:
        return ActorRole.APPLICANT
    return None


def require_roles(*allowed: ActorRole) -> Callable[[Request], ActorRole]:
    """A FastAPI dependency that returns the caller's role if it is one of `allowed`."""

    def dependency(request: Request) -> ActorRole:
        tokens: tuple[str, str] = request.app.state.tokens
        role = role_from_header(request.headers.get("authorization"), *tokens)
        if role is None:
            raise HTTPException(status_code=401, detail="missing or invalid token")
        if role not in allowed:
            raise HTTPException(status_code=403, detail="this role may not do this")
        return role

    return dependency
