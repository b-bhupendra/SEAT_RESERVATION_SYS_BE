from typing import Generic, TypeVar, List
from pydantic import BaseModel
from sqlalchemy.orm import Query

T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

def paginate(query: Query, page: int, size: int) -> dict:
    total = query.count()
    pages = (total + size - 1) // size if size > 0 else 0
    
    if size > 0:
        items = query.offset((page - 1) * size).limit(size).all()
    else:
        items = query.all()
        
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }
