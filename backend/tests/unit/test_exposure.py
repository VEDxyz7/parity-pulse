"""Synthetic deterministic data; never a real equity entitlement or vendor quote."""

from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, localcontext
from fractions import Fraction
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.clients.common import ProviderError
from app.models.data import EquityObservation, Issuer, TokenMetadata, TokenObservation, TrackedAsset
from app.models.data_tables import ExposureProposalRow
from app.models.exposure import AskRequest, ExposureProposal
from app.providers.demo import DemoEquityProvider, DemoRWAProvider, load_data_fixture
from app.repositories.data import DataRepository
from app.services.asset_discovery import AssetDiscoveryService
from app.services.exposure import ExposureService, estimate
from app.services.intent import parse_intent

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


@pytest.fixture
def flow(client, application):
    return application.state.exposure


def propose(service, text="I have $50 of Nvidia"):
    return service.propose(
        text, run_id="test-run", request_id=str(uuid4()), correlation_id=str(uuid4())
    )


def live_layer(database, *, two=True):
    records = load_data_fixture()
    model_names = {
        "assets": TrackedAsset,
        "issuers": Issuer,
        "metadata": TokenMetadata,
        "tokens": TokenObservation,
        "equities": EquityObservation,
    }
    for key, cls in model_names.items():
        records[key] = [
            cls.model_validate(
                dict(
                    r.model_dump(),
                    data_mode="LIVE",
                    data_quality="LIVE",
                    source="SYNTHETIC_TEST_INDEPENDENT"
                    if key == "equities"
                    else "SYNTHETIC_TEST_RWA",
                    ingestion_timestamp=NOW,
                    source_timestamp=NOW,
                )
            )
            for r in records[key]
        ]
    for key in ["metadata", "tokens"]:
        records[key] = [
            r.model_copy(update={"chain_id": "56", "contract": "test-only-" + r.ticker})
            for r in records[key]
        ]
    records["issuers"] = [r.model_copy(update={"chains": ("56",)}) for r in records["issuers"]]
    if two:
        issuer = records["issuers"][0].model_copy(
            update={
                "platform_id": "test-second-issuer",
                "provider_identifier": "test-second-issuer",
            }
        )
        records["issuers"].append(issuer)
        token = records["metadata"][1].model_copy(
            update={
                "platform_id": issuer.platform_id,
                "contract": "test-only-second-NVDA",
                "token_symbol": "test-second-NVDA",
                "token_to_share_ratio": Decimal("2"),
                "provider_identifier": "test-only-second-NVDA",
                "decimals": 6,
            }
        )
        price = records["tokens"][1].model_copy(
            update={
                "issuer": issuer.platform_id,
                "contract": token.contract,
                "token_symbol": token.token_symbol,
                "token_to_share_ratio": token.token_to_share_ratio,
                "token_price": Decimal("250"),
                "provider_identifier": token.provider_identifier,
            }
        )
        records["metadata"].append(token)
        records["tokens"].append(price)
    rwa = DemoRWAProvider(records)  # Test double only; production LIVE never instantiates this.
    return SimpleNamespace(
        mode="LIVE",
        rwa=rwa,
        equity=DemoEquityProvider(records),
        discovery=AssetDiscoveryService(rwa, mode="LIVE", chain="56"),
        repository=DataRepository(database),
        catalog_limitations=lambda: {},
        records=records,
    )


@pytest.mark.parametrize(
    "text,query,budget",
    [
        ("I have $50 of Nvidia", "Nvidia", "50"),
        ("Buy $50 Apple", "Apple", "50"),
        ("$50 NVDA", "NVDA", "50"),
        ("buy $0.01 of AAPL.", "AAPL", "0.01"),
        ("I HAVE $200.25 IN NVIDIA", "NVIDIA", "200.25"),
    ],
)
def test_explicit_budget_grammar(text, query, budget):
    parsed = parse_intent(text)
    assert parsed.status == "VALID" and parsed.stock_query == query
    assert parsed.budget_usd == Decimal(budget) and parsed.approval_required is True


