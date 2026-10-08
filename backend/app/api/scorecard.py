"""Read-oriented evaluation APIs. Financial facts and execution authority are not inputs."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.models.scorecard import AuditPage, DecisionTrace, Scorecard, ScorecardPage, ScorecardQuery
from app.models.terminal import TerminalPage
from app.services.audit import safe_record

router = APIRouter(prefix="/api", tags=["scorecard and audit"])
Id = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.:-]{1,160}$")]


def context(request):
    return dict(
        generated_at=request.app.state.scorecard.clock(),
        data_mode=request.app.state.scorecard.mode,
        run_id=request.app.state.run_id,
        request_id=request.state.request_id,
        correlation_id=request.state.correlation_id,
    )


def read(request, query, operation):
    try:
        values = request.app.state.settings.redaction_values()
        if any(v in query.model_dump_json() for v in values):
            raise HTTPException(422)
        service = request.app.state.scorecard
        cards = service.list(query)
        result = operation(service, cards)
        safe_record(result, values)
        return result
    except LookupError:
        raise HTTPException(404) from None
    except (ValueError, ArithmeticError, OSError, TypeError):
        raise HTTPException(503, "Evaluation unavailable; no substitution") from None


def page(items, query, reasons=()):
    return TerminalPage(
        items=tuple(items[query.offset : query.offset + query.limit]),
        limit=query.limit,
        offset=query.offset,
        has_more=len(items) > query.offset + query.limit,
        reasons=reasons,
    )


@router.get("/scorecard", response_model=ScorecardPage)
def scorecards(request: Request, query: Annotated[ScorecardQuery, Query()]):
    return read(
        request,
        query,
        lambda service, cards: ScorecardPage(
            **context(request), page=page(cards, query), metrics=service.metrics(cards)
        ),
    )


@router.get("/scorecard/{evaluation_id}", response_model=ScorecardPage)
def scorecard(evaluation_id: Id, request: Request):
    if request.query_params:
        raise HTTPException(422)

    def selected(service, _cards):
        card = next(
            (
                c
                for c in service.store.list(Scorecard, mode=service.mode)
                if c.evaluation_id == evaluation_id
            ),
            None,
        )
        if card is None:
            raise LookupError()
        return ScorecardPage(
            **context(request),
            page=TerminalPage(
                items=(card,),
                limit=1,
                offset=0,
                has_more=False,
                reasons=("IMMUTABLE_HISTORICAL_EVALUATION_NOT_CURRENT_STATE",),
            ),
            metrics=service.metrics((card,)),
        )

    return read(request, ScorecardQuery(), selected)


@router.get("/audit", response_model=AuditPage)
def events(request: Request, query: Annotated[ScorecardQuery, Query()]):
    return read(
        request,
        query,
        lambda service, cards: AuditPage(
            **context(request), page=page(service.events(cards, query), query)
        ),
    )


@router.get("/audit/decisions/{decision_id}", response_model=DecisionTrace)
def trace(decision_id: Id, request: Request, query: Annotated[ScorecardQuery, Query()]):
    if query.decision_id and query.decision_id != decision_id:
        raise HTTPException(422)
    query = query.model_copy(update={"decision_id": decision_id})
    return read(
        request,
        query,
        lambda service, cards: service.audit.trace(
            decision_id, cards, service.events(cards), context(request)
        ),
    )
