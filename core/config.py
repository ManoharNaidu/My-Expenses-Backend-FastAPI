import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str, min_length: Optional[int] = None) -> str:
    value = os.getenv(name)
    if not value or not value.strip():
        raise RuntimeError(f"Missing or empty required env: {name}")
    if min_length is not None and len(value) < min_length:
        raise RuntimeError(f"Env {name} must be at least {min_length} characters")
    return value.strip()


def _require_port(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        port = int(raw)
    except ValueError:
        raise RuntimeError(f"Env {name} must be an integer, got: {raw!r}")
    if not (1 <= port <= 65535):
        raise RuntimeError(f"Env {name} must be a valid port (1–65535), got: {port}")
    return port


JWT_SECRET = _require_env("JWT_SECRET", min_length=32)
SUPABASE_URL = _require_env("SUPABASE_URL")
SUPABASE_KEY = _require_env("SUPABASE_KEY")

JWT_ALGORITHM = "HS256"

# Access token: short-lived. Configurable via env so deployments can tune it.
# Default 60 min. The old value was 1 year — changed as part of security hardening.
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

CORS_ORIGINS_RAW = os.getenv("CORS_ORIGINS", "*").strip()
CORS_ORIGINS = (
    [o.strip() for o in CORS_ORIGINS_RAW.split(",") if o.strip()]
    if CORS_ORIGINS_RAW != "*"
    else ["*"]
)

_cors_allow_credentials_raw = os.getenv("CORS_ALLOW_CREDENTIALS", "false").strip().lower()
CORS_ALLOW_CREDENTIALS = _cors_allow_credentials_raw in {"1", "true", "yes", "on"}

if CORS_ORIGINS == ["*"] and CORS_ALLOW_CREDENTIALS:
    CORS_ALLOW_CREDENTIALS = False

PORT = int(os.getenv("PORT", "8000"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))  # 10 MB

# Brevo v3 API
BREVO_API_KEY = _require_env("BREVO_API_KEY", min_length=20)
BREVO_SENDER_EMAIL = _require_env("SENDER_EMAIL")
BREVO_SENDER_NAME = os.getenv("SENDER_NAME", "My Expense App")
