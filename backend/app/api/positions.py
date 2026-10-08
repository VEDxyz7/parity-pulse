"""Single-account position inspection only. No public evidence ingestion or exit API."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from app.models.position import Position

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("", response_model=list[Position])
def positions(request: Request, limit: int = 100):
    if not 1 <= limit <= 1000:
        raise HTTPException(422, "Bounded position listing required")
    service = request.app.state.positions
    return service.store.list(mode=service.mode, limit=limit)


@router.get("/{position_id}", response_model=Position)
def position(position_id: UUID, request: Request):
    service = request.app.state.positions
    try:
        return service.store.get(position_id, mode=service.mode)
    except KeyError:
        raise HTTPException(404, "Position not found in this data mode") from None
