"""GET-only Terminal inspection. Never invokes refresh, agents, quotes or reconciliation."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.models.terminal import (
    AgentEvidenceRow,
    EpisodeQuery,
    EpisodeRow,
    ExecutionAnalyticsRow,
    IssuerRow,
    TerminalOverview,
    TerminalQuery,
    TerminalSection,
    TrustMonitorRow,
)

router = APIRouter(prefix="/api/terminal", tags=["read-only Terminal analytics"])


def safe_projection(value):
    if isinstance(value, dict):
        if set(value) & {
            "chain_of_thought",
            "hidden_reasoning",
            "private_key",
            "userSignature",
            "typedDataToSign",
        }:
            raise ValueError("Forbidden analytical projection")
        for item in value.values():
            safe_projection(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            safe_projection(item)


def read(request, query, section=None):
    service = request.app.state.terminal
    try:
        if any(v in query.model_dump_json() for v in request.app.state.settings.redaction_values()):
            raise HTTPException(422)
        context = dict(
            generated_at=service.clock(),
            data_mode=service.mode,
            run_id=request.app.state.run_id,
            request_id=request.state.request_id,
            correlation_id=request.state.correlation_id,
        )
        result = (
            TerminalSection(
                **context, page=getattr(service, section)(query, context["generated_at"])
            )
            if section
            else service.overview(query, context)
        )
        if any(
            v in result.model_dump_json() for v in request.app.state.settings.redaction_values()
        ):
            raise ValueError("Sensitive stored content refused")
        safe_projection(result.model_dump())
        return result
    except (ValueError, LookupError, ArithmeticError, OSError, TypeError):
        raise HTTPException(503, "Terminal records unavailable; no substitution") from None


@router.get("", response_model=TerminalOverview)
def overview(request: Request, query: Annotated[TerminalQuery, Query()]):
    return read(request, query)


@router.get("/issuers", response_model=TerminalSection[IssuerRow])
@router.get("/prices", response_model=TerminalSection[IssuerRow])
def issuers(request: Request, query: Annotated[TerminalQuery, Query()]):
    return read(request, query, "issuers")


@router.get("/trust", response_model=TerminalSection[TrustMonitorRow])
def trust(request: Request, query: Annotated[TerminalQuery, Query()]):
    return read(request, query, "trust_monitor")


@router.get("/agents", response_model=TerminalSection[AgentEvidenceRow])
def agents(request: Request, query: Annotated[TerminalQuery, Query()]):
    return read(request, query, "agent_evidence")


@router.get("/executions", response_model=TerminalSection[ExecutionAnalyticsRow])
def executions(request: Request, query: Annotated[TerminalQuery, Query()]):
    return read(request, query, "executions")


@router.get("/episodes", response_model=TerminalSection[EpisodeRow])
def episodes(request: Request, query: Annotated[EpisodeQuery, Query()]):
    return read(request, query, "episodes")
