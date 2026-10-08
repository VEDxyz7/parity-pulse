"""Deterministic evaluation of existing decisions; no authority to make a new decision."""

from collections import Counter
from decimal import Decimal, localcontext
from threading import RLock

from app.models.portfolio import portfolio_fingerprint
from app.models.scorecard import (
    AuditEvent,
    EvaluationMetrics,
    PredictionEvaluation,
    RouteEvaluation,
    Scorecard,
)
from app.models.terminal import EpisodeQuery, TerminalQuery
from app.services.audit import AuditService
from app.services.research_model import direction


def quality(*, action, permitted=None, blocked=False, required=False):
    """Evaluate explicit existing controls, never opportunity profitability.

    DEFER is allowed: permission alone never implies a duty to buy. 'required' is used
    only for an existing explicit drift-band rebalance obligation, not confidence/edge.
    """
    if action:
        return (
            "INCORRECT_ACTION"
            if blocked or permitted is False
            else ("CORRECT_ACTION" if permitted is True else "UNSCORABLE")
        )
    if blocked:
        return "CORRECT_ABSTENTION"
    if required:
        return "INCORRECT_ABSTENTION"
    return "CORRECT_ABSTENTION" if permitted is False else "UNSCORABLE"


def route_evaluation(route):
    if route is None:
        return RouteEvaluation(reasons=("ROUTE_EVIDENCE_UNAVAILABLE",))
    eligible = [c for c in route.candidates if c.eligible]
    selected = route.selected_candidate
    values = [c.ranking_cost_per_share_usd for c in eligible]
    minimum = min(values) if values and all(v is not None for v in values) else None
    chosen = selected.ranking_cost_per_share_usd if selected else None
    with localcontext() as ctx:
        ctx.prec = 256
        excess = chosen - minimum if chosen is not None and minimum is not None else None
    if excess is not None and excess < 0:
        raise ValueError("Route comparison cost binding conflict")
    return RouteEvaluation(
        route_id=str(route.route_id),
        selected_issuer=route.issuer,
        basis=route.ranking_basis,
        token_price_usd=selected.inputs.token_price_usd if selected else None,
        shares_per_token=selected.inputs.token_to_share_ratio if selected else None,
        effective_cost_per_share_usd=selected.effective_cost_per_share_usd if selected else None,
        liquidity_state=selected.liquidity_state if selected else "UNAVAILABLE",
        liquidity_usd=selected.inputs.liquidity_usd if selected else None,
        liquidity_source=selected.inputs.liquidity_source if selected else None,
        trust_state=selected.trust_state if selected else None,
        tradability=selected.tradability if selected else None,
        selected_cost_per_share_usd=chosen,
        minimum_eligible_cost_per_share_usd=minimum,
        excess_cost_per_share_usd=excess,
        minimum_cost_selected=chosen == minimum
        if chosen is not None and minimum is not None
        else None,
        alternative_costs_per_share_usd={
            str(c.candidate_id): c.ranking_cost_per_share_usd for c in eligible
        },
        estimated_costs_usd=selected.estimated_costs_usd if selected else None,
        estimated_fees_usd=selected.inputs.fees_usd if selected else None,
        estimated_gas_usd=selected.inputs.gas_usd if selected else None,
        estimated_slippage_bps=selected.inputs.slippage_bps if selected else None,
        reasons=("ELIGIBLE_RECORDED_ROUTES_ONLY", "ESTIMATES_NOT_REALIZED_COSTS"),
    )


