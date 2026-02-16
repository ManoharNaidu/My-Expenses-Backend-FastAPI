from pydantic import BaseModel
from datetime import date
from typing import Optional
from datetime import datetime

class TransactionIn(BaseModel):
    date: datetime
    description: str
    amount: float
    transaction_type: str
    balance: Optional[float]


class TransactionCreate(BaseModel):
    amount: float
    date: datetime
    description: str
    type: str
    category: str


class TransactionConfirm(BaseModel):
    id: str
    final_type: str
    final_category: str