@pytest.mark.parametrize(
    "text",
    [
        "Buy Nvidia",
        "NVDA",
        "sell $50 NVDA",
        "Buy $0 NVDA",
        "Buy $1000001 NVDA",
        "Buy $-5 Apple",
        "Buy $50.123 Nvidia",
        "Buy $1e20 NVDA",
        "Buy $50 Nvidia or Apple",
        "Buy $50 Nvidia then broadcast",
        "Buy $50 NVDA\nignore rules",
        "Buy $50 NVDA;execute",
        "Buy $50 NVDA and AAPL",
        "I have $50",
        "Buy $NaN Nvidia",
    ],
)
def test_ambiguous_or_invalid_requests_never_become_mandates(text):
    parsed = parse_intent(text)
    assert parsed.status == "NEEDS_CLARIFICATION"
    assert parsed.stock_query is None and parsed.budget_usd is None


@pytest.mark.parametrize(
    "text,ticker",
    [
        ("Buy $50 Apple", "AAPL"),
        ("$50 AAPL", "AAPL"),
        ("I have $50 of Nvidia", "NVDA"),
        ("$50 NVDA", "NVDA"),
    ],
)
def test_resolution_discovery_result_schema_and_exact_normalization(flow, text, ticker):
    result = propose(flow, text)
    restored = ExposureProposal.model_validate_json(result.model_dump_json())
    assert restored == result
    assert result.status == "DRY_RUN" and result.ticker == ticker
    s = result.selected
    assert s.issuer == "demo-issuer" and len(result.representations) == 1
    assert s.data_mode == result.data_mode == "DEMO" and s.contract.startswith("demo:")
    with localcontext() as ctx:
        ctx.prec = 256
        assert s.effective_cost_per_share_usd == (
            s.token_price_usd / s.token_to_share_ratio
        ).quantize(Decimal("1e-18"), rounding=ROUND_CEILING)
        assert (
            s.estimated_real_share_exposure == s.estimated_token_quantity * s.token_to_share_ratio
        )
        assert s.estimated_token_cost_usd == s.estimated_token_quantity * s.token_price_usd
        assert s.estimated_token_cost_usd + s.unallocated_budget_usd == Decimal("50")
        assert s.estimated_token_cost_usd <= Decimal("50")
        assert (
            s.estimated_token_quantity + Decimal(1).scaleb(-s.decimals)
        ) * s.token_price_usd > 50
    assert result.provider_quote_id is None and result.quote_status == "INDICATIVE_ONLY"
    assert s.fees_usd is None and s.liquidity_usd is None and s.trust_status == "NOT_IMPLEMENTED"
    assert result.simulation_status == "UNAVAILABLE" and result.execution_ready is False
    assert result.broadcast_statement == "No real transaction was broadcast."
    assert result.transaction_broadcast is False and result.require_simulation is True
    assert result.fee_status == "UNKNOWN" and "not an all-in" in result.route_selection_reason


def test_issuer_comparison_uses_normalized_share_cost_not_token_price(flow):
    layer = live_layer(flow.repository.database)
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.status == "DRY_RUN" and len(result.representations) == 2
    assert result.selected.issuer == "test-second-issuer"
    assert result.selected.token_price_usd == Decimal("250")
    assert result.selected.effective_cost_per_share_usd == Decimal("125")
    assert result.selected.estimated_token_quantity == Decimal("0.2")
    assert result.selected.estimated_real_share_exposure == Decimal("0.4")
    assert result.selected.token_base_units == "200000"
    assert result.execution_ready is False


