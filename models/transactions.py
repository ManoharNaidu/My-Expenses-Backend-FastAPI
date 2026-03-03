from pydantic import BaseModel, Field
from datetime import date
from typing import Optional
from datetime import datetime

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
    description: str = Field(..., max_length=_DESC_MAX)
    type: str = Field(..., max_length=50)
    category: str = Field(..., max_length=_CAT_MAX)


class TransactionConfirm(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    final_type: str = Field(..., max_length=50)
    final_category: str = Field(..., max_length=_CAT_MAX)
