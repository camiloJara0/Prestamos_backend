from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from datetime import date, timedelta
from urllib.parse import quote_plus
from typing import List

from app.db.database import SessionLocal
from app.schemas.notificacion import (
    PushSubscriptionCreate, 
    PushSubscriptionOut, 
    RecordatorioCuotaResponse
)
from app.dependencies.auth import get_current_user
from app.services import notificacion as notificacion_service
from app.models.models import PrestamoCuota, Prestamo, Cliente, MetodoPagoPrestamista

router = APIRouter(prefix="/notificacion", tags=["Notificaciones"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/subscribe", response_model=PushSubscriptionOut, status_code=status.HTTP_201_CREATED)
def suscribir_push(
    subscription: PushSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Registra o actualiza la suscripción Push delegando a la capa de servicios."""
    return notificacion_service.guardar_suscripcion(
        db=db, 
        email_usuario=current_user["sub"], 
        subscription=subscription
    )


@router.post("/unsubscribe")
def desuscribir_push(
    subscription: PushSubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Elimina la suscripción Push especificada por su endpoint."""
    notificacion_service.eliminar_suscripcion(db=db, endpoint=subscription.endpoint)
    return {"message": "Suscripción eliminada correctamente."}


@router.get("/proximos-vencimientos", response_model=List[RecordatorioCuotaResponse])
def obtener_proximos_vencimientos(
    dias_anticipacion: int = Query(default=3, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene las cuotas pendientes que vencen en los próximos N días.
    Genera la plantilla con el formato Credifast y el enlace directo a WhatsApp.
    """
    hoy = date.today()
    fecha_limite = hoy + timedelta(days=dias_anticipacion)

    # Consulta optimizada uniendo Cuotas -> Préstamos -> Clientes
    cuotas_proximas = (
        db.query(PrestamoCuota, Prestamo, Cliente)
        .join(Prestamo, PrestamoCuota.prestamo_id == Prestamo.id)
        .join(Cliente, Prestamo.cliente_id == Cliente.id)
        .filter(
            PrestamoCuota.estado == "pendiente",
            PrestamoCuota.fecha_vencimiento >= hoy,
            PrestamoCuota.fecha_vencimiento <= fecha_limite
        )
        .order_by(PrestamoCuota.fecha_vencimiento.asc())
        .all()
    )

    resultado = []
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio", 
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    for cuota, prestamo, cliente in cuotas_proximas:
        dias_restantes = (cuota.fecha_vencimiento - hoy).days
        
        # Formato del monto sin decimales y con puntos de miles (ej: 105.000)
        monto_fmt = f"{int(cuota.valor_cuota):,}".replace(",", ".")
        
        # Formato de fecha legible (ej: 24 octubre)
        fecha_str = f"{cuota.fecha_vencimiento.day} {meses[cuota.fecha_vencimiento.month - 1]}"
        
        # Extraer solo el primer nombre del cliente
        primer_nombre = cliente.nombre.split()[0].capitalize() if cliente.nombre else "Cliente"
        referencia = cuota.referencia_pago or f"REF-P{prestamo.id}C{cuota.numero_cuota}"

        # Plantilla limpia (sin espacios especiales ni invisibles)
        mensaje = (
            f"Hola {primer_nombre}\n"
            f"Recuerda que se acerca la fecha de pago de tu cuota con Credifast 💸\n"
            f"👉Cuota {monto_fmt}\n"
            f"📆 Fecha límite : {fecha_str}\n\n"
            f"Puedes hacer el pago por transferencia o programar recogida"
        )

        # Formatear teléfono con indicativo de Colombia (+57)
        telefono_limpio = "".join(filter(str.isdigit, cliente.telefono or ""))
        if len(telefono_limpio) == 10:
            telefono_limpio = f"57{telefono_limpio}"

        # Uso de api.whatsapp.com/send con quote_plus para forzar interpretación limpia en WhatsApp Web / App
        if telefono_limpio:
            mensaje_encoded = quote_plus(mensaje)
            url_wa = f"https://api.whatsapp.com/send?phone={telefono_limpio}&text={mensaje_encoded}"
        else:
            url_wa = ""

        resultado.append(
            RecordatorioCuotaResponse(
                cuota_id=cuota.id,
                prestamo_id=prestamo.id,
                cliente_nombre=cliente.nombre,
                cliente_telefono=cliente.telefono or "",
                numero_cuota=cuota.numero_cuota,
                monto=cuota.valor_cuota,
                fecha_vencimiento=cuota.fecha_vencimiento,
                dias_para_vencer=dias_restantes,
                referencia_pago=referencia,
                mensaje_whatsapp=mensaje,
                whatsapp_url=url_wa
            )
        )

    return resultado