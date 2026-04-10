from fastapi import APIRouter, Depends, HTTPException
from core.database import supabase
from models.debts import DebtCreate, DebtUpdate, RepaymentCreate
from routes.auth import get_current_user

router = APIRouter()

@router.get("/debts")
def get_debts(user=Depends(get_current_user)):
    """List all debts for the current user."""
    return (
        supabase.table("debts")
        .select("*")
        .eq("user_id", user["id"])
        .order("created_at", desc=True)
        .execute()
        .data
    )

@router.post("/debts")
def create_debt(data: DebtCreate, user=Depends(get_current_user)):
    """Create a new debt entry."""
    record = {
        "user_id": user["id"],
        "creditor": data.creditor,
        "total_amount": data.total_amount,
        "current_balance": data.total_amount,
        "category": data.category,
        "due_date": data.due_date.isoformat() if data.due_date else None,
        "notes": data.notes,
        "status": "ACTIVE",
    }
    result = supabase.table("debts").insert(record).execute()
    return result.data[0] if result.data else None

@router.put("/debts/{debt_id}")
def update_debt(debt_id: str, data: DebtUpdate, user=Depends(get_current_user)):
    """Update debt details."""
    update_dict = data.dict(exclude_unset=True)
    if "due_date" in update_dict and update_dict["due_date"]:
        update_dict["due_date"] = update_dict["due_date"].isoformat()
        
    if not update_dict:
        raise HTTPException(status_code=400, detail="No update data provided")

    result = (
        supabase.table("debts")
        .update(update_dict)
        .eq("id", debt_id)
        .eq("user_id", user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Debt not found or permission denied")
    return result.data[0]

@router.get("/debts/{debt_id}/repayments")
def get_repayments(debt_id: str, user=Depends(get_current_user)):
    """List all repayments for a specific debt."""
    return (
        supabase.table("debt_repayments")
        .select("*")
        .eq("debt_id", debt_id)
        .eq("user_id", user["id"])
        .order("date", desc=True)
        .execute()
        .data
    )

@router.post("/debts/{debt_id}/repayments")
def create_repayment(debt_id: str, data: RepaymentCreate, user=Depends(get_current_user)):
    """Record a repayment and update debt balance."""
    # 1. Verify debt ownership and get current balance
    debt_result = supabase.table("debts").select("*").eq("id", debt_id).eq("user_id", user["id"]).execute()
    if not debt_result.data:
        raise HTTPException(status_code=404, detail="Debt not found")
    
    debt = debt_result.data[0]
    old_balance = float(debt["current_balance"])
    new_balance = max(0.0, old_balance - data.amount)
    
    # 2. Add repayment record
    repayment_record = {
        "debt_id": debt_id,
        "user_id": user["id"],
        "amount": data.amount,
        "date": data.repayment_date.isoformat(),
        "transaction_id": data.transaction_id,
        "notes": data.notes,
    }
    supabase.table("debt_repayments").insert(repayment_record).execute()
    
    # 3. Update debt balance
    update_data = {"current_balance": new_balance}
    if new_balance <= 0:
        update_data["status"] = "PAID"
        
    updated_debt = supabase.table("debts").update(update_data).eq("id", debt_id).execute()
    
    return {
        "message": "Repayment recorded",
        "debt": updated_debt.data[0] if updated_debt.data else None
    }
