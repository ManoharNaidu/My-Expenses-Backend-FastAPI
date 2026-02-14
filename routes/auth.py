from fastapi import APIRouter, HTTPException, Depends
from uuid import uuid4
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.database import supabase
from core.security import hash_password, verify_password, create_access_token
from core.config import JWT_SECRET, JWT_ALGORITHM
from schemas.auth import RegisterRequest, LoginRequest, AuthResponse

router = APIRouter(prefix="/auth")
security = HTTPBearer()

@router.post("/register", response_model=AuthResponse)
def register(data: RegisterRequest):
    existing = supabase.from_("users").select("id").eq("email", data.email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid4())
    supabase.from_("users").insert({
        "id": user_id,
        "name": data.name,
        "email": data.email,
        "password_hash": hash_password(data.password),
        "is_onboarded": False
    }).execute()

    token = create_access_token({"sub": user_id})
    return {"access_token": token}

@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest):
    res = supabase.from_("users").select("*").eq("email", data.email).single().execute()
    user = res.data

    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user["id"]})
    return {"access_token": token}

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        user_id = payload["sub"]
        user = supabase.from_("users").select("*").eq("id", user_id).single().execute().data
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/me")
def me(user=Depends(get_current_user)):
    response = {
        "id": user["id"],
        "name": user["name"],
        "is_onboarded": user["is_onboarded"],
    }

    if user["is_onboarded"]:
        rows = supabase.table("user_categories") \
            .select("income_category, expense_category") \
            .eq("user_id", user["id"]) \
            .execute().data
        response["categories"] = {
            "income_categories": [r["income_category"] for r in rows],
            "expense_categories": [r["expense_category"] for r in rows]
        }

    return response
