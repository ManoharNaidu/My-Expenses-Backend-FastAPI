from fastapi import APIRouter, Depends, Query

from routes.auth import get_current_user
from schemas.ai import ReviewStagingRequest
from services.langgraph_workflows import run_budget_coach_graph, run_review_staging_graph

router = APIRouter(prefix="/ai")


@router.post("/review-staging")
def review_staging(data: ReviewStagingRequest, user=Depends(get_current_user)):
    return run_review_staging_graph(user_id=user["id"], staging_ids=data.staging_ids)


@router.get("/budget-coach")
def budget_coach(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    user=Depends(get_current_user),
):
    return run_budget_coach_graph(user_id=user["id"], year=year, month=month)
