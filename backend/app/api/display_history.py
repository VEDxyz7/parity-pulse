"""Fixed-window history reads. Never refreshes a provider or writes production evidence."""

from typing import Literal

from fastapi import APIRouter

from app.models.display_history import DisplayHistory
from app.services.display_history import load_history

router = APIRouter(prefix="/api/display-history", tags=["historical display only"])


@router.get("/{ticker}", response_model=DisplayHistory)
def history(ticker: Literal["NVDA", "AAPL"]):
    return load_history(ticker)
