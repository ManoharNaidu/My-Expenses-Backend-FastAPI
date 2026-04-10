from fastapi import APIRouter, HTTPException, Depends

from core.database import supabase
from routes.auth import get_current_user
from schemas.onboarding import OnboardingRequest

router = APIRouter()


@router.post("/auth/onboarding")
def onboard_user(data: OnboardingRequest, user=Depends(get_current_user)):
    if user["is_onboarded"]:
        raise HTTPException(status_code=409, detail="User already onboarded")

    update_payload = {
        "is_onboarded": True,
    }
    if data.persona is not None and data.persona.strip():
        update_payload["persona"] = data.persona.strip()

    supabase.from_("users") \
        .update(update_payload) \
        .eq("id", user["id"]) \
        .execute()

    # Insert selected categories into user_categories
    category_records = []

    for pair in data.categories:
        if pair.get("income_category"):
            category_records.append({
                "user_id": user["id"],
                "type": "income",
                "category": pair.get("income_category")
            })

        if pair.get("expense_category"):
            category_records.append({
                "user_id": user["id"],
                "type": "expense",
                "category": pair.get("expense_category")
            })

    if category_records:
        supabase.table("user_categories").insert(category_records).execute()

    return {
        "message": "Onboarding complete",
        "categories_added": len(data.categories),
    }


