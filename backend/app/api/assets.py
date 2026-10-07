from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from app.models.data import (
    EquityObservation,
    MarketStatus,
    NewsEvent,
    TokenMetadata,
    TokenObservation,
    TrackedAsset,
)


class AssetList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_mode: str
    assets: list[TrackedAsset]
    representations: list[TokenMetadata]
    limitations: dict[str, str] = {}


class AssetDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    data_mode: str
    reason: str | None = None
    asset: TrackedAsset | None = None
    assets: list = []
    tokens: list[TokenMetadata] = []
    token_observations: list[TokenObservation] = []
    equity_observations: list[EquityObservation] = []
    market_status: list[MarketStatus] = []
    news: list[NewsEvent] = []
    limitations: dict[str, str] = {}


router = APIRouter(prefix="/api", tags=["read-only data"])


@router.get("/assets", response_model=AssetList)
def assets(request: Request):
    return request.app.state.data_layer.assets()


@router.get("/assets/{ticker}", response_model=AssetDetail)
def asset(request: Request, ticker: str):
    if not 1 <= len(ticker) <= 100 or any(ord(c) < 32 for c in ticker):
        from fastapi import HTTPException

        raise HTTPException(422)
    return request.app.state.data_layer.asset(ticker)
