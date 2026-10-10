"""Deterministic drift planning over Phase 10. This service has no execution transport."""

import threading
from decimal import Decimal, localcontext
from fractions import Fraction
from uuid import NAMESPACE_URL, uuid5

from app.models.portfolio import (
    DriftRow,
    PortfolioConfig,
    PortfolioInputs,
    PortfolioRules,
    PortfolioSnapshot,
    PreparationRecord,
    RebalanceAction,
    RebalancePlan,
)
from app.models.portfolio import portfolio_fingerprint as fingerprint
from app.models.position import quantity
from app.models.routing import RoutePolicy
from app.services.funding import FundingService
from app.services.position import change
from app.services.risk import RiskEngine
from app.services.routing import RoutingService

OWNED = {"OPEN", "EXIT_PENDING"}
UNCERTAIN = {"OPENING", "EXITING", "UNKNOWN", "RECONCILIATION_REQUIRED"}


def fresh(at, now):
    return at is not None and 0 <= (now - at).total_seconds() <= 120


class PortfolioService:
    def __init__(
        self,
        store,
        positions,
        source,
        *,
        clock,
        trust_required=True,
        inventory="POSITIONS",
        allow_closed_underlying=False,
    ):
        self.store, self.positions, self.source, self.clock = store, positions, source, clock
        if inventory not in {"POSITIONS", "WALLET"}:
            raise ValueError("Unsupported inventory authority")
        # POSITIONS: holdings are Phase 10 confirmed positions. WALLET: holdings are the
        # verified on-chain balances in the captured token funding states (live rebalance).
        self.inventory = inventory
        if allow_closed_underlying and inventory != "WALLET":
            raise ValueError("Closed-underlying trading is wallet rebalancing only")
        self.allow_closed_underlying = allow_closed_underlying
        # Configured rebalancing may run on cost/liquidity/risk/freshness alone when the
        # operator disables Trust; routes are then labelled TRUST_NOT_EVALUATED.
        self.trust_required = trust_required
        self.mode = positions.mode
        self.router, self.risk, self.funding = RoutingService(), RiskEngine(), FundingService()
        self.lock = threading.RLock()
        self.recovery_complete = False

    def configure(self, rules, *, expected_version, request_id, correlation_id):
        rules = PortfolioRules.model_validate(rules.model_dump(exclude={"expected_version"}))
        old = self.store.config(mode=self.mode)
        now = self.clock()
        config = PortfolioConfig(
            **rules.model_dump(),
            data_mode=self.mode,
            version=expected_version + 1,
            created_at=old.created_at if old else now,
            updated_at=now,
        )
        return self.store.set_config(
            config,
            expected_version=expected_version,
            request_id=request_id,
            correlation_id=correlation_id,
        )

    def configure_from_mandate(self, mandate, rules, **version_and_ids):
        """Existing bounded agent intent may suggest a mandate, never balances or orders.

        Explicit user-reviewed ticker targets and limits remain mandatory. No agent may
        invent the universe or replace host market/risk/funding facts.
        """
        from app.agents.schemas import Mandate

        mandate = Mandate.model_validate_json(mandate.model_dump_json())
        rules = PortfolioRules.model_validate_json(rules.model_dump_json())
        with localcontext() as ctx:
            ctx.prec = 256
            stock = (
                sum((t.weight for t in rules.targets if t.kind == "TOKENIZED_STOCK"), Decimal(0))
                * 100
            )
            cash = next(t.weight for t in rules.targets if t.kind == "CASH") * 100
        if (
            mandate.mode != "AUTOPILOT"
            or mandate.allocation_stock_percent != stock
            or mandate.allocation_cash_percent != cash
            or mandate.budget_usd is not None
            and mandate.budget_usd != rules.max_rebalance_notional_usd
            or mandate.risk_budget_usd is not None
            and mandate.risk_budget_usd != rules.risk_budget_usd
        ):
            raise ValueError(
                "Agent mandate must match explicit user-reviewed portfolio targets/limits"
            )
        return self.configure(rules, **version_and_ids)

    def state(self):
        config = self.store.config(mode=self.mode)
        plan = self.store.pending(mode=self.mode)
        count = self.positions.store.count(mode=self.mode, active=True)
        live = getattr(self, "live_execution", False)
        return dict(
            data_mode=self.mode,
            execution_mode="LIVE" if live else "DRY_RUN",
            config=config,
            pending_plan=plan,
            latest_decision=self.store.latest(mode=self.mode),
            active_positions=self.positions.store.list(mode=self.mode, active=True, limit=100),
            position_coverage_complete=count <= 100,
            recovery_complete=self.recovery_complete,
            live_trading_enabled=live,
        )

    def capture(self, config):
        if self.positions.store.count(mode=self.mode) > 100:
            raise ValueError("Portfolio position universe exceeds 100; no truncation allowed")
        positions = tuple(self.positions.store.list(mode=self.mode, limit=100))
        inputs = self.source.capture(config)
        inputs = PortfolioInputs.model_validate_json(inputs.model_dump_json())
        if inputs.data_mode != self.mode:
            raise ValueError("Portfolio source mode mismatch")
        body = dict(
            config_version=config.version,
            data_mode=self.mode,
            inputs=inputs,
            positions=positions,
            captured_at=inputs.captured_at,
        )
        return PortfolioSnapshot(snapshot_id=fingerprint(body), **body)

    def _validate_snapshot(self, config, snapshot, now):
        i = snapshot.inputs
        reasons = list(i.blockers)
        if not self.recovery_complete or not self.positions.recovery_complete:
            reasons.append("RECOVERY_INCOMPLETE")
        if not fresh(i.captured_at, now) or not fresh(i.position_verified_at, now):
            reasons.append("POSITION_STATE_STALE_OR_MISSING")
        if not i.inventory_complete:
            reasons.append("INVENTORY_NOT_VERIFIED_COMPLETE")
        funding = i.funding
        if funding is None:
            reasons.append("CURRENT_FUNDING_UNAVAILABLE")
        elif (
            not funding.identity_verified
            or funding.asset.symbol != config.funding_symbol
            or not all(
                fresh(t, now)
                for t in (
                    funding.asset.observed_at,
                    funding.price_observed_at,
                    funding.balance_observed_at,
                    funding.native_price_observed_at,
                    funding.conversion_cost_observed_at,
                )
            )
            or funding.source == "TEST_FIXTURE"
            and self.mode != "DEMO"
        ):
            reasons.append("FUNDING_IDENTITY_OR_FRESHNESS_INVALID")
        route_map = {r.identity.contract: r for r in i.routes}
        targets = {t.asset: t for t in config.targets}
        for t in config.targets:
            if t.kind == "TOKENIZED_STOCK" and not any(
                r.identity.underlying == t.asset and r.supported for r in i.routes
            ):
                reasons.append("UNSUPPORTED_OR_UNRESOLVED_ASSET")
        for p in snapshot.positions:
            self.positions.store._validate_journal(p)
            journal = [p.entry_execution, *p.applied_exit_executions]
            if p.exit_intent and p.exit_intent.execution:
                journal.append(p.exit_intent.execution)
            if any(
                self.positions.execution.store.get(a.execution_id, mode=self.mode) != a
                for a in journal
            ):
                reasons.append("CURRENT_EXECUTION_REQUIRES_POSITION_RECONCILIATION")
            if p.state in UNCERTAIN or p.job.status == "RUNNING":
                reasons.append("POSITION_RECONCILIATION_UNRESOLVED")
            if p.entry_execution.external_tracking_only and p.entry_execution.state in {
                "EXECUTION_PENDING",
                "EXECUTION_SUBMITTED",
                "EXECUTION_UNKNOWN",
            }:
                reasons.append("UNCONFIRMED_EXECUTION_NOT_OWNED")
            if p.state not in OWNED:
                continue
            if not fresh(p.updated_at, now):
                reasons.append("POSITION_STATE_STALE_OR_MISSING")
            if (
                p.instrument.ticker not in targets
                or targets[p.instrument.ticker].kind != "TOKENIZED_STOCK"
            ):
                reasons.append("UNCONFIGURED_OWNED_ASSET")
            if funding and p.entry_execution.quote.request.userWalletAddress != funding.wallet:
                reasons.append("POSITION_WALLET_MISMATCH")
            if funding and (
                funding.asset.contract != p.entry_execution.quote.request.fromTokenAddress
                or funding.asset.decimals != int(p.entry_execution.quote.route.fromToken.decimal)
            ):
                reasons.append("POSITION_CASH_ASSET_MISMATCH")
            r = route_map.get(p.instrument.contract)
            if r is None or (
                r.identity.underlying,
                r.identity.token,
                r.identity.issuer,
                r.identity.chain_id,
                r.token_to_share_ratio,
            ) != (
                p.instrument.ticker,
                p.instrument.token,
                p.instrument.issuer,
                p.instrument.chain_id,
                p.instrument.shares_per_token,
            ):
                reasons.append("POSITION_PRICE_OR_RATIO_IDENTITY_MISMATCH")
        price_mode = "DEMO" if self.mode == "DEMO" else "LIVE"
        for r in i.routes:
            if (
                r.token_price_usd is None
                or not r.price_source
                or not r.ratio_source
                or r.price_quality != price_mode
                or not fresh(r.price_timestamp, now)
                or not fresh(r.ratio_observed_at, now)
                or self.mode != "DEMO"
                and (r.identity.contract.startswith("demo:") or r.price_source.startswith("TEST"))
            ):
                reasons.append("PRICE_OR_RATIO_STALE_MISSING_INVALID")
        return tuple(dict.fromkeys(reasons))

    def evaluate(self, *, idempotency_key, request_id, correlation_id, persist=True):
        with self.lock, localcontext() as ctx:
            ctx.prec = 256
            config = self.store.config(mode=self.mode)
            if config is None:
                raise ValueError("PORTFOLIO_NOT_CONFIGURED")
            old = self.store.for_request(idempotency_key, mode=self.mode) if persist else None
            if old:
                return old
            snapshot = self.capture(config)
            now = self.clock()
            reasons = list(self._validate_snapshot(config, snapshot, now))
            values = {t.asset: Decimal(0) for t in config.targets}
            shares = {t.asset: Decimal(0) for t in config.targets}
            owned = [p for p in snapshot.positions if p.state in OWNED]
            marks = {r.identity.contract: r for r in snapshot.inputs.routes}
            if not reasons:
                f = snapshot.inputs.funding
                values["CASH"] = quantity(f.balance_base_units, f.asset.decimals) * f.unit_price_usd
                for p in owned if self.inventory == "POSITIONS" else ():
                    values[p.instrument.ticker] += (
                        p.remaining_quantity * marks[p.instrument.contract].token_price_usd
                    )
                    shares[p.instrument.ticker] += p.normalized_share_exposure
                for h in self._holdings(snapshot):
                    mark = marks[h.asset.contract]
                    held = quantity(h.balance_base_units, h.asset.decimals)
                    values[mark.identity.underlying] += held * mark.token_price_usd
                    shares[mark.identity.underlying] += held * mark.token_to_share_ratio
            total = sum(values.values(), Decimal(0)) if not reasons else None
            if total is not None and total <= 0:
                reasons.append("PORTFOLIO_VALUE_NOT_POSITIVE")
                total = None
            rows = []
            for t in sorted(config.targets, key=lambda t: t.asset):
                valid = total is not None
                current = values[t.asset] if valid else None
                with localcontext() as display:
                    display.prec = 72
                    weight = current / total if valid else None
                drift = weight - t.weight if valid else None
                exact_drift = (
                    Fraction(current) / Fraction(total) - Fraction(t.weight) if valid else None
                )
                outside = valid and abs(exact_drift) > Fraction(t.drift_band)
                rows.append(
                    DriftRow(
                        asset=t.asset,
                        kind=t.kind,
                        current_value_usd=current,
                        target_value_usd=total * t.weight if valid else None,
                        current_weight=weight,
                        target_weight=t.weight,
                        drift=drift,
                        allowed_band=t.drift_band,
                        required_delta_usd=total * t.weight - current if valid else None,
                        position_ids=tuple(
                            p.position_id for p in owned if p.instrument.ticker == t.asset
                        ),
                        current_share_exposure=shares[t.asset] if valid else None,
                        state="DISABLED"
                        if t.kind == "CRYPTO"
                        else "OUTSIDE_BAND"
                        if outside
                        else "WITHIN_BAND"
                        if valid
                        else "UNAVAILABLE",
                        reasons=("OPTIONAL_CRYPTO_NOT_VERIFIED",)
                        if t.kind == "CRYPTO"
                        else ("DRIFT_EXCEEDS_BAND",)
                        if outside
                        else ()
                        if valid
                        else tuple(reasons),
                    )
                )
                if outside and abs(exact_drift) > Fraction(config.max_drift):
                    reasons.append("EXCESSIVE_DRIFT")
            actions = []
            route_decisions = []
            if total is not None and not reasons:
                work = [
                    r for r in rows if r.kind == "TOKENIZED_STOCK" and r.state == "OUTSIDE_BAND"
                ]
                # Cash drift is repaired only through explicitly configured stock deltas.
                cash = next(r for r in rows if r.asset == "CASH")
                if cash.state == "OUTSIDE_BAND" and not work:
                    work = [
                        r for r in rows if r.kind == "TOKENIZED_STOCK" and r.required_delta_usd != 0
                    ]
                for row in sorted(
                    work,
                    key=lambda r: (r.required_delta_usd > 0, -abs(r.required_delta_usd), r.asset),
                ):
                    amount = abs(row.required_delta_usd)
                    if row.required_delta_usd > 0:
                        rows_for_asset = [
                            r for r in snapshot.inputs.routes if r.identity.underlying == row.asset
                        ]
                        action = self._action(
                            config,
                            snapshot,
                            row,
                            rows_for_asset,
                            amount,
                            len(actions) + 1,
                            None,
                            route_decisions,
                        )
                        if action:
                            actions.append(action)
                        else:
                            reasons.append("NO_TRUST_RISK_ROUTE_FOR_ASSET")
                    elif self.inventory == "WALLET":
                        held = sorted(
                            (
                                h
                                for h in self._holdings(snapshot)
                                if marks[h.asset.contract].identity.underlying == row.asset
                            ),
                            key=lambda h: (
                                -quantity(h.balance_base_units, h.asset.decimals)
                                * marks[h.asset.contract].token_price_usd,
                                h.asset.contract,
                            ),
                        )
                        for h in held:
                            if amount <= 0:
                                break
                            mark = marks[h.asset.contract]
                            value = (
                                quantity(h.balance_base_units, h.asset.decimals)
                                * mark.token_price_usd
                            )
                            action = self._action(
                                config,
                                snapshot,
                                row,
                                [mark],
                                min(amount, value),
                                len(actions) + 1,
                                None,
                                route_decisions,
                                holding=h,
                            )
                            if action:
                                actions.append(action)
                                amount -= action.notional_usd
                            else:
                                reasons.append("HELD_REPRESENTATION_REDUCTION_BLOCKED")
                        dust = sum(
                            (
                                marks[h.asset.contract].token_price_usd
                                * Decimal(10) ** (-h.asset.decimals)
                                for h in held
                            ),
                            Decimal(0),
                        )
                        if amount > dust:
                            reasons.append("REDUCTION_QUANTITY_UNAVAILABLE")
                    else:
                        holdings = sorted(
                            (p for p in owned if p.instrument.ticker == row.asset),
                            key=lambda p: (
                                -p.remaining_quantity
                                * marks[p.instrument.contract].token_price_usd,
                                p.instrument.contract,
                                str(p.position_id),
                            ),
                        )
                        for p in holdings:
                            if amount <= 0:
                                break
                            mark = marks[p.instrument.contract]
                            notional = min(amount, p.remaining_quantity * mark.token_price_usd)
                            action = self._action(
                                config,
                                snapshot,
                                row,
                                [mark],
                                notional,
                                len(actions) + 1,
                                p,
                                route_decisions,
                            )
                            if action:
                                actions.append(action)
                                amount -= action.notional_usd
                            else:
                                reasons.append("HELD_REPRESENTATION_REDUCTION_BLOCKED")
                        dust = sum(
                            (
                                marks[p.instrument.contract].token_price_usd
                                * Decimal(10) ** (-p.instrument.decimals)
                                for p in holdings
                            ),
                            Decimal(0),
                        )
                        if amount > dust:
                            reasons.append("REDUCTION_QUANTITY_UNAVAILABLE")
                if len(actions) > 100:
                    raise ValueError("Unsupported rebalance action count")
                if (
                    sum((a.notional_usd for a in actions), Decimal(0))
                    > config.max_rebalance_notional_usd
                ):
                    reasons.append("REBALANCE_NOTIONAL_CAP")
                if (
                    sum((a.risk.stress_loss_usd or Decimal(0) for a in actions), Decimal(0))
                    > config.risk_budget_usd
                ):
                    reasons.append("AGGREGATE_RISK_BUDGET_LIMIT")
                buy_cost = sum(
                    (
                        a.notional_usd + a.risk_inputs.costs_usd + a.risk_inputs.conversion_cost_usd
                        for a in actions
                        if a.side == "BUY"
                    ),
                    Decimal(0),
                )
                if buy_cost > values["CASH"]:
                    reasons.append("INSUFFICIENT_CURRENT_FUNDING_NO_ASSUMED_SALE_PROCEEDS")
                projected = sum((v for k, v in values.items() if k != "CASH"), Decimal(0)) + sum(
                    (a.notional_usd if a.side == "BUY" else -a.notional_usd for a in actions),
                    Decimal(0),
                )
                if projected > config.max_stock_exposure_usd:
                    reasons.append("PORTFOLIO_STOCK_EXPOSURE_CAP")
                for a in actions:
                    context = a.risk_inputs.context
                    if projected > context.max_portfolio_exposure_usd:
                        reasons.append("AGGREGATE_EXISTING_RISK_EXPOSURE_CAP")
                    if context.trades_today + len(actions) > context.max_trades_per_day:
                        reasons.append("AGGREGATE_TRADE_COUNT_LIMIT")
            if any(not a.eligible_for_preparation for a in actions):
                reasons.extend(
                    r for a in actions if not a.eligible_for_preparation for r in a.reasons
                )
            reasons = tuple(dict.fromkeys(reasons))
            if reasons:
                actions = [
                    change(
                        a,
                        eligible_for_preparation=False,
                        reasons=tuple(dict.fromkeys((*a.reasons, *reasons))),
                    )
                    for a in actions
                ]
            status = "BLOCKED" if reasons else "REBALANCE_REQUIRED" if actions else "NO_ACTION"
            plan_id = fingerprint(dict(config=config, snapshot=snapshot))
            plan = RebalancePlan(
                plan_id=plan_id,
                data_mode=self.mode,
                config=config,
                snapshot=snapshot,
                total_value_usd=total,
                rows=tuple(rows),
                actions=tuple(actions),
                route_decisions=tuple(route_decisions),
                status=status,
                reasons=reasons
                or (("DRIFT_REBALANCE_PROPOSED",) if actions else ("WITHIN_CONFIGURED_BANDS",)),
                idempotency_key=idempotency_key,
                request_id=request_id,
                correlation_id=correlation_id,
                created_at=now,
                updated_at=now,
            )
            return self.store.claim(plan) if persist else plan

    def _risk_inputs(self, config, snapshot, asset, route, notional, decision_id, funding):
        template = next((r.evidence for r in snapshot.inputs.risks if r.asset == asset), None)
        if template is None or template.context is None or funding is None:
            return None
        stock_value = sum(
            (
                p.remaining_quantity
                * next(
                    r.token_price_usd
                    for r in snapshot.inputs.routes
                    if r.identity.contract == p.instrument.contract
                )
                for p in snapshot.positions
                if p.state in OWNED and self.inventory == "POSITIONS"
            ),
            Decimal(0),
        ) + sum(
            (
                quantity(h.balance_base_units, h.asset.decimals) * h.unit_price_usd
                for h in self._holdings(snapshot)
            ),
            Decimal(0),
        )
        cash = snapshot.inputs.funding
        cash_usd = quantity(cash.balance_base_units, cash.asset.decimals) * cash.unit_price_usd
        if self.inventory == "WALLET" and funding.asset.contract != cash.asset.contract:
            # A wallet sale spends the held token, not cash: bound it by the token's value.
            cash_usd = (
                quantity(funding.balance_base_units, funding.asset.decimals)
                * funding.unit_price_usd
            )
        context = change(
            template.context, wallet_available_usd=cash_usd, existing_exposure_usd=stock_value
        )
        return change(
            template,
            decision_id=decision_id,
            purpose="DIRECT_EXPOSURE",
            budget_usd=config.max_rebalance_notional_usd,
            risk_budget_usd=config.risk_budget_usd,
            notional_usd=notional,
            costs_usd=route.fees_usd
            + route.gas_usd
            + notional * route.slippage_bps / Decimal(10000),
            conversion_cost_usd=funding.conversion_cost_usd,
            slippage_bps=route.slippage_bps,
            context=context,
            trust_state=route.trust_state
            if route.trust_state != "UNKNOWN"
            else "INSUFFICIENT_EVIDENCE",
            trust_required=self.trust_required,
            tradable=route.tradable is True,
            route_available=route.route_available is True,
            liquidity_usd=route.liquidity_usd,
            token_observed_at=route.price_timestamp,
        )

    def _holdings(self, snapshot):
        """Wallet inventory: verified, non-zero token balances that have a captured mark."""
        if self.inventory != "WALLET":
            return ()
        marks = {r.identity.contract for r in snapshot.inputs.routes}
        return tuple(
            f
            for f in snapshot.inputs.token_funding
            if int(f.balance_base_units) > 0 and f.asset.contract in marks
        )

    def _action(
        self,
        config,
        snapshot,
        drift,
        routes,
        notional,
        priority,
        position,
        route_decisions,
        holding=None,
    ):
        now = self.clock()
        mode = "DEMO" if self.mode == "DEMO" else "LIVE"
        risk_template = next(
            (r.evidence for r in snapshot.inputs.risks if r.asset == drift.asset), None
        )
        if risk_template is None or risk_template.context is None:
            return None
        context = risk_template.context
        funding = (
            holding
            if holding is not None
            else snapshot.inputs.funding
            if position is None
            else next(
                (
                    f
                    for f in snapshot.inputs.token_funding
                    if f.asset.contract == position.instrument.contract
                ),
                None,
            )
        )
        candidates, risks = [], {}
        for route in routes:
            from app.models.execution import address

            try:
                address(route.identity.contract)
                identified = route.identity.chain_id == "56"
            except ValueError:
                identified = False
            if not identified:
                candidates.append(
                    change(
                        route,
                        supported=False,
                        normalization_reasons=[
                            *route.normalization_reasons,
                            "UNSUPPORTED_EXECUTION_CHAIN_OR_CONTRACT",
                        ],
                    )
                )
                continue
            if (
                route.cost_status != "AVAILABLE"
                or any(
                    v is None
                    for v in (
                        route.fees_usd,
                        route.gas_usd,
                        route.slippage_bps,
                        route.price_timestamp,
                    )
                )
                or self.trust_required
                and route.trust_state not in {"NORMAL", "LIKELY_INFORMATION"}
            ):
                candidates.append(route)
                continue
            e = self._risk_inputs(
                config, snapshot, drift.asset, route, notional, "portfolio_preview", funding
            )
            if e is None:
                continue
            risk = self.risk.evaluate_execution(e, now=now)
            risks[route.identity.contract] = (e, risk)
            candidates.append(
                change(
                    route,
                    risk_state=risk.status,
                    risk_source="EXISTING_RISK_ENGINE",
                    risk_timestamp=now,
                    risk_id=uuid5(NAMESPACE_URL, fingerprint(e)),
                    risk_max_notional_usd=risk.maximum_notional_usd,
                    risk_reason_codes=[c.code for c in risk.checks if not c.passed],
                )
            )
        policy = RoutePolicy(
            require_costs=True,
            require_liquidity=True,
            require_trust=self.trust_required,
            require_risk=True,
            allow_closed_underlying=self.allow_closed_underlying,
            min_liquidity_usd=context.min_liquidity_usd,
            max_slippage_bps=context.max_slippage_bps,
        )
        routing = self.router.decide(
            drift.asset, notional, candidates, mode=mode, now=now, policy=policy
        )
        route_decisions.append(routing)
        if routing.status != "ROUTE_SELECTED":
            return None
        route = routing.selected_candidate.inputs
        decimals = (
            position.instrument.decimals
            if position
            else holding.asset.decimals
            if holding is not None
            else self.source.decimals(route.identity.contract)
        )
        if type(decimals) is not int or not 0 <= decimals <= 36:
            return None
        units = int(Fraction(notional) / Fraction(route.token_price_usd) * 10**decimals)
        if position:
            units = min(units, int(position.remaining_quantity_base_units))
        if holding is not None:
            if holding.asset.contract != route.identity.contract:
                return None
            units = min(units, int(holding.balance_base_units))
        if units <= 0 or units >= 2**256:
            return None
        actual = quantity(str(units), decimals) * route.token_price_usd
        side = "SELL" if position or holding is not None else "BUY"
        action_id = fingerprint(
            dict(
                snapshot=snapshot.snapshot_id,
                asset=drift.asset,
                side=side,
                contract=route.identity.contract,
                quantity=str(units),
                position=str(position.position_id) if position else None,
            )
        )
        decision = (
            self.positions.exit_decision_id(position.position_id, str(units))
            if position
            else "rebalance_" + action_id
        )
        e = self._risk_inputs(config, snapshot, drift.asset, route, actual, decision, funding)
        risk = self.risk.evaluate_execution(e, now=now)
        funding_check = self.funding.check(
            actual, funding, wallet=snapshot.inputs.funding.wallet, mode=self.mode, now=now
        )
        reasons = []
        if risk.status != "PASS":
            reasons.extend(c.code for c in risk.checks if not c.passed)
        if funding_check.status != "PASS":
            reasons.extend(funding_check.reasons)
        if (
            (position or holding is not None)
            and funding
            and (
                funding.unit_price_usd != route.token_price_usd
                or funding.asset.decimals != decimals
                or int(funding_check.required_base_units or "0") != units
            )
        ):
            reasons.append("REDUCTION_FUNDING_MARK_QUANTITY_MISMATCH")
        if position and (position.state != "OPEN" or position.exit_rule != "PORTFOLIO_DRIFT"):
            reasons.append("EXISTING_POSITION_EXIT_POLICY_HAS_PRIORITY")
        delta = (
            quantity(str(units), decimals)
            * route.token_to_share_ratio
            * (1 if side == "BUY" else -1)
        )
        if position:
            current_units = int(position.remaining_quantity_base_units)
        elif self.inventory == "WALLET":
            current_units = sum(
                int(h.balance_base_units)
                for h in self._holdings(snapshot)
                if h.asset.contract == route.identity.contract
            )
        else:
            current_units = sum(
                int(p.remaining_quantity_base_units)
                for p in snapshot.positions
                if p.state in OWNED and p.instrument.contract == route.identity.contract
            )
        return RebalanceAction(
            action_id=action_id,
            asset=drift.asset,
            side=side,
            priority=priority,
            notional_usd=actual,
            quantity_base_units=str(units),
            decimals=decimals,
            current_representation_base_units=str(current_units),
            target_representation_base_units=str(
                current_units + units * (1 if side == "BUY" else -1)
            ),
            current_share_exposure=drift.current_share_exposure,
            estimated_share_delta=delta,
            target_share_exposure=max(Decimal(0), drift.current_share_exposure + delta),
            position_id=position.position_id if position else None,
            inventory_source="WALLET_BALANCE"
            if self.inventory == "WALLET"
            else "PHASE10_POSITION",
            route=routing,
            risk=risk,
            risk_inputs=e,
            eligible_for_preparation=not reasons,
            reasons=tuple(reasons)
            or (
                ("DRIFT_EXCEEDS_CONFIGURED_BAND",)
                if drift.state == "OUTSIDE_BAND"
                else ("CASH_DRIFT_REQUIRES_STOCK_ADJUSTMENT",)
            ),
            execution_decision_id=decision,
        )

    def can_reduce(self, position, amount, decision_id, evidence, funding_state):
        plan = self.store.pending(mode=self.mode)
        config = self.store.config(mode=self.mode)
        held = (
            next(
                (p for p in plan.snapshot.positions if p.position_id == position.position_id), None
            )
            if plan
            else None
        )
        return bool(
            self.recovery_complete
            and plan
            and config == plan.config
            and held
            and held.instrument == position.instrument
            and held.entry_execution == position.entry_execution
            and held.remaining_quantity_base_units == position.remaining_quantity_base_units
            and held.applied_exit_executions == position.applied_exit_executions
            and fresh(plan.created_at, self.clock())
            and not self._validate_snapshot(plan.config, plan.snapshot, self.clock())
            and funding_state in plan.snapshot.inputs.token_funding
            and any(
                a.side == "SELL"
                and a.position_id == position.position_id
                and a.quantity_base_units == amount
                and a.execution_decision_id == decision_id
                and a.eligible_for_preparation
                and a.risk_inputs == evidence
                for a in plan.actions
            )
        )

    def prepare(self, plan_id, action_id, *, allowance):
        """Host-only fresh preparation, through the original services. Never an API trade."""
        with self.lock:
            plan = self.store.get(plan_id, mode=self.mode)
            action = next((a for a in plan.actions if a.action_id == action_id), None)
            if (
                action is None
                or plan.status != "REBALANCE_REQUIRED"
                or not action.eligible_for_preparation
            ):
                raise ValueError("PLAN_NOT_ACTIONABLE")
            if any(r.action_id == action_id for r in plan.preparations):
                return plan
            if not fresh(plan.created_at, self.clock()) or self.positions.has_unresolved(
                action.execution_decision_id
            ):
                raise ValueError("STALE_OR_UNRESOLVED_REBALANCE")
            current = self.capture(plan.config)
            if self._validate_snapshot(plan.config, current, self.clock()) or fingerprint(
                [p.model_dump(exclude_computed_fields=True) for p in current.positions]
            ) != fingerprint(
                [p.model_dump(exclude_computed_fields=True) for p in plan.snapshot.positions]
            ):
                raise ValueError("POSITION_SNAPSHOT_CHANGED_REPLAN_REQUIRED")
            fields = {"captured_at", "position_verified_at"}
            if fingerprint(current.inputs.model_dump(exclude=fields)) != fingerprint(
                plan.snapshot.inputs.model_dump(exclude=fields)
            ):
                raise ValueError("MARKET_OR_FUNDING_INPUTS_CHANGED_REPLAN_REQUIRED")
            if action.side == "SELL":
                f = next(
                    f
                    for f in current.inputs.token_funding
                    if f.asset.contract == action.route.selected_representation.contract
                )
                position = self.positions.prepare_exit(
                    action.position_id,
                    evidence=action.risk_inputs,
                    funding_state=f,
                    allowance=allowance,
                    correlation_id=str(plan.correlation_id),
                    quantity_base_units=action.quantity_base_units,
                )
                attempt = self.positions.execution.store.for_decision(
                    action.execution_decision_id, mode=self.mode
                )
                if position.state not in {"EXIT_PENDING", "EXITING", "OPEN"}:
                    raise ValueError("POSITION_REDUCTION_UNRESOLVED")
            else:
                attempt = self.positions.execution.prepare(
                    action.risk_inputs,
                    current.inputs.funding,
                    target_contract=action.route.selected_representation.contract,
                    allowance=allowance,
                    correlation_id=str(plan.correlation_id),
                )
            record = PreparationRecord(
                action_id=action.action_id,
                execution_id=attempt.execution_id if attempt else None,
                status="DRY_RUN_PREPARED"
                if attempt and attempt.simulation and attempt.simulation.status == "PASS"
                else "BLOCKED",
                reasons=attempt.reason_codes if attempt else ("PREPARATION_UNAVAILABLE",),
                observed_at=self.clock(),
            )
            return self.store.save(
                change(
                    plan,
                    version=plan.version + 1,
                    preparations=(*plan.preparations, record),
                    updated_at=self.clock(),
                ),
                expected_version=plan.version,
            )

    def recover(self):
        """Restore existing pending decisions; do not generate plans, fetch prices or submit."""
        self.recovery_complete = False
        self.store.config(mode=self.mode)
        plan = self.store.pending(mode=self.mode)
        if plan:
            for action in plan.actions:
                attempt = self.positions.execution.store.for_decision(
                    action.execution_decision_id, mode=self.mode
                )
                if attempt and attempt.data_mode != self.mode:
                    raise ValueError("Execution mode conflict")
                if attempt and attempt.evidence != action.risk_inputs:
                    raise ValueError(
                        "Recovered execution does not match immutable rebalance inputs"
                    )
                # Preparation may have been journalled before a crash linked its receipt.
                if attempt and not any(r.action_id == action.action_id for r in plan.preparations):
                    receipt = PreparationRecord(
                        action_id=action.action_id,
                        execution_id=attempt.execution_id,
                        status="RECONCILIATION_REQUIRED"
                        if attempt.external_tracking_only
                        else "DRY_RUN_PREPARED"
                        if attempt.simulation and attempt.simulation.status == "PASS"
                        else "BLOCKED",
                        observed_at=self.clock(),
                        reasons=attempt.reason_codes
                        or ("EXISTING_EXECUTION_REQUIRES_RECONCILIATION",),
                    )
                    plan = self.store.save(
                        change(
                            plan,
                            version=plan.version + 1,
                            preparations=(*plan.preparations, receipt),
                            updated_at=self.clock(),
                        ),
                        expected_version=plan.version,
                    )
        self.recovery_complete = True
        return plan

    def register_confirmed_entry(self, plan_id, action_id, instrument):
        """Bind an already confirmed journal entry to Phase 10; never generate settlement.

        The caller must supply verified instrument metadata available at quote time. No
        guessed company, decimals, historical ratio or actual quantity is created here.
        """
        with self.lock:
            plan = self.store.get(plan_id, mode=self.mode)
            action = next((a for a in plan.actions if a.action_id == action_id), None)
            if action is None or action.side != "BUY" or plan.status != "REBALANCE_REQUIRED":
                raise ValueError("CONFIRMED_PORTFOLIO_ENTRY_REQUIRED")
            attempt = self.positions.execution.store.for_decision(
                action.execution_decision_id, mode=self.mode
            )
            if (
                attempt is None
                or attempt.state != "EXECUTION_CONFIRMED"
                or attempt.evidence != action.risk_inputs
            ):
                raise ValueError("CONFIRMED_BOUND_EXECUTION_REQUIRED")
            selected = action.route.selected_candidate.inputs
            if (
                instrument.ticker,
                instrument.issuer,
                instrument.token,
                instrument.chain_id,
                instrument.contract,
                instrument.decimals,
                instrument.shares_per_token,
                instrument.ratio_observed_at,
                instrument.ratio_available_at,
                instrument.source,
                instrument.data_mode,
            ) != (
                selected.identity.underlying,
                selected.identity.issuer,
                selected.identity.token,
                selected.identity.chain_id,
                selected.identity.contract,
                action.decimals,
                selected.token_to_share_ratio,
                selected.ratio_observed_at,
                selected.ratio_observed_at,
                selected.ratio_source,
                self.mode,
            ):
                raise ValueError("DISCOVERED_AS_OF_PORTFOLIO_INSTRUMENT_REQUIRED")
            return self.positions.create(
                attempt.execution_id, instrument, exit_rule="PORTFOLIO_DRIFT"
            )

    def complete(self, plan_id):
        """Release a pending intent only after all confirmed legs reconcile in Phase 10.

        Read existing evidence only. Partial processing, pending orders, proposals, lost
        position links and missing current inventory never count as a completed rebalance.
        """
        with self.lock:
            plan = self.store.get(plan_id, mode=self.mode)
            if plan.status == "COMPLETED":
                return plan
            if plan.status != "REBALANCE_REQUIRED":
                raise ValueError("PENDING_REBALANCE_REQUIRED")
            current = self.capture(plan.config)
            if self._validate_snapshot(plan.config, current, self.clock()):
                raise ValueError("CURRENT_PORTFOLIO_RECONCILIATION_REQUIRED")
            execution_ids = []
            for action in plan.actions:
                attempt = self.positions.execution.store.for_decision(
                    action.execution_decision_id, mode=self.mode
                )
                if (
                    attempt is None
                    or attempt.state != "EXECUTION_CONFIRMED"
                    or attempt.evidence != action.risk_inputs
                    or attempt.settlement_conflict
                    or attempt.conflicting_tx_hashes
                    or attempt.last_conflicting_tx_hash
                ):
                    raise ValueError("EVERY_REBALANCE_LEG_REQUIRES_CONFIRMED_SETTLEMENT")
                execution_ids.append(attempt.execution_id)
                if action.side == "BUY":
                    position = self.positions.store.for_execution(
                        attempt.execution_id, mode=self.mode
                    )
                    if (
                        position is None
                        or position.exit_rule != "PORTFOLIO_DRIFT"
                        or position.state not in {"OPEN", "CLOSED"}
                    ):
                        raise ValueError("CONFIRMED_ENTRY_POSITION_LINK_REQUIRED")
                    selected = action.route.selected_candidate.inputs
                    if (
                        position.instrument.ticker,
                        position.instrument.issuer,
                        position.instrument.contract,
                        position.instrument.chain_id,
                        position.instrument.shares_per_token,
                        position.instrument.decimals,
                    ) != (
                        action.asset,
                        selected.identity.issuer,
                        selected.identity.contract,
                        selected.identity.chain_id,
                        selected.token_to_share_ratio,
                        action.decimals,
                    ):
                        raise ValueError("CONFIRMED_ENTRY_REPRESENTATION_MISMATCH")
                else:
                    position = self.positions.store.get(action.position_id, mode=self.mode)
                    if (
                        position.state not in {"OPEN", "CLOSED"}
                        or attempt not in position.applied_exit_executions
                    ):
                        raise ValueError("CONFIRMED_REDUCTION_POSITION_LINK_REQUIRED")
            return self.store.save(
                change(
                    plan,
                    version=plan.version + 1,
                    status="COMPLETED",
                    completion_snapshot=current,
                    settled_execution_ids=tuple(execution_ids),
                    updated_at=self.clock(),
                ),
                expected_version=plan.version,
            )

    def mark_executed(self, plan_id):
        """Wallet-inventory plans only: the live executor confirmed every leg on-chain."""
        with self.lock:
            plan = self.store.get(plan_id, mode=self.mode)
            if self.inventory != "WALLET" or plan.status != "REBALANCE_REQUIRED":
                raise ValueError("Only a pending wallet-inventory plan can be marked executed")
            return self.store.save(
                change(
                    plan,
                    version=plan.version + 1,
                    status="EXECUTED",
                    execution_mode="LIVE",
                    live_trading_enabled=True,
                    broadcast=True,
                    updated_at=self.clock(),
                ),
                expected_version=plan.version,
            )

    def retire(self, plan_id):
        with self.lock:
            plan = self.store.get(plan_id, mode=self.mode)
            if plan.status != "REBALANCE_REQUIRED":
                raise ValueError("Only a pending rebalance proposal may be retired")
            for action in plan.actions:
                if action.side == "SELL" and any(
                    r.action_id == action.action_id for r in plan.preparations
                ):
                    raise ValueError(
                        "Prepared position reduction requires lifecycle reconciliation"
                    )
                a = self.positions.execution.store.for_decision(
                    action.execution_decision_id, mode=self.mode
                )
                if a and a.external_tracking_only:
                    raise ValueError(
                        "Observed external execution cannot be cancelled as a proposal"
                    )
            return self.store.save(
                change(plan, version=plan.version + 1, status="RETIRED", updated_at=self.clock()),
                expected_version=plan.version,
            )