class ScorecardService:
    def __init__(
        self,
        store,
        terminal,
        exposure,
        scans,
        *,
        clock,
        secrets=(),
        demo_flow=None,
        paper=None,
        demo_preparation=None,
    ):
        self.store, self.terminal, self.exposure, self.scans = store, terminal, exposure, scans
        self.clock, self.demo_flow, self.paper = clock, demo_flow, paper
        self.demo_preparation = demo_preparation
        self.mode = terminal.mode
        self.audit = AuditService(store, clock=clock, secrets=secrets)
        self.lock = RLock()

    def _card(
        self,
        kind,
        origin,
        ident,
        decision,
        at,
        payload,
        *,
        ticker=None,
        issuer=None,
        run_id=None,
        episode_id=None,
        correlation_id=None,
        inputs=None,
        action="DEFER",
        outcome="DEFERRED",
        abstained=True,
        **fields,
    ):
        return Scorecard(
            evaluation_id="pending",
            scorecard_type=kind,
            origin=origin,
            origin_id=str(ident),
            decision_id=str(decision),
            run_id=run_id,
            episode_id=episode_id,
            correlation_id=str(correlation_id) if correlation_id is not None else None,
            ticker=ticker,
            selected_issuer=issuer,
            data_mode=self.mode,
            synthetic=self.mode == "DEMO",
            decision_at=at,
            recorded_at=self.clock(),
            evidence_asof=at,
            input_digest=portfolio_fingerprint(inputs or payload),
            source_digest=portfolio_fingerprint(payload),
            action=action,
            outcome=outcome,
            abstained=abstained,
            control_quality="UNSCORABLE",
            **fields,
        )

    def _event(
        self,
        card,
        kind,
        payload,
        *,
        at=None,
        status="RECORDED",
        inputs=None,
        outputs=None,
        reasons=(),
        execution_id=None,
    ):
        return self.audit.event(
            card,
            kind,
            at or card.decision_at,
            status,
            card.origin,
            payload,
            inputs=inputs,
            outputs=outputs,
            reasons=reasons,
            execution_id=execution_id,
        )

    def _finish(self, card, events, cutoff):
        events.append(
            self._event(
                card,
                "OUTCOME",
                {
                    "outcome": card.outcome,
                    "prediction": card.prediction,
                    "executions": card.executions,
                    "paper_pnl": card.paper_pnl,
                },
                at=card.evidence_asof,
                status=card.outcome,
                outputs={"outcome": card.outcome, "abstained": card.abstained},
                reasons=card.abstention_reasons,
            )
        )
        evaluation = dict(
            quality=card.control_quality,
            prediction=card.prediction,
            route=card.route,
            input_digest=card.input_digest,
        )
        events.append(
            self._event(
                card,
                "SCORECARD",
                evaluation,
                at=card.evidence_asof,
                status=card.control_quality,
                outputs={
                    "quality": card.control_quality,
                    "score": None,
                    "direction_correct": card.prediction.direction_correct,
                },
            )
        )
        if len(events) > 2000 or any(e.timestamp > cutoff for e in events):
            raise ValueError("Evaluation exceeds point-in-time/audit bound")
        card = card.model_copy(update={"event_ids": tuple(e.event_id for e in events)})
        card = card.model_copy(update={"evaluation_id": self.audit.evaluation_id(card)})
        return Scorecard.model_validate_json(card.model_dump_json()), events

    def _links(self, card, events, decision_ids, rows, cutoff):
        linked = tuple(r for r in rows if r.decision_id in decision_ids and r.updated_at <= cutoff)
        for row in linked:
            for a in self.terminal.execution.history(row.execution_id, mode=self.mode):
                if a.updated_at > cutoff:
                    continue

                def add(kind, payload, status, outputs=None, at=None, attempt=a, analytics=row):
                    events.append(
                        self._event(
                            card,
                            kind,
                            payload,
                            at=at or attempt.updated_at,
                            status=status,
                            outputs={
                                "execution_decision_id": attempt.decision_id,
                                **(outputs or {}),
                            },
                            reasons=attempt.reason_codes,
                            execution_id=analytics.execution_id,
                        )
                    )

                if a.risk:
                    add(
                        "RISK_APPROVE" if a.risk.status == "PASS" else "RISK_REJECT",
                        a.risk,
                        a.risk.status,
                        at=a.risk.evaluated_at,
                    )
                if a.quote:
                    add(
                        "QUOTE",
                        a.quote,
                        "QUOTE_OBTAINED",
                        {
                            "provider": a.quote.route.vendorName,
                            "quote_id": a.quote.route.quoteId,
                            "execution_mode": a.quote.route.executionMode,
                        },
                        at=a.quote.received_at,
                    )
                if a.route:
                    add("BUILD", a.route, "FINGERPRINT_BOUND", {"fingerprint": a.route.fingerprint})
                if a.simulation:
                    add(
                        "SIMULATION" if a.simulation.status == "PASS" else "SIMULATION_FAILURE",
                        a.simulation,
                        a.simulation.status,
                        at=a.simulation.evaluated_at,
                    )
                if a.user_confirmation:
                    add(
                        "APPROVAL",
                        a.user_confirmation,
                        "HOST_CONFIRMATION_RECORDED",
                        at=a.user_confirmation.confirmed_at,
                    )
                mapping = {
                    "EXECUTION_SUBMITTED": "EXECUTION_SUBMITTED",
                    "EXECUTION_PENDING": "EXECUTION_SUBMITTED",
                    "EXECUTION_CONFIRMED": "EXECUTION_CONFIRMED",
                    "EXECUTION_FAILED": "EXECUTION_FAILED",
                    "EXECUTION_UNKNOWN": "EXECUTION_UNKNOWN",
                    "BLOCKED": "NO_ACTION",
                }
                if a.state in mapping:
                    add(mapping[a.state], a, a.state)
            if row.position_id:
                events.append(
                    self._event(
                        card,
                        "POSITION",
                        row,
                        at=row.updated_at,
                        status=row.position_state or "UNKNOWN",
                        execution_id=row.execution_id,
                        outputs={
                            "position_id": row.position_id,
                            "filled": row.filled_base_units,
                            "remaining": row.remaining_base_units,
                        },
                    )
                )
                if row.position_state == "CLOSED":
                    events.append(
                        self._event(
                            card,
                            "EXIT",
                            row,
                            at=row.updated_at,
                            status="CLOSED",
                            execution_id=row.execution_id,
                        )
                    )
        if not linked:
            return card
        priority = [
            "RECONCILIATION_REQUIRED",
            "UNKNOWN",
            "FAILED",
            "SUBMITTED",
            "BLOCKED",
            "SIMULATED",
            "DRY_RUN",
            "PROPOSED",
            "CONFIRMED",
        ]
        outcome = next(k for k in priority if any(r.category == k for r in linked))
        if outcome == "CONFIRMED" and all(r.position_state == "CLOSED" for r in linked):
            outcome = "CLOSED"
        last = max(linked, key=lambda r: (r.updated_at, r.execution_id))
        route = card.route.model_copy(
            update={
                "provider": last.provider,
                "provider_quote_id": last.quote_id,
                "execution_mode": last.execution_mode,
                "actual_fees_native_base_units": last.actual_fees_native_base_units,
                "actual_average_execution_price": last.average_execution_price,
            }
        )
        withheld = outcome in {"BLOCKED", "UNKNOWN", "RECONCILIATION_REQUIRED", "FAILED"}
        return card.model_copy(
            update={
                "executions": linked,
                "outcome": outcome,
                "route": route,
                "evidence_asof": max(card.evidence_asof, *(r.updated_at for r in linked)),
                "abstained": True if withheld else card.abstained,
                "abstention_scope": "EXECUTION" if withheld else card.abstention_scope,
                "abstention_reasons": tuple(
                    dict.fromkeys(
                        (*card.abstention_reasons, *(c for r in linked for c in r.reasons))
                    )
                )
                if withheld
                else card.abstention_reasons,
            }
        )

    def _direct(self, p, rows, cutoff):
        s = p.selected
        card = self._card(
            "DIRECT_EXPOSURE",
            "EXPOSURE_PROPOSAL",
            p.proposal_id,
            p.proposal_id,
            p.created_at,
            p,
            ticker=p.ticker,
            issuer=s.issuer if s else None,
            run_id=p.run_id,
            correlation_id=p.correlation_id,
            action="PROPOSE" if s else "NO_ACTION",
            outcome="PROPOSED" if s else "REJECTED",
            abstained=s is None,
            requested_exposure_usd=p.requested_budget_usd,
            estimated_share_exposure=s.estimated_real_share_exposure if s else None,
            route=route_evaluation(p.route_decision),
            reasons=tuple(p.execution_blockers),
            abstention_reasons=(p.route_selection_reason,) if s is None else (),
        )
        events = [
            self._event(
                card,
                "INPUT",
                p.intent,
                outputs={
                    "request_id": p.request_id,
                    "budget_usd": str(p.requested_budget_usd)
                    if p.requested_budget_usd is not None
                    else None,
                    "intent_status": p.intent.status,
                },
            )
        ]
        if p.representations:
            events.extend(
                [
                    self._event(
                        card,
                        "ASSET_DISCOVERY",
                        p.representations,
                        outputs={"ticker": p.ticker, "representations": len(p.representations)},
                    ),
                    self._event(
                        card,
                        "DATA_FETCH",
                        p.representations,
                        status="FROZEN_OBSERVATION_REFERENCES",
                    ),
                    self._event(
                        card,
                        "NORMALIZATION",
                        p.representations,
                        outputs={
                            "ratio": str(s.token_to_share_ratio) if s else None,
                            "effective_share_cost_usd": str(s.effective_cost_per_share_usd)
                            if s
                            else None,
                            "selected_contract": s.contract if s else None,
                        },
                    ),
                ]
            )
        if p.route_decision:
            events.append(
                self._event(
                    card,
                    "ROUTE",
                    p.route_decision,
                    status=p.route_decision.status,
                    outputs={"route_id": str(p.route_decision.route_id)},
                    reasons=p.route_decision.reason_codes,
                )
            )
        events.append(
            self._event(
                card,
                "DECISION" if s else "NO_ACTION",
                p,
                status=card.action,
                outputs={"action": card.action},
                reasons=card.abstention_reasons,
            )
        )
        events.append(
            self._event(
                card,
                "QUOTE",
                p.independent_equity,
                status=p.quote_status,
                outputs={"provider_quote_id": None},
            )
        )
        card = card.model_copy(
            update={
                "control_quality": quality(
                    action=s is not None, permitted=s is not None, blocked=s is None
                )
            }
        )
        return self._finish(
            self._links(card, events, {str(p.proposal_id)}, rows, cutoff), events, cutoff
        )

    def _scan(self, scan, rows, cutoff):
        s = scan.selected_candidate
        chosen_route = next((c.route for c in scan.candidates if s and c.candidate == s), None)
        reasons = tuple(dict.fromkeys((*scan.blockers, *(s.rejection_reasons if s else ()))))
        abstained = scan.final_action != "BUY"
        card = self._card(
            "OPPORTUNITY",
            "OPPORTUNITY_SCAN",
            scan.run_id,
            scan.decision_id,
            scan.timestamp,
            scan,
            ticker=s.ticker if s else None,
            issuer=s.issuer if s else None,
            run_id=scan.run_id,
            correlation_id=scan.correlation_id,
            action=scan.final_action,
            outcome="DEFERRED" if abstained else "PROPOSED",
            abstained=abstained,
            confidence=s.confidence if s else None,
            trust_classification=s.trust if s else None,
            expected_net_edge_usd=s.net_edge_usd if s else None,
            requested_exposure_usd=scan.mandate.budget_usd,
            route=route_evaluation(chosen_route),
            reasons=reasons,
            abstention_reasons=reasons if abstained else (),
        )
        events = [
            self._event(card, "INPUT", scan.mandate),
            self._event(card, "DATA_FETCH", scan.provenance, status="FROZEN_EVIDENCE_REFERENCES"),
            self._event(
                card,
                "CANDIDATE_SCAN",
                scan.candidates,
                outputs={
                    "universe": scan.universe_count,
                    "eligible": scan.eligible_count,
                    "rejected": scan.rejected_count,
                },
            ),
            self._event(card, "TRUST", scan.candidates, status="PERSISTED_CANDIDATE_EVIDENCE"),
            self._event(
                card,
                "NO_ACTION" if abstained else "DECISION",
                scan,
                status=scan.final_action,
                reasons=reasons,
            ),
            self._event(
                card,
                "RISK_APPROVE" if scan.risk_validation == "PASS" else "RISK_REJECT",
                {"status": scan.risk_validation},
                status=scan.risk_validation,
            ),
        ]
        if scan.agent_run:
            events.append(self._agent_event(card, scan.agent_run))
        if chosen_route:
            events.append(self._event(card, "ROUTE", chosen_route, status=chosen_route.status))
        blocked = scan.eligible_count == 0 or scan.risk_validation != "PASS" or bool(scan.blockers)
        card = card.model_copy(
            update={
                "control_quality": quality(
                    action=not abstained, permitted=not blocked, blocked=blocked
                ),
                "prediction": PredictionEvaluation(
                    predicted_return=s.predicted_open_return if s else None,
                    predicted_direction=direction(s.predicted_open_return)
                    if s and s.predicted_open_return is not None
                    else None,
                    noise_suppressed=abstained
                    and any(c.candidate.trust == "LIKELY_NOISE" for c in scan.candidates),
                ),
            }
        )
        return self._finish(
            self._links(card, events, {scan.decision_id}, rows, cutoff), events, cutoff
        )

    def _agent_event(self, card, run):
        # Never project AgentResponse.reasoning_summary or arbitrary raw responses.
        return self._event(
            card,
            "AGENT_RUN",
            {
                "run_id": run.run_id,
                "evidence": run.evidence,
                "outputs": [r.output for r in run.responses],
                "decision": run.decision,
            },
            at=run.timestamp,
            status=run.status,
            outputs={
                "agent_run_id": run.run_id,
                "action": run.decision.decision,
                "agent_count": len(run.responses),
            },
            reasons=run.decision.reasons,
        )

    def _agent(self, run, rows, cutoff):
        d = run.decision
        c = next((c for c in run.candidate_table if c.candidate_id == d.candidate_id), None)
        mandate = run.responses[0].output.mandate
        card = self._card(
            mandate.mode,
            "AGENT_RUN",
            run.run_id,
            run.decision_id,
            run.timestamp,
            {
                "mandate": mandate,
                "candidates": run.candidate_table,
                "decision": d,
                "evidence": run.evidence,
            },
            ticker=d.ticker,
            issuer=d.issuer,
            run_id=run.run_id,
            correlation_id=run.correlation_id,
            action=d.decision,
            outcome="PROPOSED" if d.decision == "BUY" else "DEFERRED",
            abstained=d.decision != "BUY",
            confidence=next(
                (r.confidence.tier for r in run.responses if r.agent == "DECISION"), None
            ),
            trust_classification=c.trust if c else None,
            reasons=d.reasons,
            abstention_reasons=d.reasons if d.decision != "BUY" else (),
            requested_exposure_usd=mandate.budget_usd,
        )
        blocked = not any(c.eligibility == "ELIGIBLE" for c in run.candidate_table)
        card = card.model_copy(
            update={
                "control_quality": quality(
                    action=d.decision == "BUY",
                    blocked=blocked,
                    permitted=None if d.decision == "BUY" else False if blocked else None,
                )
            }
        )
        events = [
            self._event(card, "INPUT", mandate),
            self._event(card, "CANDIDATE_SCAN", run.candidate_table),
            self._agent_event(card, run),
            self._event(
                card,
                "DECISION" if d.decision == "BUY" else "NO_ACTION",
                d,
                status=d.decision,
                reasons=d.reasons,
            ),
        ]
        return self._finish(
            self._links(card, events, {run.decision_id}, rows, cutoff), events, cutoff
        )

    def _portfolio(self, plan, rows, cutoff):
        initial = dict(
            config=plan.config,
            snapshot=plan.snapshot,
            rows=plan.rows,
            actions=plan.actions,
            reasons=plan.reasons,
            routes=plan.route_decisions,
        )
        original_status = (
            plan.status if plan.status in {"NO_ACTION", "BLOCKED"} else ("REBALANCE_REQUIRED")
        )
        known_status = plan.status if plan.updated_at <= cutoff else original_status
        abstained = original_status in {"NO_ACTION", "BLOCKED"}
        card = self._card(
            "AUTOPILOT",
            "PORTFOLIO_PLAN",
            plan.plan_id,
            plan.plan_id,
            plan.created_at,
            initial,
            correlation_id=plan.correlation_id,
            action=original_status,
            outcome=known_status,
            abstained=abstained,
            requested_exposure_usd=plan.config.max_rebalance_notional_usd,
            abstention_reasons=plan.reasons if abstained else (),
            reasons=plan.reasons,
            allocations=tuple(
                {
                    "asset": r.asset,
                    "target_weight": str(r.target_weight),
                    "decision_time_weight": str(r.current_weight)
                    if r.current_weight is not None
                    else None,
                    "drift": str(r.drift) if r.drift is not None else None,
                    "drift_band": str(r.allowed_band),
                    "state": r.state,
                }
                for r in plan.rows
            ),
            proposed_actions=tuple(
                {
                    "action_id": a.action_id,
                    "execution_decision_id": a.execution_decision_id,
                    "asset": a.asset,
                    "side": a.side,
                    "notional_usd": str(a.notional_usd),
                    "quantity_base_units": a.quantity_base_units,
                    "risk": a.risk.status,
                    "route_id": str(a.route.route_id),
                    "eligible": a.eligible_for_preparation,
                }
                for a in plan.actions
            ),
        )
        outside = any(r.state == "OUTSIDE_BAND" for r in plan.rows)
        blocked = original_status == "BLOCKED"
        card = card.model_copy(
            update={
                "control_quality": quality(
                    action=not abstained,
                    permitted=outside if not blocked else False,
                    blocked=blocked,
                    required=outside and not blocked,
                )
            }
        )
        if original_status == "NO_ACTION" and not outside:
            card = card.model_copy(update={"control_quality": "CORRECT_ABSTENTION"})
        events = [
            self._event(card, "INPUT", plan.config),
            self._event(card, "DATA_FETCH", plan.snapshot, status="FROZEN_PORTFOLIO_SNAPSHOT"),
            self._event(card, "FEATURE_CALCULATION", plan.rows, status="AUTHORITATIVE_DRIFT"),
            self._event(
                card,
                "NO_ACTION" if abstained else "DECISION",
                initial,
                status=original_status,
                reasons=plan.reasons,
            ),
        ]
        for a in plan.actions:
            events.append(
                self._event(
                    card,
                    "ROUTE",
                    a.route,
                    status=a.route.status,
                    outputs={
                        "action_id": a.action_id,
                        "execution_decision_id": a.execution_decision_id,
                    },
                )
            )
            events.append(
                self._event(
                    card,
                    "RISK_APPROVE" if a.risk.status == "PASS" else "RISK_REJECT",
                    a.risk,
                    status=a.risk.status,
                )
            )
        card = self._links(
            card, events, {a.execution_decision_id for a in plan.actions}, rows, cutoff
        )
        if known_status == "COMPLETED":
            bound = {r.execution_id for r in card.executions if r.category == "CONFIRMED"}
            if not {str(i) for i in plan.settled_execution_ids}.issubset(bound):
                card = card.model_copy(
                    update={
                        "outcome": "RECONCILIATION_REQUIRED",
                        "abstained": True,
                        "abstention_scope": "EXECUTION",
                        "abstention_reasons": ("CANONICAL_COMPLETION_EXECUTION_LINK_UNAVAILABLE",),
                    }
                )
            else:
                card = card.model_copy(
                    update={
                        "outcome": "COMPLETED",
                        "evidence_asof": max(card.evidence_asof, plan.updated_at),
                    }
                )
        return self._finish(card, events, cutoff)

    def _historical(self, run, e, row, projected, cutoff):
        d = e.decision
        target = projected.opening_outcome
        predicted = row.prediction.predicted_return
        actual = target.opening_return if target else None
        with localcontext() as ctx:
            ctx.prec = 256
            error = (
                abs(predicted - actual) if predicted is not None and actual is not None else None
            )
        card = self._card(
            "OPPORTUNITY",
            "RESEARCH_REPLAY",
            f"{run.run_id}:{e.episode_id}",
            d.decision_id,
            d.decision_at,
            {
                "decision": d,
                "prediction": row.prediction,
                "retrieval": row.retrieval,
                "known_target": target,
            },
            inputs=d,
            ticker=d.ticker,
            issuer=d.issuer,
            run_id=run.run_id,
            episode_id=e.episode_id,
            action=row.hypothetical_decision,
            outcome="PREDICTION_SCORED" if target else projected.outcome_state,
            abstained=True,
            confidence=row.prediction.confidence,
            trust_classification=row.trust_state,
            expected_net_edge_usd=row.cost_adjusted_edge_usd,
            abstention_reasons=row.reasons,
            reasons=row.reasons,
            prediction=PredictionEvaluation(
                predicted_return=predicted,
                actual_opening_return=actual,
                predicted_direction=row.prediction.direction,
                actual_direction=direction(actual) if actual is not None else None,
                direction_correct=row.prediction.direction == direction(actual)
                if actual is not None and row.prediction.direction is not None
                else None,
                absolute_magnitude_error=error,
                noise_suppressed=row.trust_state == "LIKELY_NOISE",
            ),
        )
        card = card.model_copy(
            update={
                "control_quality": "CORRECT_ABSTENTION",
                "abstention_scope": "EXECUTION",
                "evidence_asof": target.available_at if target else d.decision_at,
            }
        )
        events = [
            self._event(card, "INPUT", d.policy),
            self._event(card, "DATA_FETCH", d.provenance, status="POINT_IN_TIME_REFERENCES"),
            self._event(card, "FEATURE_CALCULATION", d.sample, status=d.data_quality),
            self._event(card, "TRUST", d.trust, status=row.trust_state),
            self._event(
                card,
                "NO_ACTION",
                row.model_dump(exclude={"hypothetical_outcome"}),
                status=row.hypothetical_decision,
                reasons=row.reasons,
            ),
        ]
        return self._finish(card, events, cutoff)

    def _demo(self, result, lifecycle, cutoff):
        d = result.opportunity
        acted = d.action == "BUY"
        card = self._card(
            "OPPORTUNITY",
            "DEMO_OPPORTUNITY",
            d.opportunity_id,
            d.opportunity_id,
            d.evaluated_at,
            result,
            ticker=d.ticker,
            issuer=d.issuer,
            action=d.action,
            outcome="PROPOSED" if acted else "REJECTED",
            abstained=not acted,
            requested_exposure_usd=d.inputs.requested_notional_usd,
            confidence=d.confidence,
            trust_classification=d.source_trust_classification,
            route=route_evaluation(result.route_decision),
            reasons=tuple(d.reason_codes),
            abstention_reasons=tuple(d.reason_codes) if not acted else (),
            expected_net_edge_usd=d.economics.net_hypothetical_edge_usd if d.economics else None,
            prediction=PredictionEvaluation(
                noise_suppressed=not acted and d.source_trust_classification == "LIKELY_NOISE"
            ),
        )
        card = card.model_copy(
            update={
                "control_quality": quality(
                    action=acted,
                    permitted=d.status == "ACTIONABLE",
                    blocked=d.status != "ACTIONABLE",
                )
            }
        )
        events = [
            self._event(card, "INPUT", d.inputs),
            self._event(
                card,
                "TRUST",
                {"assessment": str(d.trust_assessment_id), "fixture": result.trust_fixture_sha256},
                status=d.source_trust_classification,
            ),
            self._event(card, "ROUTE", result.route_decision, status=result.route_decision.status),
            self._event(
                card,
                "DECISION" if acted else "NO_ACTION",
                d,
                status=d.status,
                reasons=d.reason_codes,
            ),
        ]
        if self.demo_preparation:
            risks, quotes, preparations, simulations = self.demo_preparation.snapshots()
            stages = (
                [
                    ("RISK", r.risk, r.risk.evaluated_at, r.risk.status, r.risk.opportunity_id)
                    for r in risks
                ]
                + [
                    (
                        "QUOTE",
                        q,
                        q.quote.quoted_at if q.quote else q.risk_before_quote.evaluated_at,
                        "SYNTHETIC_QUOTE" if q.status == "QUOTED" else "BLOCKED",
                        q.opportunity.opportunity_id,
                    )
                    for q in quotes
                ]
                + [
                    (
                        "BUILD",
                        p,
                        p.transaction.prepared_at
                        if p.transaction
                        else p.risk_revalidation.evaluated_at,
                        "DEMO_PREPARATION" if p.status == "PREPARED" else "BLOCKED",
                        p.risk_revalidation.opportunity_id,
                    )
                    for p in preparations
                ]
                + [
                    (
                        "SIMULATION",
                        s.simulation,
                        s.simulation.evaluated_at,
                        s.simulation.status,
                        next(
                            (
                                p.transaction.opportunity_id
                                for p in preparations
                                if p.transaction
                                and p.transaction.transaction_id == s.simulation.transaction_id
                            ),
                            None,
                        ),
                    )
                    for s in simulations
                ]
            )
            for kind, payload, at, status, opportunity_id in sorted(stages, key=lambda r: r[2]):
                if opportunity_id != d.opportunity_id or at > cutoff:
                    continue
                if kind == "RISK":
                    kind = "RISK_APPROVE" if status == "PASS" else "RISK_REJECT"
                if kind == "SIMULATION" and status == "SIMULATION_FAIL":
                    kind = "SIMULATION_FAILURE"
                events.append(
                    self._event(
                        card, kind, payload, at=at, status=status, reasons=payload.reason_codes
                    )
                )
                outcome = {
                    "QUOTE": "QUOTED",
                    "BUILD": "PREPARED",
                    "SIMULATION": "SIMULATED",
                    "SIMULATION_FAILURE": "BLOCKED",
                    "RISK_REJECT": "BLOCKED",
                }.get(kind)
                blocked_stage = status == "BLOCKED" or kind in {"RISK_REJECT", "SIMULATION_FAILURE"}
                if blocked_stage:
                    outcome = "BLOCKED"
                card = card.model_copy(
                    update={
                        "evidence_asof": max(card.evidence_asof, at),
                        **({"outcome": outcome} if outcome else {}),
                    }
                )
                if blocked_stage:
                    card = card.model_copy(
                        update={
                            "abstained": True,
                            "abstention_scope": "EXECUTION",
                            "abstention_reasons": tuple(payload.reason_codes),
                        }
                    )
                elif kind in {"QUOTE", "BUILD", "SIMULATION"}:
                    card = card.model_copy(
                        update={
                            "abstained": not acted,
                            "abstention_scope": "DECISION",
                            "abstention_reasons": tuple(d.reason_codes) if not acted else (),
                        }
                    )
        if lifecycle:
            events.extend(
                [
                    self._event(
                        card,
                        "RISK_APPROVE",
                        lifecycle.risk,
                        at=lifecycle.risk.evaluated_at,
                        status=lifecycle.risk.status,
                    ),
                    self._event(
                        card,
                        "QUOTE",
                        lifecycle.quote,
                        at=lifecycle.quote.quoted_at,
                        status="SYNTHETIC_QUOTE",
                    ),
                    self._event(
                        card,
                        "BUILD",
                        lifecycle.preparation,
                        at=lifecycle.preparation.prepared_at,
                        status="DEMO_PREPARATION",
                    ),
                    self._event(
                        card,
                        "SIMULATION",
                        lifecycle.simulation,
                        at=lifecycle.simulation.evaluated_at,
                        status="LOCAL_DEMO_SIMULATION",
                    ),
                    self._event(
                        card,
                        "POSITION",
                        lifecycle.position,
                        at=lifecycle.position.entered_at,
                        status="PAPER_FILLED",
                        outputs={"position_id": str(lifecycle.position.position_id)},
                    ),
                ]
            )
            card = card.model_copy(
                update={"outcome": "PAPER_FILLED", "evidence_asof": lifecycle.position.entered_at}
            )
            if lifecycle.exit and lifecycle.exit.exited_at <= cutoff:
                events.append(
                    self._event(
                        card,
                        "EXIT",
                        lifecycle.exit,
                        at=lifecycle.exit.exited_at,
                        status="PAPER_EXITED",
                    )
                )
                # Reuse the established paper evaluation, never recalculate its P&L here.
                score = self.paper.scorecard(lifecycle.position.position_id)
                card = card.model_copy(
                    update={
                        "outcome": "PAPER_EXITED",
                        "paper_pnl": score.pnl,
                        "evidence_asof": lifecycle.exit.exited_at,
                    }
                )
        return self._finish(card, events, cutoff)

    def capture(self, *, at=None):
        with self.lock:
            now = self.clock()
            cutoff = at or now
            if cutoff > now:
                raise ValueError("Future evaluation cutoff refused")
            execution_page = self.terminal.executions(TerminalQuery(limit=100), now)
            if execution_page.has_more:
                raise ValueError("Execution evaluation inspection bound exceeded")
            rows = execution_page.items
            cards, events = [], []

            def accept(result):
                card, trail = result
                cards.append(card)
                events.extend(trail)

            for p in self.exposure.list_original(self.terminal.layer.mode, cutoff):
                accept(self._direct(p, rows, cutoff))
            scans = self.scans.list(mode=self.mode)
            for scan in scans:
                if scan.timestamp <= cutoff:
                    accept(self._scan(scan, rows, cutoff))
            seen = {s.decision_id for s in scans if s.timestamp <= cutoff}
            agent_runs = self.terminal.agents.list_runs(self.mode, cutoff, limit=101)
            if len(agent_runs) > 100:
                raise ValueError("Agent evaluation inspection bound exceeded")
            for run in agent_runs:
                if len(cards) > 500:
                    raise ValueError("Decision inspection bound exceeded")
                if run.decision_id not in seen:
                    accept(self._agent(run, rows, cutoff))
            for plan in self.terminal.portfolio.store.list_plans(mode=self.mode):
                if plan.created_at <= cutoff:
                    accept(self._portfolio(plan, rows, cutoff))
            projected = self.terminal.episodes(EpisodeQuery(limit=100, as_of=cutoff), now)
            if projected.has_more:
                raise ValueError("Historical evaluation inspection bound exceeded")
            episodes = {(p.run_id, p.episode_id): p for p in projected.items}
            for run in self.terminal.research.list(self.terminal.layer.mode):
                replay = {r.episode_id: r for r in run.rows}
                for e in run.episodes:
                    if (run.run_id, e.episode_id) in episodes:
                        accept(
                            self._historical(
                                run,
                                e,
                                replay[e.episode_id],
                                episodes[(run.run_id, e.episode_id)],
                                cutoff,
                            )
                        )
            if self.mode == "DEMO" and self.demo_flow:
                paper = self.paper.list() if self.paper else ()
                for result in self.demo_flow.snapshots():
                    if result.opportunity.evaluated_at <= cutoff:
                        lifecycle = next(
                            (
                                p
                                for p in paper
                                if p.order.opportunity_id == result.opportunity.opportunity_id
                                and p.position.entered_at <= cutoff
                            ),
                            None,
                        )
                        accept(self._demo(result, lifecycle, cutoff))
            linked_ids = {r.execution_id for c in cards for r in c.executions}
            for row in rows:
                if row.execution_id in linked_ids:
                    continue
                history = self.terminal.execution.history(row.execution_id, mode=self.mode)
                first = history[0]
                if first.created_at > cutoff:
                    continue
                # A host execution may predate the consolidated decision catalogs. Retain
                # its actual risk/input authority and explicitly flag the missing upstream link.
                card = self._card(
                    first.evidence.purpose,
                    "EXECUTION_JOURNAL",
                    row.execution_id,
                    first.decision_id,
                    first.created_at,
                    first.evidence,
                    correlation_id=first.correlation_id,
                    action="PROPOSE",
                    outcome="PROPOSED",
                    abstained=False,
                    requested_exposure_usd=first.evidence.notional_usd,
                    confidence=first.evidence.confidence,
                    trust_classification=first.evidence.trust_state,
                    reasons=("UPSTREAM_DECISION_CATALOG_LINK_UNAVAILABLE",),
                )
                trail = [
                    self._event(card, "INPUT", first.evidence),
                    self._event(card, "DECISION", first.evidence, status="PROPOSAL"),
                ]
                accept(
                    self._finish(
                        self._links(card, trail, {first.decision_id}, rows, cutoff), trail, cutoff
                    )
                )
            if len(cards) > 500 or len(events) > 20000:
                raise ValueError("Evaluation capture inspection bound exceeded")
            self.audit.append(cards, events)
            # Return the persisted first capture, not a timestamp-varying duplicate.
            ids = {c.evaluation_id for c in cards}
            return tuple(
                c for c in self.store.list(Scorecard, mode=self.mode) if c.evaluation_id in ids
            )

    def list(self, query):
        if query.data_mode and query.data_mode != self.mode:
            raise ValueError("Cross-mode evaluation query refused")
        cutoff = query.as_of or self.clock()
        if query.after and query.before and query.after > query.before:
            raise ValueError("Inverted date filter")
        cards = self.capture(at=cutoff)
        selected = tuple(
            c
            for c in cards
            if (
                (not query.decision_id or c.decision_id == query.decision_id)
                and (
                    not query.ticker
                    or c.ticker == query.ticker
                    or any(a.get("asset") == query.ticker for a in c.allocations)
                )
                and (not query.scorecard_type or c.scorecard_type == query.scorecard_type)
                and (not query.outcome or c.outcome == query.outcome)
                and (
                    not query.execution_status
                    or any(r.lifecycle_state == query.execution_status for r in c.executions)
                )
                and (not query.after or c.decision_at >= query.after)
                and (not query.before or c.decision_at <= query.before)
            )
        )
        return tuple(sorted(selected, key=lambda c: (c.decision_at, c.origin_id), reverse=True))

    @staticmethod
    def metrics(cards):
        # Descriptive decision evaluations; independent classification labels are unavailable.
        scored = [c for c in cards if c.prediction.direction_correct is not None]
        high = [c for c in scored if c.confidence == "HIGH"]
        with localcontext() as ctx:
            ctx.prec = 256

            def accuracy(items):
                return (
                    Decimal(sum(c.prediction.direction_correct for c in items)) / len(items)
                    if items
                    else None
                )

            return EvaluationMetrics(
                decision_count=len(cards),
                directional_samples=len(scored),
                directional_accuracy=accuracy(scored),
                high_confidence_samples=len(high),
                high_confidence_accuracy=accuracy(high),
                control_quality_counts=dict(Counter(c.control_quality for c in cards)),
            )

    def events(self, cards):
        ids = {i for c in cards for i in c.event_ids}
        events = self.store.list(AuditEvent, mode=self.mode)
        selected = tuple(sorted((e for e in events if e.event_id in ids), key=self.audit.order))
        if ids != {e.event_id for e in selected}:
            raise ValueError("Evaluation trace is incomplete")
        return selected
