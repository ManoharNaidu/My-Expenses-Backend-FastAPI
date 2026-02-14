from fastapi import APIRouter, HTTPException, Depends

from core.database import supabase
from routes.auth import get_current_user
from schemas.onboarding import OnboardingRequest

router = APIRouter()


@router.post("/auth/onboarding")
def onboard_user(data: OnboardingRequest, user=Depends(get_current_user)):
    if user["is_onboarded"]:
        raise HTTPException(status_code=200, detail="User already onboarded")

    supabase.from_("users") \
        .update({
            "is_onboarded": True,
        }) \
        .eq("id", user["id"]) \
        .execute()

    # Insert selected categories into user_categories
    category_records = [
        {"user_id": user["id"], "income_category": pair.get("income_category"), "expense_category": pair.get("expense_category")}
        for pair in data.categories
    ]

    if category_records:
        supabase.table("user_categories").insert(category_records).execute()

    return {
        "message": "Onboarding complete",
        "categories_added": len(data.categories),
    }

