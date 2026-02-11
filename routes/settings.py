from fastapi import APIRouter, HTTPException, Depends

from core.database import supabase
from core.security import verify_password, hash_password
from routes.auth import get_current_user
from schemas.settings import UpdateNameRequest, UpdatePasswordRequest, UpdateCategoriesRequest

router = APIRouter(prefix="/settings")


@router.put("/name")
def update_name(data: UpdateNameRequest, user=Depends(get_current_user)):
    supabase.from_("users") \
        .update({"name": data.name}) \
        .eq("id", user["id"]) \
        .execute()

    return {"message": "Name updated"}


@router.put("/password")
def update_password(data: UpdatePasswordRequest, user=Depends(get_current_user)):
    if not verify_password(data.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    supabase.from_("users") \
        .update({"password_hash": hash_password(data.new_password)}) \
        .eq("id", user["id"]) \
        .execute()

    return {"message": "Password updated"}


@router.put("/categories")
def update_categories(data: UpdateCategoriesRequest, user=Depends(get_current_user)):
    # Delete existing categories
    supabase.table("user_categories") \
        .delete() \
        .eq("user_id", user["id"]) \
        .execute()

    # Insert new categories
    category_records = [
        {"user_id": user["id"], "category": category}
        for category in data.categories
    ]

    if category_records:
        supabase.table("user_categories").insert(category_records).execute()

    return {"message": "Categories updated", "categories": data.categories}

