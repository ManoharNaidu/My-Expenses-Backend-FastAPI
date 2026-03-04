from pydantic import BaseModel, Field
from typing import List, Optional

_PASSWORD_MIN = 8
_PASSWORD_MAX = 128
_NAME_MIN = 1
_NAME_MAX = 200
_CURRENCY_MAX = 10

class UpdateNameRequest(BaseModel):
    name: str = Field(..., min_length=_NAME_MIN, max_length=_NAME_MAX)


class UpdatePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=_PASSWORD_MAX)
    new_password: str = Field(..., min_length=_PASSWORD_MIN, max_length=_PASSWORD_MAX)


class UpdateCurrencyRequest(BaseModel):
    currency: str = Field(..., min_length=1, max_length=_CURRENCY_MAX)


class UpdateCategoriesRequest(BaseModel):
    categories: List[dict[str, Optional[str]]] = Field(..., max_length=200)


class AppLockUpdateRequest(BaseModel):
    enabled: bool
    use_biometric: bool = False
    pin_hash: Optional[str] = Field(default=None, max_length=255)



