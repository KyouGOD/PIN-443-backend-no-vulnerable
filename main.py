import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.database.database import engine, Base
from app.api import auth, banking
from app.auth.oauth import oauth
from app.docs.api_description import API_DESCRIPTION, TAGS_DESCRIPTIONS


app = FastAPI(
    root_path="/api",
    title="Банковский API",
    description=API_DESCRIPTION,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "auth", "description": TAGS_DESCRIPTIONS["auth"]},
        {"name": "banking", "description": TAGS_DESCRIPTIONS["banking"]},
    ],
)

Base.metadata.create_all(bind=engine)

app.state.oauth = oauth

app.add_middleware(
    SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "your-secret-key")
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "https://localhost:4200",
        "https://pin-443.ru",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(banking.router)
