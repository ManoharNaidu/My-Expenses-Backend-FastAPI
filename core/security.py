from datetime import datetime, timedelta, timezone
import bcrypt

import jwt

from core.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET

# ---------------------------------------------------------------------------
# Password hashing — bcrypt directly (passlib removed)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Returns a bcrypt hash of the given password string."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verifies a plain password against its bcrypt hash. Safe against ValueErrors."""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False



# ---------------------------------------------------------------------------
# JWT — PyJWT (python-jose removed)
# ---------------------------------------------------------------------------

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid or expired tokens."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