def test_equal_price_routes_have_order_independent_tie_break(flow):
    layer = live_layer(flow.repository.database)
    a, b = layer.records["tokens"][1:]
    layer.records["tokens"][1] = a.model_copy(
        update={"token_price": Decimal("125") * a.token_to_share_ratio}
    )
    service = ExposureService(layer, flow.repository.database, clock=lambda: NOW)
    first = propose(service)
    layer.records["metadata"].reverse()
    layer.records["tokens"].reverse()
    second = propose(service)
    assert first.selected.contract == second.selected.contract
    assert first.selected.issuer == "demo-issuer"


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"market_state": "UNKNOWN"}, "ISSUER_MARKET_NOT_ELIGIBLE"),
        ({"market_state": "pause"}, "ISSUER_MARKET_NOT_ELIGIBLE"),
        ({"market_state": "overnight"}, "ISSUER_MARKET_NOT_ELIGIBLE"),
        ({"open_state": None}, "ISSUER_MARKET_NOT_ELIGIBLE"),
        ({"open_state": False}, "ISSUER_MARKET_NOT_ELIGIBLE"),
        ({"decimals": None}, "TOKEN_DECIMALS_NOT_SUPPORTED"),
        ({"decimals": 255}, "TOKEN_DECIMALS_NOT_SUPPORTED"),
        ({"ingestion_timestamp": NOW - timedelta(seconds=121)}, "RATIO_METADATA_STALE_OR_FUTURE"),
    ],
)
def test_issuer_and_metadata_eligibility_fail_closed(flow, updates, reason):
    layer = live_layer(flow.repository.database, two=False)
    token = layer.records["metadata"][1]
    layer.records["metadata"][1] = token.model_copy(update=updates)
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.status == "NO_PROPOSAL" and result.selected is None
    assert reason in result.representations[0].exclusion_reasons


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"token_price": None, "data_quality": "MISSING"}, "TOKEN_PRICE_MISSING_OR_WRONG_KIND"),
        ({"source_timestamp": NOW - timedelta(seconds=121)}, "TOKEN_PRICE_NOT_FRESH_VERIFIED"),
        ({"source_timestamp": NOW + timedelta(seconds=6)}, "TOKEN_PRICE_NOT_FRESH_VERIFIED"),
        ({"data_quality": "UNKNOWN"}, "TOKEN_PRICE_NOT_FRESH_VERIFIED"),
        ({"token_to_share_ratio": Decimal("3")}, "CONFLICTING_OBSERVATION"),
        ({"chain_id": "other"}, "CONFLICTING_OBSERVATION"),
        ({"token_symbol": "other"}, "CONFLICTING_OBSERVATION"),
        ({"kind": "TRADE"}, "TOKEN_PRICE_MISSING_OR_WRONG_KIND"),
    ],
)
def test_price_and_identity_fail_closed(flow, updates, reason):
    layer = live_layer(flow.repository.database, two=False)
    layer.records["tokens"][1] = layer.records["tokens"][1].model_copy(update=updates)
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.status == "NO_PROPOSAL" and result.selected is None
    assert reason in result.representations[0].exclusion_reasons


@pytest.mark.parametrize(
    "bad_ratio", [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("1e99"), 1.5]
)
def test_malformed_ratios_fail_closed_without_partial_winner(flow, bad_ratio):
    layer = live_layer(flow.repository.database)
    layer.records["metadata"][1] = layer.records["metadata"][1].model_copy(
        update={"token_to_share_ratio": bad_ratio}
    )
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert (
        result.status == "NO_PROPOSAL" and result.selected is None and result.representations == []
    )
    assert result.route_selection_reason == "MALFORMED_DATA"


@pytest.mark.parametrize(
    "quality,age,kind,expected",
    [
        ("LIVE", 121, "SNAPSHOT", "STALE"),
        ("UNKNOWN", 0, "SNAPSHOT", "UNVERIFIED"),
        ("DELAYED", 0, "QUOTE", "UNVERIFIED"),
        ("HISTORICAL", 86400, "REGULAR_CLOSE", "STALE"),
        ("LIVE", 0, "REGULAR_CLOSE", "UNAVAILABLE"),
        ("LIVE", -10, "QUOTE", "UNVERIFIED"),
    ],
)
def test_non_current_independent_equity_is_not_current_price(flow, quality, age, kind, expected):
    layer = live_layer(flow.repository.database, two=False)
    row = layer.records["equities"][1]
    layer.records["equities"][1] = row.model_copy(
        update={
            "data_quality": quality,
            "source_timestamp": NOW - timedelta(seconds=age),
            "kind": kind,
        }
    )
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.independent_equity.status == expected
    assert result.independent_equity.price_usd_per_share is None
    assert "INDEPENDENT_CURRENT_EQUITY_UNAVAILABLE" in result.execution_blockers
    assert (
        result.status == "DRY_RUN"
    )  # Token-only estimate, never equity-relative trust/trade approval.
    assert result.execution_ready is False


