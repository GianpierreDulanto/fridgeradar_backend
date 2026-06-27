import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import TokenBlacklist

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    to_encode.update({"exp": expire, "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days)
    to_encode.update({"exp": expire, "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# RF-AUT-004: server-side JWT revocation
# ---------------------------------------------------------------------------
def is_token_revoked(jti: str, db: Session) -> bool:
    """True if the jti has been revoked AND its expiry is still in the future."""
    from sqlalchemy import and_

    if not jti:
        return False
    return (
        db.query(TokenBlacklist)
        .filter(and_(TokenBlacklist.jti == jti, TokenBlacklist.expires_at > datetime.now(timezone.utc)))
        .first()
        is not None
    )


def revoke_token(
    jti: str,
    user_id: str,
    expires_at: datetime,
    db: Session,
    reason: str = "logout",
) -> TokenBlacklist:
    """Idempotently insert a jti into the blacklist. Safe to call twice."""
    import uuid as _uuid

    entry = (
        db.query(TokenBlacklist)
        .filter(TokenBlacklist.jti == jti)
        .first()
    )
    if entry:
        return entry
    entry = TokenBlacklist(
        jti=_uuid.UUID(jti) if isinstance(jti, str) else jti,
        user_id=_uuid.UUID(user_id) if isinstance(user_id, str) else user_id,
        expires_at=expires_at,
        reason=reason,
    )
    db.add(entry)
    db.commit()
    return entry


def cleanup_revoked_tokens(db: Session) -> int:
    """Drop blacklist rows whose token would have expired anyway.

    Returns the number of rows deleted. Safe to call from a scheduled job.
    """
    from sqlalchemy import delete

    result = db.execute(
        delete(TokenBlacklist).where(TokenBlacklist.expires_at <= datetime.now(timezone.utc))
    )
    db.commit()
    return result.rowcount
