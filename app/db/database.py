from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.base import Base
import app.models 

# Base de datos SQLite para desarrollo y pruebas. En produccion se cambiara
DATABASE_URL = "mysql+pymysql://root:@localhost/prestamos"

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)