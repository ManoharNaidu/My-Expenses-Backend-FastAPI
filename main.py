import os
import logging
from fastapi import FastAPI
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routes.auth import router as auth_router
from routes.health import router as health_router
from routes.onboarding import router as onboarding_router
from routes.settings import router as settings_router
from routes.upload import router as upload_router
from routes.transactions import router as transactions_router
from routes.feedback import router as feedback_router

app = FastAPI(title="Expense Automation API")
logger = logging.getLogger(__name__)

GENERIC_ERROR_MESSAGE = "Something unexpected happened. Please try again."

port = os.getenv("PORT", 8000)

# ---------------- CORS Middleware ----------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": message},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"message": "Invalid request data"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled server error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"message": GENERIC_ERROR_MESSAGE},
    )

# ---------------- Register Routers ----------------

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(settings_router)
app.include_router(upload_router)
app.include_router(transactions_router)
app.include_router(feedback_router)
