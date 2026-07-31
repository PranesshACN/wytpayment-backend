from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core import config

# SQLite requires different check_same_thread parameter
if config.IS_SQLITE:
    connect_args = {"check_same_thread": False}
    engine = create_engine(config.DATABASE_URL, connect_args=connect_args)
else:
    # pool_pre_ping prevents closed connections issues in pooler setups like Supabase/pgbouncer
    engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
