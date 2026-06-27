from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.ingestion_service.db.problem_models import Instructor, PlatformStudent


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_instructor_api_key() -> str:
    return secrets.token_urlsafe(32)


JWT_AUDIENCE = "bstu_platform_instructor"
JWT_AUDIENCE_STUDENT = "bstu_platform_student"
JWT_AUDIENCE_PLATFORM_ADMIN = "bstu_platform_admin"
_BCRYPT_ROUNDS = 12


def _sha256_digest(plaintext: str) -> bytes:
    return hashlib.sha256(plaintext.encode("utf-8")).digest()


def hash_password(plaintext: str) -> str:
    """SHA256→bcrypt: без лимита 72 байта у сыро UTF-8, совместимо с любыми длинными паролями API."""
    d = _sha256_digest(plaintext)
    return bcrypt.hashpw(d, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("ascii")


def verify_password(plaintext: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    raw = password_hash.encode("utf-8")
    try:
        if bcrypt.checkpw(_sha256_digest(plaintext), raw):
            return True
    except ValueError:
        pass
    # Совместимость со старыми хешами passlib/bcrypt только по сыруой UTF-8 (до 72 байт)
    try:
        pw = plaintext.encode("utf-8")[:72]
        return bcrypt.checkpw(pw, raw)
    except ValueError:
        return False


def encode_instructor_jwt(instructor_id: uuid.UUID, secret: str, expire_hours: int) -> str:
    """Access token преподавателя (передаётся как Authorization Bearer)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(instructor_id),
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=expire_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_instructor_id_from_jwt(token: str, secret: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE,
        )
        sub = payload.get("sub")
        if sub is None:
            return None
        return uuid.UUID(str(sub))
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


def encode_student_jwt(student_id: uuid.UUID, secret: str, expire_hours: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(student_id),
        "aud": JWT_AUDIENCE_STUDENT,
        "iat": now,
        "exp": now + timedelta(hours=expire_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def encode_platform_admin_jwt(admin_id: uuid.UUID, secret: str, expire_hours: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(admin_id),
        "aud": JWT_AUDIENCE_PLATFORM_ADMIN,
        "iat": now,
        "exp": now + timedelta(hours=expire_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_platform_admin_id_from_jwt(token: str, secret: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE_PLATFORM_ADMIN,
        )
        sub = payload.get("sub")
        if sub is None:
            return None
        return uuid.UUID(str(sub))
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


def decode_student_id_from_jwt(token: str, secret: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE_STUDENT,
        )
        sub = payload.get("sub")
        if sub is None:
            return None
        return uuid.UUID(str(sub))
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


async def instructor_from_bearer(session: AsyncSession, bearer_token: str) -> Instructor | None:
    """
    Распознать Bearer: JWT доступа или legacy API-ключ (SHA256 в api_key_hash).
    """
    from config import get_config

    token = bearer_token.strip()
    cfg = getattr(get_config(), "platform_jwt_secret", None)
    if cfg and token.count(".") == 2:
        uid = decode_instructor_id_from_jwt(token, cfg)
        if uid:
            row = await session.get(Instructor, uid)
            if row is not None:
                return row

    h = hash_api_key(token)
    res = await session.execute(select(Instructor).where(Instructor.api_key_hash == h))
    return res.scalar_one_or_none()


async def student_row_from_jwt(session: AsyncSession, bearer_token: str) -> PlatformStudent | None:
    from config import get_config

    token = bearer_token.strip()
    secret = getattr(get_config(), "platform_jwt_secret", None)
    if not secret or token.count(".") != 2:
        return None
    sid = decode_student_id_from_jwt(token, secret)
    if sid is None:
        return None
    return await session.get(PlatformStudent, sid)
