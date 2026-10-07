from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from app.models.exposure import AskRequest, ExposureProposal, ParsedIntent
from app.services.intent import parse_intent

router = APIRouter(prefix="/api", tags=["dry-run exposure"])


def safe_text(body: AskRequest, request: Request):
    # A credential pasted as a stock request may not enter a provider query or SQLite.
    if any(value in body.text for value in request.app.state.settings.redaction_values()):
        raise HTTPException(422)
    return body.text


@router.post("/intent/parse", response_model=ParsedIntent)
def parse(body: AskRequest, request: Request):
    return parse_intent(safe_text(body, request))


@router.post("/exposure/quote", response_model=ExposureProposal)
def quote(body: AskRequest, request: Request):
    if request.query_params:
        raise HTTPException(404)
    return request.app.state.exposure.propose(
        safe_text(body, request),
        run_id=request.app.state.run_id,
        request_id=request.state.request_id,
        correlation_id=request.state.correlation_id,
    )


@router.get("/exposure/proposals/{proposal_id}", response_model=ExposureProposal)
def proposal(proposal_id: UUID, request: Request):
    service = request.app.state.exposure
    result = service.repository.get(proposal_id, service.layer.mode, service.clock())
    if result is None:
        raise HTTPException(404)
    return result
