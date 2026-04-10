from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.database import supabase
from routes.auth import get_current_user

router = APIRouter()


class CategoryBudgetSchema(BaseModel):
    category: str = Field(..., min_length=1, max_length=100)
    monthly_limit: float = Field(..., ge=0, le=1e12)
    alerts_enabled: bool = True
    enabled: bool = True


@router.get('/category-budgets')
def get_category_budgets(user=Depends(get_current_user)):
    rows = (
        supabase.table('category_budgets')
        .select('*')
        .eq('user_id', user['id'])
        .order('category')
        .execute()
        .data
    )
    return rows


@router.put('/category-budgets')
def replace_category_budgets(
    payload: list[CategoryBudgetSchema],
    user=Depends(get_current_user),
):
    user_id = user['id']

    # Replace-all contract: delete existing then insert current payload.
    supabase.table('category_budgets').delete().eq('user_id', user_id).execute()

    if not payload:
        return {'message': 'Category budgets updated', 'count': 0}

    rows = [
        {
            'user_id': user_id,
            'category': item.category.strip(),
            'monthly_limit': item.monthly_limit,
            'alerts_enabled': item.alerts_enabled,
            'enabled': item.enabled,
        }
        for item in payload
        if item.category.strip()
    ]

    if not rows:
        return {'message': 'Category budgets updated', 'count': 0}

    inserted = supabase.table('category_budgets').insert(rows).execute().data
    return {
        'message': 'Category budgets updated',
        'count': len(inserted or []),
        'budgets': inserted or [],
    }


@router.delete('/category-budgets/{category}')
def delete_category_budget(category: str, user=Depends(get_current_user)):
    cleaned = category.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail='Category is required')

    supabase.table('category_budgets').delete().eq('user_id', user['id']).eq(
        'category', cleaned
    ).execute()
    return {'message': 'Category budget deleted'}
