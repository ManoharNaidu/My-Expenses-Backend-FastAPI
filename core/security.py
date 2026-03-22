from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from core.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRE_MINUTES

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hash.encode('utf-8'))
    except ValueError:
        return False

def create_access_token(data: dict):
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
