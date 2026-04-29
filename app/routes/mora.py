from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.services import mora as services
from app.schemas import mora as schemas
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/moras", tags=["Moras"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=list[schemas.MoraOut])
def listar_moras(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return services.get_moras(db, skip, limit)

@router.get("/{mora_id}", response_model=schemas.MoraOut)
def obtener_mora(mora_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_mora = services.get_mora(db, mora_id)
    if not db_mora:
        raise HTTPException(status_code=404, detail="Mora no encontrada")
    return db_mora

@router.put("/{mora_id}", response_model=schemas.MoraOut)
def actualizar_mora(mora_id: int, mora: schemas.MoraUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_mora = services.update_mora(db, mora_id, mora)
    if not db_mora:
        raise HTTPException(status_code=404, detail="Mora no encontrada")
    return db_mora

@router.delete("/{mora_id}")
def eliminar_mora(mora_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_mora = services.delete_mora(db, mora_id)
    if not db_mora:
        raise HTTPException(status_code=404, detail="Mora no encontrada")
    return {"mensaje": "Mora eliminada"}

# Manual temporalmente
@router.post("/procesar-moras")
def ejecutar_moras(db: Session = Depends(get_db)):
    moras = services.procesar_moras(db, tasa_diaria=0.01)
    return {"moras_actualizadas": [m.id for m in moras]}