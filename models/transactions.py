from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

_DESC_MAX = 2000
_CAT_MAX = 100
_AMOUNT_MIN = -1e12
_AMOUNT_MAX = 1e12

class TransactionIn(BaseModel):
    date: datetime
    description: str = Field(..., max_length=_DESC_MAX)
    amount: float = Field(..., ge=_AMOUNT_MIN, le=_AMOUNT_MAX)
    transaction_type: str
    balance: Optional[float] = None


class TransactionCreate(BaseModel):
    amount: float = Field(..., ge=_AMOUNT_MIN, le=_AMOUNT_MAX)
    date: datetime
    description: Optional[str] = Field(default=None, max_length=_DESC_MAX)
    notes: Optional[str] = Field(default=None, max_length=_DESC_MAX)
    type: str = Field(..., max_length=50)
    category: str = Field(..., max_length=_CAT_MAX)
    repeat_monthly: bool = False
    recurring_id: Optional[str] = Field(default=None, max_length=64)


class RecurringTransactionCreate(BaseModel):
    amount: float = Field(..., ge=_AMOUNT_MIN, le=_AMOUNT_MAX)
    type: str = Field(..., max_length=50)
    category: str = Field(..., max_length=_CAT_MAX)
    description: Optional[str] = Field(default=None, max_length=_DESC_MAX)
    start_date: datetime
    day_of_month: int = Field(..., ge=1, le=28)
    end_date: Optional[datetime] = None
    is_active: bool = True


class BudgetGoalUpdate(BaseModel):
    monthly_limit: float = Field(..., ge=0, le=_AMOUNT_MAX)
    alerts_enabled: bool = True


class RecurringTransactionToggle(BaseModel):
    is_active: bool


class TransactionConfirm(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    final_type: str = Field(..., max_length=50)
    final_category: str = Field(..., max_length=_CAT_MAX)
