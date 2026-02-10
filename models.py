from pydantic import BaseModel
from datetime import date
from typing import Optional


class TransactionIn(BaseModel):
    date: date
    description: str
    amount: float
    transaction_type: str
    balance: Optional[float]


class TransactionConfirm(BaseModel):
    id: str
    final_type: str
    final_category: str
