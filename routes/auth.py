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
        "is_onboarded": False,
        "currency": (data.currency or "AUD").upper(),
    }).execute()

    token = create_access_token({"sub": user_id})
    return {"access_token": token}

@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest):
    try:
        res = supabase.from_("users").select("*").eq("email", data.email).single().execute()
        user = res.data
    except Exception:
        user = None

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
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        try:
            user = supabase.from_("users").select("*").eq("id", user_id).single().execute().data
        except Exception:
            user = None

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/me")
def me(user=Depends(get_current_user)):
    response = {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "is_onboarded": user["is_onboarded"],
        "currency": user.get("currency"),
    }

    if user["is_onboarded"]:
        rows = supabase.table("user_categories") \
            .select("type", "category") \
            .eq("user_id", user["id"]) \
            .execute().data
        response["categories"] = {
            "income_categories": [r["category"] for r in rows if r["type"] == "income"],
            "expense_categories": [r["category"] for r in rows if r["type"] == "expense"]
        }

    return response
