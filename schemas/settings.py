from pydantic import BaseModel
from typing import List, Optional


class UpdateNameRequest(BaseModel):
    name: str


class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UpdateCategoriesRequest(BaseModel):
    categories: List[dict[str, Optional[str]]]

