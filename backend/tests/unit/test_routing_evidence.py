"""Existing Trust cache can inform a route only with matching current scope/price/ratio."""

from datetime import timedelta
from uuid import uuid4

import pytest

from app.repositories.trust import TrustRepository
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.routing_evidence import RoutingEvidenceReader


def changed(model, **values):
    return type(model).model_validate({**model.model_dump(), **values})


@pytest.mark.parametrize(
    "mutation", ["matching", "price", "ratio", "identity", "old", "future", "other_mode"]
)
def test_cached_trust_is_scoped_fresh_and_bound_to_actual_price_and_ratio(
    client, application, mutation
):
    # Deliberately synthetic cached assessment to test join/filter contracts, not calibration.
    service = application.state.exposure
    layer = service.layer
    token = next(t for t in layer.rwa.records["metadata"] if t.ticker == "NVDA")
    price = next(p for p in layer.rwa.records["tokens"] if p.ticker == "NVDA")
    assessment = (
        DemoTrustSandbox()
        .assess(
            "thin-move",
            run_id="offline-test",
            request_id="offline-test",
            correlation_id="offline-test",
        )
        .assessment
    )
    now = assessment.evaluated_at
    row = changed(
        assessment.representations[0],
        token_price_usd=price.token_price,
        token_to_share_ratio=token.token_to_share_ratio,
        token_timestamp=price.source_timestamp,
    )
    if mutation == "price":
        row = changed(row, token_price_usd="1")
    elif mutation == "ratio":
        row = changed(row, token_to_share_ratio="2")
    elif mutation == "identity":
        row = changed(row, contract="demo:unrelated")
    assessment = changed(assessment, assessment_id=uuid4(), representations=[row])
    if mutation == "old":
        assessment = changed(assessment, evaluated_at=now - timedelta(seconds=120))
    elif mutation == "future":
        assessment = changed(assessment, evaluated_at=now + timedelta(seconds=1))
    elif mutation == "other_mode":
        assessment = changed(assessment, data_mode="LIVE")
    TrustRepository(service.repository.database).save(assessment)
    service.clock = lambda: now
    proposal = client.post("/api/exposure/quote", json={"text": "Buy $50 NVDA"}).json()
    route = proposal["route_decision"]
    if mutation == "matching":
        assert route["status"] == "NO_ROUTE"
        assert route["candidates"][0]["inputs"]["trust_assessment_id"] == str(
            assessment.assessment_id
        )
        assert "TRUST_LIKELY_NOISE" in route["candidates"][0]["rejection_reasons"]
    else:
        assert route["status"] == "ROUTE_SELECTED"
        assert route["candidates"][0]["inputs"]["trust_state"] == "UNKNOWN"
    assert not route["execution_ready"]
    reader = RoutingEvidenceReader(service.repository.database)
    assert reader.latest("UNSUPPORTED", mode="DEMO", now=now) is None
    with pytest.raises(ValueError):
        reader.latest("NVDA", mode="ANY", now=now)