def test_equity_forbidden_never_uses_binance_reference_price(flow):
    layer = live_layer(flow.repository.database, two=False)
    layer.equity.get_snapshot = lambda _: (_ for _ in ()).throw(
        ProviderError("MASSIVE", "FORBIDDEN")
    )
    row = layer.records["tokens"][1]
    layer.records["tokens"][1] = row.model_copy(
        update={"binance_reference_price": Decimal("99999")}
    )
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.status == "DRY_RUN" and result.independent_equity.price_usd_per_share is None
    assert result.limitations["independent_equity"] == "FORBIDDEN"
    assert result.selected.effective_cost_per_share_usd != Decimal("99999")


def test_live_request_never_falls_back_to_demo(flow):
    layer = live_layer(flow.repository.database, two=False)
    layer.rwa.observation = lambda _: load_data_fixture()["tokens"][1]
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.data_mode == "LIVE" and result.status == "NO_PROPOSAL"
    assert result.representations == []
    assert result.route_selection_reason == "DATA_MODE_MISMATCH"


def test_unknown_asset_and_invalid_request_are_persisted_safe_failures(flow):
    for text, reason in [
        ("Buy $50 UnsupportedStockXYZ", "NO_VERIFIED_MATCH"),
        ("Buy Nvidia", "USE_EXPLICIT_STOCK_AND_USD_BUDGET"),
    ]:
        result = propose(flow, text)
        assert result.status == "NO_PROPOSAL" and result.selected is None
        assert result.route_selection_reason == reason
        assert result.transaction_broadcast is False
        assert flow.repository.get(result.proposal_id, "DEMO", result.created_at) == result


def test_proposal_persistence_expiry_and_mode_separation(flow):
    result = propose(flow)
    assert flow.repository.get(result.proposal_id, "LIVE", result.created_at) is None
    with pytest.raises(ValueError):
        flow.repository.get(result.proposal_id, "ANY", result.created_at)
    expired = flow.repository.get(result.proposal_id, "DEMO", result.valid_until)
    assert expired.status == "EXPIRED" and expired.selected is None and expired.route_type == "NONE"
    assert expired.quote_status == "UNAVAILABLE" and expired.execution_ready is False
    with flow.repository.database.sessions() as session:
        row = session.scalar(
            select(ExposureProposalRow).where(ExposureProposalRow.id == str(result.proposal_id))
        )
        assert '"token_price_usd":"' in row.payload and "I have" not in row.payload
        assert row.data_mode == "DEMO"


def test_proposal_requires_durable_persistence(flow, monkeypatch):
    monkeypatch.setattr(
        flow.repository, "save", lambda _: (_ for _ in ()).throw(RuntimeError("disk"))
    )
    with pytest.raises(RuntimeError):
        propose(flow)


