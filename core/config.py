import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


# Required — fail fast at import if missing (production safety)
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
JWT_EXPIRE_MINUTES = 60 * 24 * 365  # 1 year

# CORS: comma-separated origins, or "*" for allow-all (avoid with credentials in prod)
CORS_ORIGINS_RAW = os.getenv("CORS_ORIGINS", "*").strip()
CORS_ORIGINS = (
    [o.strip() for o in CORS_ORIGINS_RAW.split(",") if o.strip()]
    if CORS_ORIGINS_RAW != "*"
    else ["*"]
)

# Browsers reject wildcard origins when credentials are enabled.
# Since this app uses Bearer tokens (Authorization header), credentials are
# usually not required. Keep this configurable for deployments that need it.
_cors_allow_credentials_raw = os.getenv("CORS_ALLOW_CREDENTIALS", "false").strip().lower()
CORS_ALLOW_CREDENTIALS = _cors_allow_credentials_raw in {"1", "true", "yes", "on"}

# Safety guard: don't combine wildcard origin with credentials=true.
if CORS_ORIGINS == ["*"] and CORS_ALLOW_CREDENTIALS:
    CORS_ALLOW_CREDENTIALS = False

# Optional
PORT = int(os.getenv("PORT", "8000"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))  # 10 MB default

# Brevo v3 API (used for email verification and password reset)
BREVO_API_KEY = _require_env("BREVO_API_KEY", min_length=20)
BREVO_SENDER_EMAIL = _require_env("SENDER_EMAIL")
BREVO_SENDER_NAME = os.getenv("SENDER_NAME", "My Expense App")
