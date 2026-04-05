import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from core.config import CORS_ALLOW_CREDENTIALS, CORS_ORIGINS, CORS_ORIGIN_REGEX
from routes.auth import router as auth_router
from routes.ai import router as ai_router
from routes.feedback import router as feedback_router
from routes.health import router as health_router
from routes.onboarding import router as onboarding_router
from routes.settings import router as settings_router
from routes.transactions import router as transactions_router
from routes.upload import router as upload_router

app = FastAPI(title="Expense Automation API")
logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "Something unexpected happened. Please try again."

# ---------------------------------------------------------------------------
# Rate limiting (slowapi)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(status_code=exc.status_code, content={"message": message})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(loc) for loc in e["loc"] if loc != "body"), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"message": "Invalid request data", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"message": GENERIC_ERROR_MESSAGE})


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
API_V1 = "/api/v1"

app.include_router(health_router)
app.include_router(auth_router, prefix=API_V1)
app.include_router(ai_router, prefix=API_V1)
app.include_router(onboarding_router, prefix=API_V1)
app.include_router(settings_router, prefix=API_V1)
app.include_router(upload_router, prefix=API_V1)
app.include_router(transactions_router, prefix=API_V1)
app.include_router(feedback_router, prefix=API_V1)
