import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.auth import router as auth_router
from routes.health import router as health_router
from routes.onboarding import router as onboarding_router
from routes.settings import router as settings_router
from routes.upload import router as upload_router
from routes.transactions import router as transactions_router

app = FastAPI(title="Expense Automation API")

port = os.getenv("PORT", 8000)

# ---------------- CORS Middleware ----------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- Register Routers ----------------

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(settings_router)
app.include_router(upload_router)
app.include_router(transactions_router)
