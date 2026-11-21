
import os
import jwt
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

Role = Literal["customer", "support", "admin"]

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "support-ticket-classifier-v2"
JWT_AUDIENCE = "support-ticket-api"

hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)


class AuthUser(BaseModel):
    user_id: str
    role: Role


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def _secret() -> str:
    value = os.getenv("APP_JWT_SECRET", "")

    if len(value) < 32:
        raise RuntimeError(
            "APP_JWT_SECRET must contain at least 32 characters"
        )

    return value


def issue_token(
    user_id: str,
    role: Role,
    expires_minutes: int = 30
) -> str:

    if role not in {"customer", "support", "admin"}:
        raise ValueError("Invalid role")

    now = datetime.now(timezone.utc)

    payload = {
        "sub": user_id,
        "role": role,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "jti": secrets.token_hex(16)
    }

    return jwt.encode(
        payload,
        _secret(),
        algorithm=JWT_ALGORITHM
    )


def decode_token(token: str) -> AuthUser:
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={
                "require": [
                    "sub", "role", "iss", "aud",
                    "iat", "nbf", "exp", "jti"
                ]
            }
        )

        if not isinstance(payload["sub"], str) or not payload["sub"]:
            raise ValueError("Invalid subject")

        if payload["role"] not in {"customer", "support", "admin"}:
            raise ValueError("Invalid role")

        return AuthUser(
            user_id=payload["sub"],
            role=payload["role"]
        )

    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"}
        )


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer)
) -> AuthUser:

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return decode_token(credentials.credentials)


def require_roles(*roles: Role):
    def authorize(user: AuthUser = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="Insufficient permissions"
            )
        return user

    return authorize