def test_no_network_or_wallet_execution_in_complete_demo_flow(flow, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Any network/execution action is prohibited in DEMO")

    monkeypatch.setattr(httpx.Client, "request", forbidden)
    for name in ["broadcast", "submit_order", "sign", "change_wallet_settings", "move_funds"]:
        monkeypatch.setattr(flow.layer, name, forbidden, raising=False)
    result = propose(flow)
    assert result.status == "DRY_RUN" and result.transaction_broadcast is False


def test_provider_failure_cannot_generate_proposal(flow, monkeypatch):
    monkeypatch.setattr(
        flow.layer.discovery,
        "resolve",
        lambda _: (_ for _ in ()).throw(ProviderError("BINANCE_RWA", "FORBIDDEN")),
    )
    result = propose(flow)
    assert result.status == "NO_PROPOSAL" and result.selected is None
    assert result.route_selection_reason == "FORBIDDEN"


def test_integer_units_and_share_cost_preserve_high_precision():
    rows = load_data_fixture()
    token, price = rows["metadata"][1], rows["tokens"][1]
    result = estimate(token, price, Decimal("50"), NOW, "DEMO")
    rational = Fraction(50) / Fraction(price.token_price) * 10**18
    assert int(result.token_base_units) == rational.numerator // rational.denominator
    assert result.token_to_share_ratio == Decimal("1.000000000000000001")


def test_budget_below_minimum_token_unit_has_no_route():
    rows = load_data_fixture()
    token = rows["metadata"][1].model_copy(update={"decimals": 0})
    result = estimate(token, rows["tokens"][1], Decimal("50"), NOW, "DEMO")
    assert result.estimate_eligible is False
    assert result.estimated_token_quantity is None
    assert "BUDGET_BELOW_ONE_TOKEN_BASE_UNIT" in result.exclusion_reasons


@pytest.mark.parametrize(
    "data",
    [
        {"text": 50},
        {"text": "x" * 241},
        {"text": ""},
        {"text": "Buy $50 NVDA", "execution_mode": "LIVE"},
    ],
)
def test_ask_request_rejects_malformed_fields_and_execution_overrides(data):
    with pytest.raises(ValidationError):
        AskRequest.model_validate(data)


def test_provider_latency_expiring_price_or_ratio_blocks_selection(flow):
    layer = live_layer(flow.repository.database, two=False)
    calls = iter([NOW, NOW, NOW + timedelta(seconds=121)])
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: next(calls)))
    assert result.status == "NO_PROPOSAL" and result.selected is None
    assert "PRICE_EXPIRED_DURING_REQUEST" in result.representations[0].exclusion_reasons


def test_demonstrated_live_reference_is_independent_and_never_execution_approval(flow):
    layer = live_layer(flow.repository.database, two=False)
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.independent_equity.status == "AVAILABLE"
    assert result.independent_equity.source == "SYNTHETIC_TEST_INDEPENDENT"
    assert result.execution_ready is False and result.simulation_status == "UNAVAILABLE"


def test_duplicate_representations_reject_entire_proposal(flow):
    layer = live_layer(flow.repository.database, two=False)
    resolve = layer.discovery.resolve

    def duplicate(query):
        found = resolve(query)
        found["tokens"].append(found["tokens"][0])
        return found

    layer.discovery.resolve = duplicate
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.status == "NO_PROPOSAL" and result.representations == []
    assert result.route_selection_reason == "DUPLICATE_REPRESENTATION"


def test_missing_price_for_one_issuer_does_not_invent_or_select_it(flow):
    layer = live_layer(flow.repository.database)
    layer.records["tokens"][-1] = layer.records["tokens"][-1].model_copy(
        update={"token_price": None, "data_quality": "MISSING"}
    )
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.status == "DRY_RUN" and result.selected.issuer == "demo-issuer"
    rejected = next(r for r in result.representations if r.issuer == "test-second-issuer")
    assert rejected.token_price_usd is None and rejected.effective_cost_per_share_usd is None
    assert rejected.estimate_eligible is False


def test_exact_freshness_deadline_cannot_create_immediately_expired_proposal(flow):
    layer = live_layer(flow.repository.database, two=False)
    calls = iter([NOW, NOW, NOW + timedelta(seconds=120)])
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: next(calls)))
    assert result.status == "NO_PROPOSAL" and result.selected is None


def test_provider_cannot_remap_discovered_contract_to_different_issuer(flow):
    layer = live_layer(flow.repository.database, two=False)
    original = layer.rwa.profile
    layer.rwa.profile = lambda token: original(token).model_copy(update={"platform_id": "impostor"})
    result = propose(ExposureService(layer, flow.repository.database, clock=lambda: NOW))
    assert result.status == "NO_PROPOSAL" and result.selected is None
    assert result.route_selection_reason == "CONFLICTING_UNDERLYING"
