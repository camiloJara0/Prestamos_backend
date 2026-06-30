from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.base import Base
from dotenv import load_dotenv
import app.models
import os

load_dotenv()

# Base de datos SQLite para desarrollo y pruebas. En produccion se cambiara a MySQL
# DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")
DATABASE_URL = "mysql+pymysql://root:@localhost/prestamos"  # Cambiar a la URL de tu base de datos MySQL


engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)