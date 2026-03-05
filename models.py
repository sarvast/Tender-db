import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database URL format: postgresql://user:password@localhost:5432/dbname
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/gem_tenders")

# Setup the database engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Tender(Base):
    __tablename__ = "tenders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    gem_bid_number = Column(String, unique=True, index=True, nullable=False)
    department_name = Column(String, nullable=True)
    # Using JSON type for list of strings (compatible with SQLite)
    item_categories = Column(JSON, nullable=True)
    estimated_value = Column(Float, nullable=True)
    emd_amount = Column(Float, nullable=True)
    bid_end_date = Column(DateTime, nullable=False)
    mii_applicable = Column(Boolean, default=False)
    mse_preference = Column(Boolean, default=False)
    is_notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

# Create tables if they do not exist
Base.metadata.create_all(bind=engine)
