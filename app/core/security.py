"""Password hashing and JWT helpers for web sessions."""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed hash of a value no user can match, used to equalize timing on
# login when the supplied email does not exist. Running bcrypt against this
# dummy hash consumes roughly the same CPU as a real comparison, so the
# response time does not leak whether an account exists.
_DUMMY_PASSWORD_HASH = pwd_context.hash("dummy-password-for-timing-equalization")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def dummy_verify_password() -> None:
    """Burn a bcrypt verify against a dummy hash to equalize login timing."""
    pwd_context.verify("dummy-password-for-timing-equalization", _DUMMY_PASSWORD_HASH)


def create_access_token(user_id: int) -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expires_at}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None

    subject = payload.get("sub")
    if subject is None:
        return None

    try:
        return int(subject)
    except (TypeError, ValueError):
        return None
