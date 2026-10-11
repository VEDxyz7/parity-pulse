"""One offline, deterministic scenario adapter, never a provider or production repository.

All Trust/Opportunity/Risk/route/quote/preparation/simulation decisions are delegated.
Only presentation histories, assumptions and descriptive portfolio/evaluation arithmetic
live here. No Settings, production database, HTTP client, signer or execution service.
"""

from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal, localcontext
from threading import RLock
from uuid import NAMESPACE_URL, uuid5

from app.agents.opportunity_agent import ranked
from app.agents.schemas import Candidate
from app.models.demo_execution import digest
from app.models.demo_opportunity import DemoOpportunityFixture
from app.models.demo_sandbox import DemoTrustDataset
from app.models.opportunity import OpportunityDecision
from app.models.presentation import (
    EvaluationRecord,
    Holding,
    PresentationAnalysis,
    PresentationProvenance,
    PresentationScan,
    PresentationWorkspace,
    PricePoint,
    ScanRequest,
    ScenarioRequest,
)
from app.models.routing import RouteIdentity, RouteInput, RoutePolicy
from app.services.demo_opportunity import DemoOpportunityFlow
from app.services.demo_preparation import DemoPreparationFlow
from app.services.demo_sandbox import DemoTrustSandbox
from app.services.normalization import comparable_economics
from app.services.routing import RoutingService

D = Decimal
# Explicit fictional representations; no real issuer/contract or executable route is asserted.
UNIVERSE = {"NVDA": ("Nvidia", D("100")), "AAPL": ("Apple", D("200"))}
REPRESENTATIONS = {"atlas": ("Atlas model", D("0.5")), "meridian": ("Meridian model", D("1"))}
PRESETS = {
    "normal": "steady",
    "above": "steady",
    "below": "steady",
    "low-liquidity": "thin-move",
    "news": "supported-move",
}
ASSUMPTIONS = [
    ("Fixed modeled regular session: 6 October 2026, 16:00 UTC. Prices are not current quotes."),
    ("Atlas and Meridian are fictional representations with scenario-only identities and ratios."),
    "Historical episodes and news are modeled inputs, excluded from production evidence.",
    (
        "Target share value is a 6% scenario assumption, not a forecast or "
        "validated predictive edge."
    ),
    ("Existing scenario risk limits apply. Quotes and local simulation cannot authorize a trade."),
]


