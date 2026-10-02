import math

from sqlalchemy.orm import Query
from app.schemas.pagination import PaginatedResponse


def paginate(query: Query, page: int = 1, limit: int = 10) -> dict:
    page = max(1, page)
    limit = max(1, limit)

    total = query.count()
    pages = math.ceil(total / limit) if total else 0

    # RF-070: una página fuera de rango devuelve la última disponible.
    if pages and page > pages:
        page = pages

    offset = (page - 1) * limit
    items = query.offset(offset).limit(limit).all()

    return PaginatedResponse.crear(
        items=items,
        total=total,
        page=page,
        limit=limit
    ).model_dump()
