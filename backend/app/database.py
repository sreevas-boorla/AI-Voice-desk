from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)

# Enable foreign keys for SQLite
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app import models
    Base.metadata.create_all(bind=engine)
    
    # Create partial unique index on appointments:
    # No two active appointments for the same provider and start_time
    with engine.connect() as conn:
        try:
            if settings.DATABASE_URL.startswith("sqlite"):
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_provider_slot "
                    "ON appointments (provider_id, start_time) "
                    "WHERE status IN ('CONFIRMED', 'RESCHEDULED')"
                ))
            elif "postgres" in settings.DATABASE_URL:
                conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_provider_slot "
                    "ON appointments (provider_id, start_time) "
                    "WHERE status IN ('CONFIRMED', 'RESCHEDULED')"
                ))
            conn.commit()
        except Exception as e:
            # Index might already exist or DB dialect doesn't support partial index
            print(f"Index creation note: {e}")
