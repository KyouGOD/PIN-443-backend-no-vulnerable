import httpx
import secrets
import os
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.auth.oauth import oauth, create_access_token, get_current_user, get_password_hash, authenticate_user
from app.models.user import User
from app.schemas.user import User as UserSchema, UserCreate, UserLogin, Token
from app.docs.api_description import AUTH_ENDPOINTS
from urllib.parse import urlencode
from sqlalchemy.exc import IntegrityError


# build t
router = APIRouter(prefix="/auth", tags=["auth"])

def get_secure_callback_url(request: Request, endpoint: str) -> str:
    base_url = os.getenv("BASE_URL")
    if base_url:
        path = request.app.url_path_for(endpoint)
        return f"{base_url.rstrip('/')}{path}"
    else:
        return str(request.url_for(endpoint))

def get_frontend_redirect_url(access_token: str) -> str:
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    params = urlencode({"access_token": access_token})
    return f"{frontend_url}/auth/callback?{params}"

@router.get(
    "/login/google",
    **AUTH_ENDPOINTS["google_login"]
)
async def google_login(request: Request):
    nonce = secrets.token_urlsafe(32)
    request.session["nonce"] = nonce
    redirect_uri = get_secure_callback_url(request, "google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri, nonce=nonce)

@router.get(
    "/callback/google",
    **AUTH_ENDPOINTS["google_callback"]
)
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
        nonce = request.session.get("nonce")
        userinfo = await oauth.google.parse_id_token(token, nonce=nonce)

        request.session.pop("nonce", None)

        user = db.query(User).filter(User.email == userinfo["email"]).first()
        if not user:
            user = User(
                email=userinfo["email"],
                full_name=userinfo["name"],
                google_id=userinfo["sub"],
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )
        redirect_url = get_frontend_redirect_url(access_token)
        return RedirectResponse(url=redirect_url)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail="Could not authenticate with Google"
        ) from e

@router.get(
    "/login/yandex",
    **AUTH_ENDPOINTS["yandex_login"]
)
async def yandex_login(request: Request):
    redirect_uri = get_secure_callback_url(request, "yandex_callback")
    return await oauth.yandex.authorize_redirect(request, redirect_uri)

@router.get(
    "/callback/yandex",
    **AUTH_ENDPOINTS["yandex_callback"]
)
async def yandex_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.yandex.authorize_access_token(request)

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.get(
                "https://login.yandex.ru/info",
                params={"format": "json"},
                headers={
                    "Authorization": f"OAuth {token['access_token']}",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            userinfo = resp.json()

            user = db.query(User).filter(User.email == userinfo["default_email"]).first()
            if not user:
                user = User(
                    email=userinfo["default_email"],
                    full_name=f"{userinfo.get('first_name', '')} {userinfo.get('last_name', '')}".strip(),
                    yandex_id=userinfo["id"],
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            access_token = create_access_token(
                data={"sub": str(user.id), "email": user.email}
            )
            redirect_url = get_frontend_redirect_url(access_token)
            return RedirectResponse(url=redirect_url)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail="Could not authenticate with Yandex"
        ) from e

@router.get("/me", response_model=UserSchema, **AUTH_ENDPOINTS["current_user"])
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get information about the current authenticated user.
    """
    return current_user

@router.post("/register", response_model=UserSchema, status_code=status.HTTP_201_CREATED, **AUTH_ENDPOINTS["register"])
async def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user with email/phone and password.
    """
    # Проверка, существует ли пользователь с такими данными
    if user_data.email:
        db_user = db.query(User).filter(User.email == user_data.email).first()
        if db_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
    
    if user_data.phone:
        db_user = db.query(User).filter(User.phone == user_data.phone).first()
        if db_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone already registered"
            )
    
    # Создаем нового пользователя
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        email=user_data.email,
        phone=user_data.phone,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
        google_id=user_data.google_id,
        yandex_id=user_data.yandex_id
    )
    
    try:
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed. Please check your data and try again."
        )

@router.post("/login", response_model=Token, **AUTH_ENDPOINTS["login"])
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticate user with email/phone and password.
    """
    user = authenticate_user(
        db, 
        email=user_data.email, 
        phone=user_data.phone, 
        password=user_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Создаем access token с данными пользователя
    token_data = {
        "sub": str(user.id),
    }
    if user.email:
        token_data["email"] = user.email
    if user.phone:
        token_data["phone"] = user.phone
    
    access_token = create_access_token(token_data)
    
    return {"access_token": access_token, "token_type": "bearer"}
