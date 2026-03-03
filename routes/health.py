from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.database import supabase

router = APIRouter()


@router.get("/")
def read_root():
    """Welcome + API version for client compatibility checks (e.g. Android)."""
    return {
        "message": "Welcome to the Expense Automation API!",
        "api_version": "1",
    }


@router.get("/health")
def health():
    """Liveness: API is up."""
    return {"status": "ok"}


@router.get("/health/ready")
def ready():
    """Readiness: API and dependencies (e.g. DB) are reachable."""
    try:
        supabase.from_("users").select("id").limit(1).execute()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "Database unreachable"},
        )
    return {"status": "ok"}

