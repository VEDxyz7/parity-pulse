"""Walk-forward research only: every row included, no orders/positions/wallet dependency."""

import hashlib
from decimal import Decimal, localcontext
from pathlib import Path

from app.models.research import (
    ReplayCosts,
    ReplayRow,
    ReplayRun,
    ResearchEpisode,
    ResearchPolicy,
)
from app.services.opportunity import analytical_edge
from app.services.research_episodes import fingerprint
from app.services.research_model import HistoricalRetrieval, RollingOpeningModel, direction


class HistoricalReplay:
    def __init__(self, policy=None):
        policy = policy or ResearchPolicy()
        self.policy = ResearchPolicy.model_validate(policy.model_dump())
        self.retrieval = HistoricalRetrieval(self.policy)
        self.model = RollingOpeningModel(self.policy)

    def run(self, episodes, *, costs=None, provenance=()):
        records = [ResearchEpisode.model_validate(e.model_dump()) for e in episodes]
        if not records:
            raise ValueError("A nonempty explicit dataset is required")
        if len({e.decision.data_mode for e in records}) != 1:
            raise ValueError("Mixed replay modes forbidden")
        by_id = {}
        for e in records:
            previous = by_id.get(e.episode_id)
            if previous and fingerprint(previous) != fingerprint(e):
                raise ValueError("Conflicting immutable episode identity")
            by_id[e.episode_id] = e
        ordered = sorted(by_id.values(), key=lambda e: (e.decision.decision_at, e.episode_id))
        costs = {
            identifier: ReplayCosts.model_validate(c.model_dump())
            for identifier, c in (costs or {}).items()
        }
        if set(costs) - set(by_id):
            raise ValueError("Costs must belong to the replay dataset")
        dataset_digest = fingerprint([e.model_dump(mode="json") for e in ordered])
        # Bind the deployed research implementation as well as nominal policy. An upgrade
        # cannot silently overwrite an earlier run produced by different machinery.
        app = Path(__file__).resolve().parents[1]
        source_files = (
            "models/research.py",
            "services/research_episodes.py",
            "services/research_model.py",
            "services/research_replay.py",
            "services/opening_target.py",
            "services/opportunity.py",
        )
        implementation_digest = fingerprint(
            {name: hashlib.sha256((app / name).read_bytes()).hexdigest() for name in source_files}
        )
        run_id = fingerprint(
            {
                "dataset": dataset_digest,
                "implementation": implementation_digest,
                "policy": self.policy.model_dump(mode="json"),
                "costs": {k: v.model_dump(mode="json") for k, v in sorted(costs.items())},
                "provenance": sorted(provenance),
            }
        )
        rows = []
        for e in ordered:
            d = e.decision
            retrieval = self.retrieval.evaluate(ordered, d)
            prediction = self.model.predict(ordered, d)
            # Accuracy uses earlier genuine walk-forward predictions whose outcomes are known
            # now; never training-fit accuracy or results from future scorecards.
            measured = [
                r
                for r in rows
                if r.prediction.status == "READY"
                and by_id[r.episode_id].decision.scope == d.scope
                and by_id[r.episode_id].target.status == "AVAILABLE"
                and by_id[r.episode_id].target.available_at <= d.decision_at
            ]
            if measured:
                with localcontext() as context:
                    context.prec = 256
                    accuracy = Decimal(
                        sum(
                            r.prediction.direction
                            == direction(by_id[r.episode_id].target.opening_return)
                            for r in measured
                        )
                    ) / len(measured)
                prediction = prediction.model_copy(
                    update={
                        "historical_directional_accuracy": accuracy,
                        "accuracy_sample_count": len(measured),
                    }
                )
            reasons = list(d.reasons)
            adjustment = None
            net = None
            action = "DEFER"
            trust_state = d.trust.classification if d.trust else "INSUFFICIENT_EVIDENCE"
            cost = costs.get(e.episode_id)
            if prediction.status != "READY":
                reasons.append(prediction.reason)
            if retrieval.status != "SUFFICIENT":
                reasons.append("ANALOGUES_INSUFFICIENT")
            if prediction.status == "READY" and d.sample is not None:
                with localcontext() as context:
                    context.prec = 256
                    target_price = d.independent_equity.price or d.independent_equity.close
                    target_price *= 1 + prediction.predicted_return
                    effective = d.sample.features.effective_price_per_share_usd
                    adjustment = target_price - effective
                    if cost is not None and (
                        0 <= (d.decision_at - cost.observed_at).total_seconds() <= 120
                        and cost.available_at <= d.decision_at
                    ):
                        _, _, _, _, net = analytical_edge(
                            effective=effective,
                            target=target_price,
                            notional=cost.requested_notional,
                            slippage_bps=cost.slippage_bps,
                            fees=cost.fees,
                            gas=cost.gas,
                            buffer=cost.execution_buffer,
                        )
                    else:
                        reasons.append("ASOF_COSTS_UNAVAILABLE")
                if (
                    net is not None
                    and net > 0
                    and retrieval.status == "SUFFICIENT"
                    and trust_state == "LIKELY_INFORMATION"
                ):
                    action = "PROPOSE_RESEARCH_ONLY"
                elif net is not None and net <= 0:
                    reasons.append("NONPOSITIVE_COST_ADJUSTED_EDGE")
            if trust_state != "LIKELY_INFORMATION":
                reasons.append("TRUST_NOT_LIKELY_INFORMATION")
            # Existing RiskEngine contracts are explicitly DEMO-only. Do not cast real rows
            # into those contracts or invent historical balances/risk budgets/sizes.
            risk = "REJECTED_PRODUCTION_GATES" if action == "PROPOSE_RESEARCH_ONLY" else "NOT_READY"
            reasons.append("PRODUCTION_TRUST_OPPORTUNITY_GATES_BLOCKED")
            reasons.append("HISTORICAL_RISK_BUDGET_WALLET_STATE_UNAVAILABLE")
            outcome = {
                "status": e.target.status,
                "opening_return": str(e.target.opening_return)
                if e.target.opening_return is not None
                else None,
                "available_at": e.target.available_at.isoformat()
                if e.target.available_at
                else None,
                "pnl": None,  # Equity opening returns are not token execution proceeds.
                "pnl_reason": "NO_HISTORICAL_TOKEN_EXIT_EXECUTION_OR_COST_PROOF",
            }
            rows.append(
                ReplayRow(
                    episode_id=e.episode_id,
                    decision_id=d.decision_id,
                    decision_at=d.decision_at,
                    eligibility=d.data_quality,
                    trust_state=trust_state,
                    retrieval=retrieval,
                    prediction=prediction,
                    expected_adjustment_per_share=adjustment,
                    cost_adjusted_edge_usd=net,
                    hypothetical_decision=action,
                    hypothetical_risk=risk,
                    hypothetical_outcome=outcome,
                    reasons=tuple(sorted(set(reasons))),
                )
            )
        # Independent underlying openings only, even if different issuers share an outcome.
        measured = {}
        for r in rows:
            e = by_id[r.episode_id]
            if r.prediction.status == "READY" and e.target.status == "AVAILABLE":
                measured.setdefault((e.decision.ticker, e.target.opening_at), r)
        with localcontext() as context:
            context.prec = 256
            accuracy = (
                (
                    Decimal(
                        sum(
                            r.prediction.direction
                            == direction(by_id[r.episode_id].target.opening_return)
                            for r in measured.values()
                        )
                    )
                    / len(measured)
                )
                if measured
                else None
            )
        run = ReplayRun(
            run_id=run_id,
            dataset_digest=dataset_digest,
            implementation_digest=implementation_digest,
            policy=self.policy,
            data_mode=ordered[0].decision.data_mode,
            episode_count=len(ordered),
            eligible_episode_count=sum(
                e.decision.data_quality == "ELIGIBLE" and e.target.status == "AVAILABLE"
                for e in ordered
            ),
            prediction_count=sum(r.prediction.status == "READY" for r in rows),
            accuracy_sample_count=len(measured),
            directional_accuracy=accuracy,
            rows=tuple(rows),
            episodes=tuple(ordered),
            costs=costs,
            provenance=tuple(sorted(provenance)),
        )
        # Existing Trust analogue maps intentionally serialize Decimal values as strings.
        # Normalize that legacy opaque payload once so persisted/reloaded runs are identical.
        return ReplayRun.model_validate_json(run.model_dump_json())
