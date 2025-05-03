from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
import re


class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    full_name: str

    @validator("phone")
    def validate_phone(cls, v):
        if v is None:
            return v
        if not re.match(r"^\+\d{11,15}$", v):
            raise ValueError(
                "Invalid phone number format. Use international format like +79123456789"
            )
        return v

    @validator("email", "phone")
    def validate_contact_info(cls, v, values, **kwargs):
        field_name = kwargs.get("field", {}).name if kwargs.get("field") else None

        if field_name == "email" and v is None and "phone" not in values:
            raise ValueError("Either email or phone must be provided")
        if field_name == "phone" and v is None and "email" not in values:
            raise ValueError("Either email or phone must be provided")
        return v


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    google_id: Optional[str] = None
    yandex_id: Optional[str] = None


class UserLogin(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: str

    @validator("email", "phone")
    def validate_contact_info(cls, v, values, **kwargs):
        field_name = kwargs.get("field", {}).name if kwargs.get("field") else None

        if field_name == "email" and v is None and "phone" not in values:
            raise ValueError("Either email or phone must be provided")
        if field_name == "phone" and v is None and "email" not in values:
            raise ValueError("Either email or phone must be provided")
        return v


class User(UserBase):
    id: int
    is_active: bool
    google_id: Optional[str] = None
    yandex_id: Optional[str] = None
    phone: Optional[str] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: int
    email: Optional[str] = None
    phone: Optional[str] = None
