from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.auth.oauth import get_current_user
from app.models.user import User
from app.models.banking import Account, Transaction, AccountType, TransactionType
from app.schemas.banking import AccountCreate, Account as AccountSchema
from app.schemas.banking import TransactionCreate, Transaction as TransactionSchema
from app.schemas.banking import TransferCreate, InterUserTransferCreate
from app.schemas.user import User as UserSchema
from app.docs.api_description import BANKING_ENDPOINTS
import uuid
from typing import List
from sqlalchemy import or_

router = APIRouter(prefix="/banking", tags=["banking"])


def generate_account_number():
    return str(uuid.uuid4().int)[:12]


@router.post(
    "/accounts/",
    response_model=AccountSchema,
    status_code=status.HTTP_201_CREATED,
    **BANKING_ENDPOINTS["create_account"],
)
async def create_account(
    account: AccountCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Преобразуем Decimal в float для credit_limit
    credit_limit = float(account.credit_limit) if account.credit_limit else 0.0

    db_account = Account(
        user_id=current_user.id,
        account_type=account.account_type,
        account_number=generate_account_number(),
        credit_limit=credit_limit,
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account


@router.get(
    "/accounts/",
    response_model=List[AccountSchema],
    **BANKING_ENDPOINTS["list_accounts"],
)
async def list_accounts(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return db.query(Account).filter(Account.user_id == current_user.id).all()


@router.post(
    "/accounts/{account_id}/deposit",
    response_model=TransactionSchema,
    **BANKING_ENDPOINTS["deposit"],
)
async def deposit(
    account_id: int,
    transaction: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if transaction.transaction_type != TransactionType.DEPOSIT:
        raise HTTPException(status_code=400, detail="Invalid transaction type")

    # Проверяем, есть ли у пользователя кредитный счет с балансом менее -20 000
    # и блокируем операции с дебетовым счетом
    if account.account_type == "debit":
        credit_account = (
            db.query(Account)
            .filter(
                Account.user_id == current_user.id,
                Account.account_type == "credit",
                Account.balance < -20000,
            )
            .first()
        )

        if credit_account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot perform operations with debit account when you have a credit account with balance less than -20,000",
            )

    amount_float = float(transaction.amount)

    db_transaction = Transaction(
        account_id=account.id,
        transaction_type=TransactionType.DEPOSIT,
        amount=amount_float,
        description=transaction.description,
    )
    account.balance += amount_float

    bonus_transaction = None
    if account.account_type == "current" and amount_float > 1000000:
        debit_account = (
            db.query(Account)
            .filter(Account.user_id == current_user.id, Account.account_type == "debit")
            .first()
        )

        if debit_account:
            bonus_transaction = Transaction(
                account_id=debit_account.id,
                transaction_type=TransactionType.DEPOSIT,
                amount=2000.0,
                description="Bonus for depositing more than 1,000,000 to current account",
            )
            debit_account.balance += 2000.0
            db.add(bonus_transaction)

    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)

    return db_transaction


@router.post(
    "/accounts/{account_id}/withdraw",
    response_model=TransactionSchema,
    **BANKING_ENDPOINTS["withdraw"],
)
async def withdraw(
    account_id: int,
    transaction: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if transaction.transaction_type != TransactionType.WITHDRAWAL:
        raise HTTPException(status_code=400, detail="Invalid transaction type")

    amount_float = float(transaction.amount)

    if amount_float > 30000:
        raise HTTPException(
            status_code=400,
            detail="Cannot withdraw more than 30,000 in one transaction",
        )

    if account.account_type != AccountType.CREDIT and account.balance < amount_float:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    if account.account_type == AccountType.CREDIT:
        if account.balance - amount_float < -account.credit_limit:
            raise HTTPException(status_code=400, detail="Credit limit exceeded")

    db_transaction = Transaction(
        account_id=account.id,
        transaction_type=TransactionType.WITHDRAWAL,
        amount=amount_float,
        description=transaction.description,
    )
    account.balance -= amount_float

    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction


@router.post(
    "/transfer/",
    response_model=List[TransactionSchema],
    **BANKING_ENDPOINTS["transfer"],
)
async def transfer(
    transfer: TransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    accounts = (
        db.query(Account)
        .filter(
            Account.id.in_([transfer.from_account_id, transfer.to_account_id]),
            Account.user_id == current_user.id,
        )
        .all()
    )

    if len(accounts) != 2:
        raise HTTPException(status_code=404, detail="One or both accounts not found")

    from_account = next(a for a in accounts if a.id == transfer.from_account_id)
    to_account = next(a for a in accounts if a.id == transfer.to_account_id)

    transfer_amount_float = float(transfer.amount)

    if transfer_amount_float > 30000:
        raise HTTPException(
            status_code=400,
            detail="Cannot transfer more than 30,000 in one transaction",
        )

    if from_account.account_type == AccountType.CREDIT:
        if from_account.balance - transfer_amount_float < -from_account.credit_limit:
            raise HTTPException(status_code=400, detail="Credit limit exceeded")
    elif from_account.balance < transfer_amount_float:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    withdrawal = Transaction(
        account_id=from_account.id,
        transaction_type=TransactionType.TRANSFER,
        amount=transfer_amount_float,
        description=f"Transfer to account {to_account.account_number}",
    )
    from_account.balance -= transfer_amount_float

    deposit = Transaction(
        account_id=to_account.id,
        transaction_type=TransactionType.TRANSFER,
        amount=transfer_amount_float,
        description=f"Transfer from account {from_account.account_number}",
    )
    to_account.balance += transfer_amount_float

    db.add_all([withdrawal, deposit])
    db.commit()
    db.refresh(withdrawal)
    db.refresh(deposit)

    return [withdrawal, deposit]


@router.get(
    "/accounts/{account_id}/transactions/",
    response_model=List[TransactionSchema],
    **BANKING_ENDPOINTS["list_transactions"],
)
async def list_transactions(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(Account)
        .filter(Account.id == account_id, Account.user_id == current_user.id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    return db.query(Transaction).filter(Transaction.account_id == account_id).all()


@router.get(
    "/available-users/",
    response_model=List[UserSchema],
    **BANKING_ENDPOINTS["available_users"],
)
async def get_available_users(
    search: str | None = Query(None, description="Search users by name or email"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all active users that are available for money transfers.
    Optionally filter users by name or email using the search parameter.
    Excludes the current user from the list.
    """
    query = db.query(User).filter(User.is_active == True, User.id != current_user.id)

    if search:
        search = f"%{search}%"
        query = query.filter(
            or_(
                User.full_name.ilike(search),
                User.email.ilike(search),
                User.phone.ilike(search),
            )
        )

    return query.all()


@router.get(
    "/users/{user_id}/accounts/",
    response_model=List[AccountSchema],
    **BANKING_ENDPOINTS["user_accounts"],
)
async def get_user_accounts(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all bank accounts belonging to the specified user.
    """
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    accounts = db.query(Account).filter(Account.user_id == user_id).all()
    return accounts


@router.post(
    "/inter-user-transfer/",
    response_model=List[TransactionSchema],
    **BANKING_ENDPOINTS["inter_user_transfer"],
)
async def inter_user_transfer(
    transfer: InterUserTransferCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Transfer money between accounts of different users.
    """
    from_account = (
        db.query(Account)
        .filter(
            Account.id == transfer.from_account_id, Account.user_id == current_user.id
        )
        .first()
    )

    if not from_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source account not found or doesn't belong to you",
        )

    to_user = (
        db.query(User)
        .filter(User.id == transfer.to_user_id, User.is_active == True)
        .first()
    )

    if not to_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient user not found or inactive",
        )

    to_account = (
        db.query(Account)
        .filter(
            Account.id == transfer.to_account_id, Account.user_id == transfer.to_user_id
        )
        .first()
    )

    if not to_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipient account not found"
        )

    transfer_amount_float = float(transfer.amount)

    if transfer_amount_float > 30000:
        raise HTTPException(
            status_code=400,
            detail="Cannot transfer more than 30,000 in one transaction",
        )

    if from_account.account_type == AccountType.CREDIT:
        if from_account.balance - transfer_amount_float < -from_account.credit_limit:
            raise HTTPException(status_code=400, detail="Credit limit exceeded")
    elif from_account.balance < transfer_amount_float:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    withdrawal = Transaction(
        account_id=from_account.id,
        transaction_type=TransactionType.TRANSFER,
        amount=transfer_amount_float,
        description=f"Transfer to user {to_user.full_name} (ID: {to_user.id}) account {to_account.account_number}",
    )
    from_account.balance -= transfer_amount_float

    deposit = Transaction(
        account_id=to_account.id,
        transaction_type=TransactionType.TRANSFER,
        amount=transfer_amount_float,
        description=f"Transfer from user {current_user.full_name} (ID: {current_user.id}) account {from_account.account_number}",
    )
    to_account.balance += transfer_amount_float

    db.add_all([withdrawal, deposit])
    db.commit()
    db.refresh(withdrawal)
    db.refresh(deposit)

    return [withdrawal, deposit]
