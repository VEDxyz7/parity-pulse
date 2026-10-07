"""Existing dynamic discovery and captured Trust adapters. No new provider subsystem."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from app.agents.adapters import DemoEvidenceAdapter
from app.clients.common import ProviderError
from app.models.data import NewsEvent
from app.models.opportunity_scan import CatalogRejection, ScanCosts, ScanSnapshot
from app.models.risk import OpportunityRiskContext
from app.providers.demo import DemoRWAProvider
from app.services.asset_discovery import AssetDiscoveryService
from app.services.demo_opportunity import DemoOpportunityFlow
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.opportunity_scan import candidate_id
from app.services.research_episodes import fingerprint


class DemoScanSource:
    """Reuse the existing synthetic fixtures, without modifying or enlarging their dataset."""

    def capture(self, request, policy):
        scenario = request.demo_scenario or "supported-move"
        sandbox = DemoTrustSandbox()
        dataset = sandbox.datasets[scenario]
        records = {"metadata": [dataset.token.record], "issuers": [dataset.issuer.record]}
        discovery = AssetDiscoveryService(DemoRWAProvider(records), mode="DEMO", chain="DEMO")
        assets, issuers, tokens = discovery.universe()
        bundle = DemoEvidenceAdapter().load(scenario)
        assessment = type(bundle.assessment).model_validate(
            {
                **bundle.assessment.model_dump(),
                "assessment_id": uuid5(NAMESPACE_URL, "phase7-existing-demo:" + scenario),
            }
        )
        fixture = DemoOpportunityFlow(sandbox).fixture
        p, i, e = fixture.risk_policy, fixture.risk_inputs, fixture.economics
        context = OpportunityRiskContext(
            data_mode="DEMO",
            observed_at=e.observed_at,
            source="EXISTING_SYNTHETIC_DEMO_RISK_FIXTURE",
            stress_adverse_move_fraction=i.adverse_move_fraction,
            wallet_available_usd=i.wallet_available_usd,
            existing_exposure_usd=i.existing_exposure_usd,
            daily_loss_usd=i.daily_loss_usd,
            trades_today=i.trades_today,
            last_trade_at=i.last_trade_at,
            system_resolved=True,
            wallet_allowed=True,
            **{
                k: getattr(p, k)
                for k in (
                    "max_position_usd",
                    "max_portfolio_exposure_usd",
                    "max_daily_loss_usd",
                    "max_risk_budget_usd",
                    "max_trades_per_day",
                    "max_liquidity_fraction",
                    "cooldown_seconds",
                    "min_confidence",
                    "min_liquidity_usd",
                    "min_liquidity_percentile",
                    "max_slippage_bps",
                    "min_net_edge_usd",
                )
            },
        )
        costs = ScanCosts(
            observed_at=e.observed_at,
            available_at=e.observed_at,
            data_mode="DEMO",
            source="EXISTING_SYNTHETIC_DEMO_ECONOMICS",
            quoted_notional_usd=e.requested_notional_usd,
            slippage_bps=e.slippage_bps,
            fees_usd=e.fees_usd,
            gas_usd=e.gas_usd,
            execution_buffer_usd=e.execution_buffer_usd,
            route_available=True,
        )
        return ScanSnapshot(
            data_mode="DEMO",
            captured_at=bundle.decision_at,
            assets=tuple(assets),
            tokens=tuple(tokens),
            assessments=(assessment,),
            articles=bundle.articles,
            costs={candidate_id(tokens[0]): costs},
            demo_economics=e,
            demo_risk_inputs=i,
            demo_risk_policy=p,
            risk_context=context,
            discovery_source="EXISTING_DEMO_DISCOVERY",
            discovery_digest=fingerprint(
                sorted(
                    [r.model_dump(mode="json") for r in (*assets, *issuers, *tokens)],
                    key=fingerprint,
                )
            ),
        )


class DataLayerScanSource:
    """Read-only providers through existing DataLayer/TrustService. No DEMO fallback.

    Current live cost, route and wallet previews are unverified: explicitly absent, never zero.
    Phase 5 captured inputs may be supplied by a host-controlled point-in-time loader, not by
    an API client. The source never starts backfill, execution or historical calibration.
    """

    def __init__(self, layer, trust, *, clock=None, research_loader=None):
        self.layer, self.trust = layer, trust
        self.clock = clock or (lambda: datetime.now(UTC))
        self.research_loader = research_loader

    def capture(self, request, policy):
        mode = "DEMO" if self.layer.mode == "DEMO" else "LIVE_READ_ONLY"
        if request.demo_scenario is not None:
            raise ValueError("Scenario selection is restricted to the DEMO runtime")
        blockers = []
        assets, tokens, assessments, articles, issuers = [], [], [], [], []
        try:
            assets, issuers, tokens = self.layer.discovery.universe()
        except ProviderError:
            blockers.append("DISCOVERY_UNAVAILABLE")
        rejected = tuple(
            CatalogRejection.model_validate(r)
            for r in getattr(self.layer.rwa, "catalog_rejections", ())
        )
        if (
            len(tokens) + len(rejected) > policy.max_representations
            or len(assets) > policy.max_stocks
        ):
            # Retain all within supported audit bounds, but NEVER truncate to favorable winners.
            if len(tokens) > 500 or len(rejected) > 500 or len(assets) > 100:
                raise ValueError("Unsupported full-universe size; scan refused without truncation")
            blockers.append("UNIVERSE_BOUND_EXCEEDED")
        if not blockers:
            tickers = sorted(
                {
                    t.ticker
                    for t in tokens
                    if not request.universe.reasons(t)
                    and t.asset_type == 1
                    and t.open_state is True
                    and t.reason_code
                    not in {"ASSET_PAUSED", "ASSET_LIMITED", "UNSUPPORTED", "MARKET_MAINTENANCE"}
                }
            )
            for ticker in tickers:
                assessments.append(
                    self.trust.assess(
                        ticker,
                        run_id="opportunity-capture",
                        request_id="opportunity-capture",
                        correlation_id=request.correlation_id or "opportunity-capture",
                    )
                )
                articles.extend(
                    self.layer.repository.list(
                        NewsEvent, mode=self.layer.mode, ticker=ticker, limit=10
                    )
                )
        at = self.clock()
        research = (
            tuple(self.research_loader(tuple(assessments), at)) if self.research_loader else ()
        )
        return ScanSnapshot(
            data_mode=mode,
            captured_at=at,
            assets=tuple(assets),
            tokens=tuple(tokens),
            assessments=tuple(assessments),
            articles=tuple(articles),
            research=research,
            catalog_rejections=rejected,
            blockers=tuple(blockers),
            discovery_source="EXISTING_DEMO_DISCOVERY"
            if mode == "DEMO"
            else "BINANCE_RWA_DISCOVERY",
            discovery_digest=fingerprint(
                sorted(
                    [r.model_dump(mode="json") for r in (*assets, *issuers, *tokens, *rejected)],
                    key=fingerprint,
                )
            ),
        )
