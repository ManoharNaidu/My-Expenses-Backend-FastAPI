from fastapi import APIRouter, Depends, HTTPException

from core.database import supabase
from routes.auth import get_current_user
from schemas.feedback import FeedbackCreateRequest

router = APIRouter(prefix="/feedback")


@router.post("")
def create_feedback(data: FeedbackCreateRequest, user=Depends(get_current_user)):
    payload = {
        "user_id": user["id"],
        "description": data.description.strip(),
    }

    result = supabase.table("feedback").insert(payload).execute()
    inserted = result.data[0] if result.data else None

    if not inserted:
        raise HTTPException(status_code=500, detail="Failed to save feedback")

    return {"message": "Feedback submitted", "feedback": inserted}
