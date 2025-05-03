from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
import time
from sqlalchemy.exc import OperationalError

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if SQLALCHEMY_DATABASE_URL and "postgresql" in SQLALCHEMY_DATABASE_URL:
    if "?" in SQLALCHEMY_DATABASE_URL:
        SQLALCHEMY_DATABASE_URL += "&client_encoding=utf8"
    else:
        SQLALCHEMY_DATABASE_URL += "?client_encoding=utf8"

max_retries = 5
retry_delay = 5

for retry in range(max_retries):
    try:
        engine = create_engine(SQLALCHEMY_DATABASE_URL)
        engine.connect()
        break
    except OperationalError:
        if retry < max_retries - 1:
            time.sleep(retry_delay)
        else:
            raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
