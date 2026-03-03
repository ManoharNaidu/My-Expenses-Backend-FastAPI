from pydantic import BaseModel, EmailStr, Field
from typing import Optional

_PASSWORD_MIN = 8
_PASSWORD_MAX = 128
_NAME_MIN = 1
_NAME_MAX = 200

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=_NAME_MIN, max_length=_NAME_MAX)
    email: EmailStr
    password: str = Field(..., min_length=_PASSWORD_MIN, max_length=_PASSWORD_MAX)
    currency: Optional[str] = Field(None, max_length=10)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=_PASSWORD_MAX)

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
