from __future__ import annotations
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field

class DebtBase(BaseModel):
    creditor: str
    total_amount: float
    category: str = "Personal"
    due_date: Optional[date] = Field(None, description="Expected payoff date or next installment date")
    notes: Optional[str] = None

class DebtCreate(DebtBase):
    pass

class DebtUpdate(BaseModel):
    creditor: Optional[str] = None
    total_amount: Optional[float] = None
    current_balance: Optional[float] = None
    category: Optional[str] = None
    due_date: Optional[date] = None
    status: Optional[str] = None  # e.g., 'ACTIVE', 'PAID'
    notes: Optional[str] = None

class RepaymentCreate(BaseModel):
    amount: float
    repayment_date: date = Field(default_factory=date.today)
    transaction_id: Optional[str] = None
    notes: Optional[str] = None
