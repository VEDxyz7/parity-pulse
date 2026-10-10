"""One deterministic router for actual discovered representations and synthetic inputs.

Filters precede economics. Exact rational ordering avoids rounding-driven winners.
Unknown costs never become zero and cannot enter an all-in or Opportunity route.
"""

import hashlib
import json
from datetime import timedelta
from decimal import ROUND_CEILING, Decimal, localcontext
from fractions import Fraction
from uuid import NAMESPACE_URL, uuid5

from pydantic import TypeAdapter

from app.models.data import utc
from app.models.opportunity import Price
from app.models.routing import RouteCandidate, RouteDecision, RouteInput, RoutePolicy
from app.services.normalization import effective_price_per_share


SESSION_STATES = {"regular", "premarket", "postmarket", "open"}
CLOSED_STATES = {"offhours", "overnight", "closed"}


def digest(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def artifact_id(kind, fingerprint):
    return uuid5(NAMESPACE_URL, f"parity:routing:{kind}:{fingerprint}")


def identity_key(row):
    i = row.identity
    return i.issuer, i.chain_id, i.contract, i.token


def display(value):
    with localcontext() as context:
        context.prec = 256
        result = Decimal(value.numerator) / Decimal(value.denominator)
        return result.quantize(Decimal("1e-18"), rounding=ROUND_CEILING)


class RoutingService:
    def decide(self, underlying, notional, inputs, *, mode, now, policy=None):
        now = utc(now)
        policy = RoutePolicy.model_validate((policy or RoutePolicy()).model_dump())
        inputs = [RouteInput.model_validate(i.model_dump()) for i in inputs]
        if notional is not None:
            # Revalidate financial bounds and mode even for service-only callers.
            notional = TypeAdapter(Price).validate_python(notional)
        if mode not in {"DEMO", "LIVE"}:
            raise ValueError("Explicit mode required")
        # A contract on one chain is one representation, even if labels disagree.
        seen = [(i.identity.chain_id, i.identity.contract) for i in inputs]
        duplicate = len(set(seen)) != len(seen)
        mixed = any(i.data_mode != mode or i.identity.underlying != underlying for i in inputs)
        candidates, values = [], {}
        for row in sorted(inputs, key=identity_key):
            reasons = list(row.normalization_reasons)
            limitations = []
            if duplicate or mixed:
                reasons.append("DUPLICATE_OR_MIXED_UNDERLYING_MODE")
            if underlying is None or notional is None:
                reasons.append("UNRESOLVED_REQUEST")
            if not row.supported or not row.normalization_eligible:
                reasons.append("UNSUPPORTED_OR_INVALID_NORMALIZATION")
            if row.token_price_usd is None:
                reasons.append("TOKEN_PRICE_UNAVAILABLE")
            # "open": issuer reports openState=True/TRADING without a session (24/7 AMM tokens).
            # Closed-underlying states trade only on on-chain pools and only when the policy
            # explicitly allows it (live wallet rebalancing over weekends/off-hours).
            states = SESSION_STATES | (CLOSED_STATES if policy.allow_closed_underlying else set())
            if row.tradable is not True or row.market_state not in states:
                reasons.append("REPRESENTATION_NOT_TRADABLE")
            elif row.market_state in CLOSED_STATES:
                limitations.append("UNDERLYING_MARKET_CLOSED")
            if row.route_available is False or row.route_support == "UNAVAILABLE":
                reasons.append("ROUTE_UNAVAILABLE")
            if policy.purpose == "OPPORTUNITY" and (
                row.route_available is not True
                or row.route_support
                not in {"SYNTHETIC_DEMO_PREPARATION", "VERIFIED_PROVIDER_ROUTE"}
            ):
                reasons.append("REQUIRED_ANALYTICAL_ROUTE_UNAVAILABLE")
            if mode == "LIVE":
                if (
                    row.price_quality != "LIVE"
                    or not self._fresh(row.price_timestamp, now)
                    or not self._fresh(row.ratio_observed_at, now)
                ):
                    reasons.append("PRICE_OR_RATIO_NOT_FRESH_VERIFIED")
                if (
                    row.identity.chain_id == "DEMO"
                    or row.identity.contract.startswith("demo:")
                    or row.route_support == "SYNTHETIC_DEMO_PREPARATION"
                ):
                    reasons.append("SYNTHETIC_INPUT_IN_LIVE")
            elif row.price_quality != "DEMO":
                reasons.append("NON_DEMO_PRICE_IN_DEMO")
            liquidity = self._state(
                row.liquidity_status,
                row.liquidity_usd is not None,
                row.liquidity_source,
                row.liquidity_timestamp,
                now,
            )
            costs = self._state(
                row.cost_status,
                all(v is not None for v in (row.fees_usd, row.gas_usd, row.slippage_bps)),
                row.cost_source,
                row.cost_timestamp,
                now,
            )
            if liquidity == "AVAILABLE":
                if row.liquidity_usd <= 0 or (
                    policy.min_liquidity_usd is not None
                    and row.liquidity_usd < policy.min_liquidity_usd
                ):
                    reasons.append("INSUFFICIENT_LIQUIDITY")
            else:
                limitations.append("LIQUIDITY_" + liquidity)
                if policy.require_liquidity:
                    reasons.append("REQUIRED_LIQUIDITY_" + liquidity)
            if costs != "AVAILABLE":
                limitations.append("COSTS_" + costs)
                if policy.require_costs:
                    reasons.append("REQUIRED_COSTS_" + costs)
            elif policy.max_slippage_bps is not None and row.slippage_bps > policy.max_slippage_bps:
                reasons.append("SLIPPAGE_LIMIT")
            trust_fresh = (
                self._fresh(row.trust_timestamp, now)
                and bool(row.trust_source)
                and row.trust_assessment_id is not None
            )
            if row.trust_state == "LIKELY_NOISE":
                reasons.append("TRUST_LIKELY_NOISE")
            if policy.require_trust and (
                not trust_fresh
                or row.trust_state
                not in (
                    {"LIKELY_INFORMATION"}
                    if policy.purpose == "OPPORTUNITY"
                    else {"NORMAL", "LIKELY_INFORMATION"}
                )
            ):
                reasons.append("TRUST_REQUIREMENT_FAILED")
            if row.trust_state == "UNKNOWN" or not trust_fresh:
                limitations.append("TRUST_NOT_CURRENTLY_VERIFIED")
            if not policy.require_trust and policy.purpose != "OPPORTUNITY":
                limitations.append("TRUST_NOT_EVALUATED")
            risk_fresh = (
                self._fresh(row.risk_timestamp, now)
                and bool(row.risk_source)
                and row.risk_id is not None
            )
            if row.risk_state == "FAIL":
                reasons.extend(["RISK_FAILED", *row.risk_reason_codes])
            if policy.require_risk and (
                row.risk_state != "PASS" or not risk_fresh or row.risk_max_notional_usd is None
            ):
                reasons.append("RISK_REQUIREMENT_FAILED")
            if (
                row.risk_state == "PASS"
                and row.risk_max_notional_usd is not None
                and notional is not None
                and notional > row.risk_max_notional_usd
            ):
                reasons.append("RISK_NOTIONAL_LIMIT")
            if row.route_available is None:
                limitations.append("PROVIDER_EXECUTION_ROUTE_NOT_VERIFIED")
            effective = all_in = estimated = None
            exact = None
            if row.token_price_usd is not None:
                effective = effective_price_per_share(
                    row.token_price_usd, row.token_to_share_ratio, presentation=True
                )
                exact = Fraction(row.token_price_usd) / Fraction(row.token_to_share_ratio)
                if costs == "AVAILABLE" and notional is not None:
                    fixed = Fraction(row.fees_usd) + Fraction(row.gas_usd)
                    additional = Fraction(notional) * Fraction(row.slippage_bps) / 10000 + fixed
                    estimated = display(additional)
                    all_in = display(exact * (1 + additional / Fraction(notional)))
                    all_in_exact = exact * (1 + additional / Fraction(notional))
                else:
                    all_in_exact = None
            else:
                all_in_exact = None
            key = artifact_id("route-candidate", digest(row.identity))
            values[key] = (exact, all_in_exact)
            candidates.append(
                RouteCandidate(
                    candidate_id=key,
                    inputs=row,
                    eligible=not reasons,
                    rejection_reasons=list(dict.fromkeys(reasons)),
                    limitations=limitations,
                    effective_cost_per_share_usd=effective,
                    estimated_costs_usd=estimated,
                    all_in_cost_per_share_usd=all_in,
                    ranking_cost_per_share_usd=None,
                    liquidity_state=liquidity,
                    cost_state=costs,
                    trust_state=row.trust_state,
                    tradability="TRADABLE"
                    if row.tradable is True
                    and row.market_state
                    in SESSION_STATES
                    | (CLOSED_STATES if policy.allow_closed_underlying else set())
                    else "UNKNOWN"
                    if row.tradable is None
                    else "NOT_TRADABLE",
                )
            )
        eligible = [c for c in candidates if c.eligible]
        complete = bool(eligible) and all(c.cost_state == "AVAILABLE" for c in eligible)
        basis = "ALL_IN_ESTIMATE" if complete else "TOKEN_PRICE_ONLY" if eligible else "NONE"
        index = 1 if complete else 0
        ranked = sorted(
            eligible, key=lambda c: (values[c.candidate_id][index], *identity_key(c.inputs))
        )
        ranks = {c.candidate_id: n for n, c in enumerate(ranked, 1)}
        candidates = [
            c.model_copy(
                update={
                    "rank": ranks.get(c.candidate_id),
                    "ranking_cost_per_share_usd": display(values[c.candidate_id][index])
                    if c.eligible
                    else None,
                }
            )
            for c in candidates
        ]
        selected = next((c for c in candidates if c.rank == 1), None)
        expiry = now + timedelta(seconds=30)
        if selected is not None:
            if mode == "LIVE":
                expiry = min(
                    expiry,
                    selected.inputs.price_timestamp + timedelta(seconds=120),
                    selected.inputs.ratio_observed_at + timedelta(seconds=120),
                )
            for required, stamp in [
                (policy.require_liquidity, selected.inputs.liquidity_timestamp),
                (policy.require_costs, selected.inputs.cost_timestamp),
                (policy.require_trust, selected.inputs.trust_timestamp),
                (policy.require_risk, selected.inputs.risk_timestamp),
            ]:
                if required and stamp is not None:
                    expiry = min(expiry, stamp + timedelta(seconds=120))
        explanation = (
            (
                (
                    "Lowest exact all-in estimated USD cost per real share "
                    "after eligibility filters; "
                    "fees, gas and slippage included. "
                    "Deterministic issuer/chain/contract/token tie-break."
                )
                if complete
                else (
                    "Lowest exact token-price USD cost per real share after eligibility filters; "
                    "deterministic issuer/chain/contract/token tie-break. "
                    "Missing costs remain unknown: "
                    "not an all-in cost comparison or trade authorization."
                )
            )
            if selected
            else (
                "No candidate satisfies the stated routing policy. "
                "No trade or execution is authorized."
            )
        )
        payload = dict(
            underlying=underlying,
            requested_notional_usd=notional,
            data_mode=mode,
            timestamp=now,
            valid_until=expiry,
            policy=policy,
            status="ROUTE_SELECTED" if selected else "NO_ROUTE",
            selected_representation=selected.inputs.identity if selected else None,
            issuer=selected.inputs.identity.issuer if selected else None,
            candidates=candidates,
            selected_candidate=selected,
            ranking_basis=basis,
            reason_codes=["MINIMUM_ELIGIBLE_EFFECTIVE_COST", "IDENTITY_TIE_BREAK"]
            if selected
            else ["NO_ELIGIBLE_ROUTE"],
            explanation=explanation,
        )
        # Sorted inputs and fixed time give stable IDs independent of discovery order.
        encoded = {
            k: v.model_dump(mode="json")
            if hasattr(v, "model_dump")
            else [x.model_dump(mode="json") for x in v]
            if isinstance(v, list) and v and hasattr(v[0], "model_dump")
            else v.isoformat()
            if hasattr(v, "isoformat")
            else str(v)
            if isinstance(v, Decimal)
            else v
            for k, v in payload.items()
        }
        return RouteDecision(route_id=artifact_id("route", digest(encoded)), **payload)

    @staticmethod
    def _fresh(stamp, now):
        return stamp is not None and 0 <= (now - stamp).total_seconds() < 120

    def _state(self, state, present, source, timestamp, now):
        if state != "AVAILABLE":
            return state
        if not present or not source or timestamp is None:
            return "UNVERIFIED"
        return "AVAILABLE" if self._fresh(timestamp, now) else "STALE"
