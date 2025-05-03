from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from decimal import Decimal
from typing import Optional


class AccountType(str, Enum):
    CURRENT = "current"
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"


class AccountBase(BaseModel):
    account_type: AccountType
    credit_limit: Optional[Decimal] = Field(default=100000, decimal_places=2, ge=0)


class AccountCreate(AccountBase):
    pass


class Account(AccountBase):
    id: int
    user_id: int
    balance: Decimal = Field(decimal_places=2)
    account_number: str
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionBase(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)
    description: str | None = None


class TransactionCreate(TransactionBase):
    transaction_type: TransactionType


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: Decimal = Field(gt=0, decimal_places=2)
    description: str | None = None


class InterUserTransferCreate(BaseModel):
    from_account_id: int
    to_user_id: int
    to_account_id: int
    amount: Decimal = Field(gt=0, decimal_places=2)
    description: str | None = None


class Transaction(TransactionBase):
    id: int
    account_id: int
    transaction_type: TransactionType
    created_at: datetime

    class Config:
        from_attributes = True
