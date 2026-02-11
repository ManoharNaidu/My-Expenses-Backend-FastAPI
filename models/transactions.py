from pydantic import BaseModel
from datetime import date
from typing import Optional


class TransactionIn(BaseModel):
    date: date
    description: str
    amount: float
    transaction_type: str
    balance: Optional[float]


class TransactionCreate(BaseModel):
    amount: float
    date: date
    original_date: date
    description: str
    type: str
    category: str


class TransactionConfirm(BaseModel):
    id: str
    final_type: str
    final_category: str