class PresentationService:
    capacity = 64

    def __init__(self):
        self.base = DemoTrustSandbox()
        self.router = RoutingService()
        self.saved = OrderedDict()
        self.analyses = OrderedDict()
        self.lock = RLock()
        self._workspace = None

    def dataset(self, request):
        key = PRESETS[request.preset]
        raw = self.base.datasets[key].model_dump(mode="json")
        company, reference = UNIVERSE[request.ticker]
        issuer, ratio = REPRESENTATIONS[request.representation]
        original_ratio = D(raw["token"]["record"]["token_to_share_ratio"])
        scale = reference / D("100")
        price_scale = scale * ratio / original_ratio
        contract = f"demo:presentation:{request.ticker}:{request.representation}"
        platform = f"presentation-{request.representation}"
        symbol = f"{request.ticker}-{request.representation.upper()}"

        # Map every as-of sample/episode to the same isolated identity, not today's real ratio.
        def remap(value):
            if isinstance(value, list):
                return [remap(v) for v in value]
            if not isinstance(value, dict):
                return value
            out = {}
            for k, v in value.items():
                if k == "ticker":
                    v = request.ticker
                elif k == "company_name":
                    v = company + " (presentation)"
                elif k in {"platform_id", "issuer"} and isinstance(v, str):
                    v = platform
                elif k == "contract":
                    v = contract
                elif k == "token_symbol":
                    v = symbol
                elif k in {"token_to_share_ratio", "ratio"}:
                    v = str(ratio)
                elif k in {"effective_price_per_share_usd"}:
                    v = str(D(v) * scale)
                elif k == "comparable_token_value_usd":
                    v = str(D(v) * price_scale)
                elif k in {"sample_id", "episode_id", "provider_identifier"}:
                    v = f"presentation:{request.ticker}:{request.representation}:{v}"
                out[k] = remap(v)
            return out

        raw = remap(raw)
        for n in raw["news"]:
            n["record"]["headline"] = (
                request.ticker + " raises guidance in modeled earnings scenario"
            )
        token_price = D(raw["price"]["record"]["token_price"]) * price_scale
        if request.preset == "above":
            token_price = reference * ratio * D("1.03")
        if request.preset == "below":
            token_price = reference * ratio * D("0.97")
        # Explicit small issuer premium allows real comparisons without arbitrary rank weights.
        if request.representation == "meridian":
            token_price *= D("1.004")
        raw["price"]["record"]["token_price"] = str(request.token_price or token_price)
        eq = request.equity_price or reference
        raw["equity"]["record"].update(price=str(eq), close=str(eq))
        if request.liquidity is not None:
            raw["price"]["record"]["provider_metadata"]["liquidity"] = str(request.liquidity)
        return DemoTrustDataset.model_validate(raw), issuer

    def analyze(self, request: ScenarioRequest):
        identity = digest(request)
        with self.lock:
            if identity in self.analyses:
                return self.analyses[identity]
            with localcontext() as ctx:
                ctx.prec = 64
                result = self._analyze(request)
            self.analyses[identity] = result
            while len(self.analyses) > self.capacity:
                self.analyses.popitem(last=False)
            return result

    def _analyze(self, request):
        dataset, issuer_name = self.dataset(request)
        key = dataset.scenario_id
        sandbox = DemoTrustSandbox()
        sandbox.datasets[key] = dataset
        sandbox.hashes[key] = digest(dataset)
        identity = digest(request)
        result = sandbox.assess(
            key, run_id="presentation-1", request_id=identity, correlation_id=identity
        )
        flow = DemoOpportunityFlow(sandbox, clock=lambda: 0)
        raw = flow.fixture.model_dump(mode="json")
        token, price, equity = dataset.token.record, dataset.price.record, dataset.equity.record
        raw["economics"].update(
            ticker=token.ticker,
            issuer=token.platform_id,
            contract=token.contract,
            target_share_price_usd=str(equity.price * D("1.06")),
            requested_notional_usd=str(min(request.budget * D("0.8"), D("50"))),
            fees_usd=str(request.fees),
            slippage_bps=str(request.slippage_bps),
        )
        raw["risk_inputs"].update(
            budget_usd=str(request.budget), risk_budget_usd=str(request.risk_budget)
        )
        flow.fixture = DemoOpportunityFixture.model_validate(raw)
        flow.fixture_hash = digest(flow.fixture)
        result = result.model_copy(
            update={
                "assessment": result.assessment.model_copy(
                    update={"assessment_id": uuid5(NAMESPACE_URL, "presentation:" + identity)}
                )
            }
        )
        flow.remember(result)
        opportunity = flow.opportunity(result.assessment.assessment_id)
        if request.window == "reopening":
            rejected = OpportunityDecision.model_validate(
                {
                    **opportunity.opportunity.model_dump(),
                    "status": "REJECTED",
                    "action": "NONE",
                    "reason_codes": [
                        *opportunity.opportunity.reason_codes,
                        "OPENING_MODEL_EVIDENCE_REQUIRED",
                    ],
                }
            )
            opportunity = opportunity.model_copy(update={"opportunity": rejected})
            flow._save(flow.opportunities, rejected.opportunity_id, opportunity)
        risk = flow.risk(opportunity.opportunity.opportunity_id)
        prep_flow = DemoPreparationFlow(flow)
        quote = preparation = simulation = None
        # Existing opening-model evidence is insufficient; never pass a regular result
        # off as reopening.
        if request.window == "regular" and risk.risk.status == "PASS":
            quote = prep_flow.quote(risk.risk.risk_id)
            if quote.quote is not None:
                preparation = prep_flow.prepare(quote.quote.quote_id)
                if preparation.transaction is not None:
                    simulation = prep_flow.simulate(preparation.transaction.transaction_id)
        economics = comparable_economics(
            price.token_price, token.token_to_share_ratio, equity.price
        )
        liq = D(price.provider_metadata["liquidity"])
        slippage = request.budget * request.slippage_bps / D("10000")
        costs = request.fees + D("0.05") + slippage
        quantity = max(D("0"), request.budget - costs) / price.token_price
        row = result.assessment.representations[0]
        explanation = {
            "NORMAL": (
                "Market alignment is within the historical baseline. Wait for a stronger signal."
            ),
            "LIKELY_NOISE": (
                "Thin liquidity weakens the price move. Preserve capital and stand down."
            ),
            "LIKELY_INFORMATION": (
                "Persistent movement, volume and modeled event context support further analysis."
            ),
            "INSUFFICIENT_EVIDENCE": (
                "These assumptions do not provide enough aligned evidence for a decision."
            ),
        }[row.classification]
        if risk.risk.status == "FAIL" and row.classification == "LIKELY_INFORMATION":
            explanation += " The requested size or costs do not pass the risk mandate."
        if request.window == "reopening":
            explanation += (
                " Reopening proposals need independent opening-model evidence; this "
                "regular-session study stands down."
            )
        history = []
        for i in range(48):
            # Scenario path is defined as a deterministic bridge, not empirical price history.
            progress = D(i) / D(47)
            eq = equity.price * (D("0.992") + progress * D("0.008"))
            p = price.token_price * (D("0.985") + progress * D("0.015"))
            history.append(
                PricePoint(
                    at=dataset.decision_at - timedelta(minutes=47 - i),
                    token=p,
                    equity=eq,
                    effective=p / token.token_to_share_ratio,
                )
            )
        return PresentationAnalysis(
            id=identity,
            inputs=request,
            provenance=self.provenance(),
            company=UNIVERSE[request.ticker][0],
            issuer_name=issuer_name,
            token_symbol=token.token_symbol,
            contract=token.contract,
            share_ratio=token.token_to_share_ratio,
            token_price=price.token_price,
            equity_price=equity.price,
            effective_cost=economics["effective_price_per_share_usd"],
            deviation=economics["deviation"],
            liquidity=liq,
            volume=price.volume,
            token_quantity=quantity,
            share_exposure=quantity * token.token_to_share_ratio,
            estimated_costs=costs,
            history=history,
            trust=result.assessment,
            opportunity=opportunity.opportunity,
            risk=risk.risk,
            route=opportunity.route_decision,
            quote=quote,
            preparation=preparation,
            simulation=simulation,
            explanation=explanation,
        )

    def provenance(self):
        return PresentationProvenance(
            as_of=self.base.datasets["steady"].decision_at, assumptions=ASSUMPTIONS
        )

    def save(self, result):
        with self.lock:
            self.saved[result.id] = result
            self.saved.move_to_end(result.id)
            while len(self.saved) > self.capacity:
                self.saved.popitem(last=False)
        return result

    def inspect(self, identifier):
        with self.lock:
            if identifier not in self.saved:
                raise LookupError("Scenario expired")
            return self.saved[identifier]

    def scan(self, request: ScanRequest):
        rows = [
            self.analyze(
                ScenarioRequest(
                    ticker=t,
                    representation=r,
                    preset="news" if t == "NVDA" else "normal",
                    budget=request.budget,
                    risk_budget=request.risk_budget,
                    window=request.window,
                )
            )
            for t in sorted(set(request.universe))
            for r in REPRESENTATIONS
        ]
        candidates = []
        for item in rows:
            row = item.trust.representations[0]
            actionable = (
                item.opportunity.status == "ACTIONABLE"
                and item.risk.status == "PASS"
                and request.window == "regular"
            )
            candidates.append(
                Candidate(
                    candidate_id=item.id,
                    ticker=item.inputs.ticker,
                    issuer=row.issuer,
                    chain_id=row.chain_id,
                    contract=row.contract,
                    data_mode="DEMO",
                    observed_at=item.provenance.as_of,
                    available_at=item.provenance.as_of,
                    trust=row.classification,
                    confidence=row.confidence,
                    deviation=item.deviation,
                    volume_percentile=(
                        row.baseline.volume_percentile / 100
                        if row.baseline.volume_percentile is not None
                        else None
                    ),
                    effective_cost=item.effective_cost,
                    liquidity_usd=item.liquidity,
                    slippage_bps=item.inputs.slippage_bps,
                    net_edge_usd=item.opportunity.economics.net_hypothetical_edge_usd
                    if item.opportunity.economics
                    else None,
                    baseline_samples=row.baseline.sample_count,
                    analogue_count=row.analogues.retrieved_sample_count,
                    eligibility="ELIGIBLE" if actionable else "REJECTED",
                    tradable=True,
                    evidence_refs=(),
                )
            )
        ranks = {
            c.candidate_id: i for i, c in enumerate(ranked(candidates, self.provenance().as_of), 1)
        }
        rows = [self.save(i.model_copy(update={"rank": ranks.get(i.id)})) for i in rows]
        rows.sort(
            key=lambda i: (i.rank is None, i.rank or 0, i.inputs.ticker, i.inputs.representation)
        )
        return PresentationScan(
            provenance=self.provenance(),
            request=request,
            candidates=rows,
            ranking=(
                "Confidence → net edge → analogue count → baseline count → liquidity → "
                "effective cost → identity"
            ),
            explanation=(
                "Existing lexicographic scan policy. Regular-session scenario targets are"
                " assumptions; reopening proposals remain pending evidence."
            ),
        )

    def exposure(self, ticker, budget):
        # Same shared router; an indicative comparison never inherits Opportunity
        # execution permission.
        rows = [
            self.analyze(
                ScenarioRequest(
                    ticker=ticker,
                    representation=r,
                    preset="news" if ticker == "NVDA" else "normal",
                    budget=budget,
                )
            )
            for r in REPRESENTATIONS
        ]
        inputs = []
        for item in rows:
            at = item.provenance.as_of
            inputs.append(
                RouteInput(
                    identity=RouteIdentity(
                        underlying=ticker,
                        issuer=f"presentation-{item.inputs.representation}",
                        chain_id="DEMO",
                        contract=item.contract,
                        token=item.token_symbol,
                    ),
                    data_mode="DEMO",
                    token_price_usd=item.token_price,
                    token_to_share_ratio=item.share_ratio,
                    price_source="PRESENTATION_SCENARIO",
                    price_timestamp=at,
                    price_quality="DEMO",
                    ratio_source="PRESENTATION_SCENARIO",
                    ratio_observed_at=at,
                    ratio_source_timestamp=at,
                    market_state="regular",
                    tradable=True,
                    liquidity_usd=item.liquidity,
                    liquidity_status="AVAILABLE",
                    liquidity_source="PRESENTATION_SCENARIO",
                    liquidity_timestamp=at,
                    fees_usd=item.inputs.fees,
                    gas_usd=D("0.05"),
                    slippage_bps=item.inputs.slippage_bps,
                    cost_status="AVAILABLE",
                    cost_source="PRESENTATION_SCENARIO",
                    cost_timestamp=at,
                )
            )
        return self.router.decide(
            ticker,
            budget,
            inputs,
            mode="DEMO",
            now=self.provenance().as_of,
            policy=RoutePolicy(require_costs=True),
        )

    def workspace(self):
        with self.lock:
            if self._workspace is not None:
                return self._workspace
            assets = [
                self.analyze(
                    ScenarioRequest(
                        ticker=t, representation=r, preset="news" if t == "NVDA" else "normal"
                    )
                )
                for t in UNIVERSE
                for r in REPRESENTATIONS
            ]
            for item in assets:
                self.save(item)
            # Explicit modeled quantities and acquisition assumptions, never actual
            # account holdings.
            holdings = []
            specs = [
                (assets[0], D("6"), D("48"), D("0.40")),
                (assets[1], D("2"), D("97"), D("0.25")),
                (assets[2], D("3"), D("98"), D("0.35")),
            ]
            total = sum(a.token_price * qty for a, qty, _, _ in specs)
            for a, qty, basis, target in specs:
                value, cost = a.token_price * qty, basis * qty
                weight = value / total
                holdings.append(
                    Holding(
                        ticker=a.inputs.ticker,
                        issuer=a.issuer_name,
                        sector="Semiconductors"
                        if a.inputs.ticker == "NVDA"
                        else "Consumer technology",
                        quantity=qty,
                        share_exposure=qty * a.share_ratio,
                        cost_basis=cost,
                        value=value,
                        pnl=value - cost,
                        weight=weight,
                        target_weight=target,
                        drift=weight - target,
                        suggested_notional=total * target - value,
                    )
                )
            evaluations = []
            for ticker in UNIVERSE:
                dataset, _ = self.dataset(ScenarioRequest(ticker=ticker, preset="news"))
                for wrapped in dataset.baseline_episodes:
                    ep = wrapped.record
                    # Explicit hypothesis, evaluated against each fixture's
                    # recorded subsequent outcome.
                    prediction = (
                        "REVERSED"
                        if ep.sample.features.absolute_deviation <= D("0.01")
                        else "PERSISTED"
                    )
                    evaluations.append(
                        EvaluationRecord(
                            id=ep.episode_id,
                            ticker=ticker,
                            at=ep.ended_at,
                            prediction=prediction,
                            outcome=ep.outcome,
                            correct=prediction == ep.outcome,
                            initial_deviation=ep.sample.features.deviation,
                            final_deviation=ep.outcome_deviation,
                            evidence=(
                                f"{ep.observation_count} modeled observations; "
                                f"outcome available {ep.outcome_available_at.isoformat()}"
                            ),
                        )
                    )
            correct = sum(e.correct for e in evaluations)
            cost = sum(h.cost_basis for h in holdings)
            asset_weights = [sum(h.weight for h in holdings if h.ticker == t) for t in UNIVERSE]
            self._workspace = PresentationWorkspace(
                provenance=self.provenance(),
                assets=assets,
                holdings=holdings,
                portfolio_value=total,
                portfolio_cost=cost,
                portfolio_pnl=total - cost,
                concentration=max(asset_weights),
                stress_loss=total * D("0.02"),
                evaluations=evaluations,
                evaluation_count=len(evaluations),
                correct_count=correct,
                accuracy=D(correct) / len(evaluations) if evaluations else None,
            )
            return self._workspace
