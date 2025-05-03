import os
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.models.user import User
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()

# Настройка для хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Используем HTTPBearer вместо OAuth2PasswordBearer для простой JWT авторизации
security = HTTPBearer(scheme_name="JWT")

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

oauth.register(
    name="yandex",
    client_id=os.getenv("YANDEX_CLIENT_ID"),
    client_secret=os.getenv("YANDEX_CLIENT_SECRET"),
    authorize_url="https://oauth.yandex.ru/authorize",
    access_token_url="https://oauth.yandex.ru/token",
    api_base_url="https://login.yandex.ru/info",
    client_kwargs={"scope": "login:email login:info"},
)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    credentials=Depends(security), db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


# Функции для работы с паролями
def verify_password(plain_password, hashed_password):
    """Проверяет соответствие пароля его хешу"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    """Хеширует пароль"""
    return pwd_context.hash(password)


def authenticate_user(
    db: Session, email: str = None, phone: str = None, password: str = None
):
    """
    Аутентифицирует пользователя по email/телефону и паролю
    Возвращает пользователя, если аутентификация успешна, иначе None
    """
    # Поиск пользователя по email или телефону
    user = None
    if email:
        user = db.query(User).filter(User.email == email).first()
    elif phone:
        user = db.query(User).filter(User.phone == phone).first()

    # Проверка пароля, если пользователь найден
    if user and verify_password(password, user.hashed_password):
        return user
    return None
