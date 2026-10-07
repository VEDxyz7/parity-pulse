"""Production-shaped Phase 8 preparation and fail-closed orchestration, non-live only."""

import logging
import threading
from uuid import uuid4

from app.clients.common import ProviderError
from app.clients.execution_gateway import DryRunExecutionGateway
from app.models.execution import ExecutionAttempt, ExecutionControls, QuoteRequest, fingerprint
from app.services.aggregator_quote import AggregatorQuoteService
from app.services.execution_builders import ApprovalService, ExecutionRouteBuilder
from app.services.execution_simulation import ExecutionSimulationService
from app.services.execution_state_machine import ExecutionStateMachine
from app.services.funding import FundingService
from app.services.risk import RiskEngine

logger = logging.getLogger("parity.execution")


class SafetyExecutionService:
    def __init__(self, provider, store, controls, *, clock):
        self.provider, self.store, self.clock = provider, store, clock
        self.controls = ExecutionControls.model_validate_json(controls.model_dump_json())
        self.risk = RiskEngine()
        self.funding = FundingService()
        self.quotes = AggregatorQuoteService(provider)
        self.builder = ExecutionRouteBuilder()
        self.approvals = ApprovalService()
        self.simulator = ExecutionSimulationService(provider)
        self.machine = ExecutionStateMachine()
        self.gateway = DryRunExecutionGateway(self.controls)
        self.lock = threading.RLock()

    def _save(self, previous, result):
        self.store.save(result, expected_version=previous.version)
        logger.info(
            "EXECUTION_SAFETY",
            extra={
                "event_fields": {
                    "execution_id": str(result.execution_id),
                    "decision_id": result.decision_id,
                    "correlation_id": result.correlation_id,
                    "data_mode": result.data_mode,
                    "status": result.state,
                }
            },
        )
        return result

    def _move(self, attempt, target, **updates):
        result = self.machine.transition(attempt, target, now=self.clock(), **updates)
        return self._save(attempt, result)

    def prepare(self, evidence, funding_state, *, target_contract, allowance, correlation_id):
        """Host-only verified observations; public requests cannot supply safety facts.

        Same decision is idempotent. Requote is explicit and bounded; no signature is produced.
        """
        with self.lock:
            old = self.store.for_decision(evidence.decision_id, mode=self.controls.data_mode)
            if old:
                if fingerprint(old.evidence) != fingerprint(evidence):
                    raise ValueError("DECISION_ALREADY_OWNED_DIFFERENT_EVIDENCE")
                return old
            now = self.clock()
            attempt = ExecutionAttempt(
                execution_id=uuid4(),
                request_id=uuid4(),
                decision_id=evidence.decision_id,
                correlation_id=correlation_id,
                data_mode=self.controls.data_mode,
                source="TEST_FIXTURE" if self.controls.data_mode == "DEMO" else "BINANCE_WEB3",
                state="PROPOSAL",
                version=0,
                generation=0,
                created_at=now,
                updated_at=now,
                evidence=evidence,
            )
            attempt, owned = self.store.claim(attempt)
            if not owned:
                return attempt
            if self.store.pending(mode=self.controls.data_mode):
                return self._move(attempt, "BLOCKED", reason_codes=("RESTART_STATE_UNRESOLVED",))
            risk = self.risk.evaluate_execution(evidence, now=now)
            funding = self.funding.check(
                evidence.notional_usd,
                funding_state,
                wallet=funding_state.wallet if funding_state else None,
                mode=self.controls.data_mode,
                now=now,
            )
            if risk.status != "PASS" or funding.status != "PASS":
                return self._move(
                    attempt,
                    "BLOCKED",
                    risk=risk,
                    funding=funding,
                    reason_codes=tuple(c.code for c in risk.checks if not c.passed)
                    + funding.reasons,
                )
            if funding.conversion_cost_usd != evidence.conversion_cost_usd:
                return self._move(
                    attempt, "BLOCKED", reason_codes=("FUNDING_CONVERSION_COST_RISK_MISMATCH",)
                )
            if (
                self.controls.data_mode == "DEMO"
                and getattr(self.provider, "fixture_only", False) is not True
            ):
                return self._move(attempt, "BLOCKED", reason_codes=("DEMO_PROVIDER_ISOLATION",))
            if self.controls.data_mode != "DEMO" and getattr(self.provider, "fixture_only", False):
                return self._move(
                    attempt, "BLOCKED", reason_codes=("REAL_MODE_HAS_NO_FIXTURE_FALLBACK",)
                )
            attempt = self._move(attempt, "RISK_APPROVED", risk=risk, funding=funding)
            return self._continue(attempt, funding_state, allowance, target_contract)

    def requote(self, attempt, *, funding_state, allowance):
        """A controlled fresh generation, never an implicit retry of a submitted order."""
        with self.lock:
            current = self.store.get(attempt.execution_id, mode=self.controls.data_mode)
            if (
                current.version != attempt.version
                or current.generation >= 2
                or current.quote is None
            ):
                raise ValueError("STALE_OR_EXHAUSTED_REQUOTE_ATTEMPT")
            now = self.clock()
            risk = self.risk.evaluate_execution(current.evidence, now=now)
            funding = self.funding.check(
                current.evidence.notional_usd,
                funding_state,
                wallet=current.quote.request.userWalletAddress,
                mode=current.data_mode,
                now=now,
            )
            refreshed = self.machine.invalidate(
                current, now=now, evidence=current.evidence, risk=risk, funding=funding
            )
            self._save(current, refreshed)
            # Dedicated preparation uses the same existing attempt, not a second order/decision.
            return self._continue(
                refreshed, funding_state, allowance, current.quote.request.toTokenAddress
            )

    def _continue(self, attempt, funding_state, allowance, target):
        funding = attempt.funding
        try:
            request = QuoteRequest(
                binanceChainId="56",
                amount=funding.required_base_units,
                fromTokenAddress=funding.state.asset.contract,
                toTokenAddress=target,
                userWalletAddress=funding.state.wallet,
            )
            quote = self.quotes.select(
                request,
                mode=self.controls.data_mode,
                funding=funding,
                evidence=attempt.evidence,
                now=self.clock(),
            )
            attempt = self._move(attempt, "QUOTE_CREATED", quote=quote)
            response = self.provider.build(quote, slippage_bps=attempt.evidence.slippage_bps)
            route = self.builder.build(
                quote,
                response,
                slippage_bps=attempt.evidence.slippage_bps,
                allowance=allowance,
                now=self.clock(),
            )
            if route.build.tx is not None:
                self.funding.check_gas(
                    funding.state,
                    (route.build.tx,),
                    costs_usd=attempt.evidence.costs_usd,
                    now=self.clock(),
                )
            attempt = self._move(attempt, "ROUTE_BUILT", route=route)
            simulation = self.simulator.simulate(route, now=self.clock())
            if simulation.status != "PASS":
                approval_fields = {}
                if route.approval_required and route.quote.route.executionMode == "RFQ":
                    approval = self.approvals.prepare(
                        route, self.provider.approval(route), now=self.clock()
                    )
                    self.funding.check_gas(
                        funding.state,
                        (approval.transaction,),
                        costs_usd=attempt.evidence.costs_usd,
                        now=self.clock(),
                    )
                    approval_fields = {
                        "approval": approval,
                        "approval_simulation": self.simulator.simulate(
                            approval, now=self.clock(), mode=self.controls.data_mode
                        ),
                    }
                return self._move(
                    attempt,
                    "BLOCKED",
                    simulation=simulation,
                    reason_codes=simulation.reason_codes,
                    **approval_fields,
                )
            attempt = self._move(attempt, "SIMULATION_PASSED", simulation=simulation)
            if route.approval_required:
                attempt = self._move(attempt, "APPROVAL_REQUIRED")
                approval = self.approvals.prepare(
                    route, self.provider.approval(route), now=self.clock()
                )
                self.funding.check_gas(
                    funding.state,
                    (route.build.tx, approval.transaction),
                    costs_usd=attempt.evidence.costs_usd,
                    now=self.clock(),
                )
                sim = self.simulator.simulate(
                    approval, now=self.clock(), mode=self.controls.data_mode
                )
                if sim.status != "PASS":
                    return self._move(
                        attempt,
                        "BLOCKED",
                        approval=approval,
                        approval_simulation=sim,
                        reason_codes=sim.reason_codes,
                    )
                # Proposal only; approval is never signed or broadcast.
                return self._save(
                    attempt,
                    ExecutionAttempt.model_validate(
                        {
                            **attempt.model_dump(),
                            "approval": approval,
                            "approval_simulation": sim,
                            "version": attempt.version + 1,
                            "updated_at": self.clock(),
                            "reason_codes": (
                                "APPROVAL_REQUIRES_EXTERNAL_CONFIRMATION_NO_EXECUTION",
                            )
                            if sim.status == "PASS"
                            else sim.reason_codes,
                        }
                    ),
                )
            attempt = self._move(attempt, "APPROVAL_CONFIRMED")
            reasons = self.gateway.submit(attempt, now=self.clock(), funding_state=funding_state)
            return self._save(
                attempt,
                ExecutionAttempt.model_validate(
                    {
                        **attempt.model_dump(),
                        "reason_codes": reasons,
                        "version": attempt.version + 1,
                        "updated_at": self.clock(),
                    }
                ),
            )
        except (ProviderError, ValueError, TypeError):
            expired = attempt.quote is not None and self.clock() >= attempt.quote.expires_at
            return self._move(
                attempt,
                "EXECUTION_EXPIRED" if expired else "BLOCKED",
                reason_codes=(
                    "REQUOTE_REBUILD_RESIMULATE_REQUIRED"
                    if expired
                    else "PROVIDER_OR_PREPARATION_INVALID",
                ),
            )

    def confirm(self, attempt, confirmation):
        with self.lock:
            current = self.store.get(attempt.execution_id, mode=self.controls.data_mode)
            if (
                current.version != attempt.version
                or current.state != "APPROVAL_CONFIRMED"
                or not self.gateway.confirmation_valid(confirmation, current, self.clock())
            ):
                raise ValueError("INVALID_OR_STALE_EXPLICIT_CONFIRMATION")
            return self._save(
                current,
                ExecutionAttempt.model_validate(
                    {
                        **current.model_dump(),
                        "user_confirmation": confirmation,
                        "version": current.version + 1,
                        "updated_at": self.clock(),
                    }
                ),
            )

    def prepare_rfq_submission(self, attempt, *, signature):
        """Offline request formatting only. No signature is generated or sent/stored.

        Bind retries to one persistent requestId and exact request digest. Signature
        ownership/recovery and live RFQ settlement remain unverified Phase 9 prerequisites.
        """
        with self.lock:
            current = self.store.get(attempt.execution_id, mode=self.controls.data_mode)
            if current.version != attempt.version or current.external_tracking_only:
                raise ValueError("RECONCILE_EXISTING_RFQ_ATTEMPT")
            if current.route is None:
                raise ValueError("RFQ_ROUTE_REQUIRED")
            from app.services.execution_builders import current_quote

            current_quote(current.quote, self.clock())
            request = self.builder.rfq_submission(
                current.route, request_id=current.request_id, signature=signature
            )
            digest = fingerprint(
                {"route": current.route.fingerprint, "request": request.wire_body()}
            )
            if current.rfq_request_digest is not None and current.rfq_request_digest != digest:
                raise ValueError("RFQ_RETRY_PAYLOAD_CHANGED")
            if current.rfq_request_digest is None:
                current = self._save(
                    current,
                    ExecutionAttempt.model_validate(
                        {
                            **current.model_dump(),
                            "rfq_request_digest": digest,
                            "version": current.version + 1,
                            "updated_at": self.clock(),
                        }
                    ),
                )
            return current, request

    def observe_approval(self, attempt, observation, *, funding_state):
        """Verified external allowance triggers a fresh trade build and simulation.

        Prior approval remains in the journal; no approval transaction is sent here.
        """
        current = self.store.get(attempt.execution_id, mode=self.controls.data_mode)
        if current.version != attempt.version or current.state != "APPROVAL_REQUIRED":
            raise ValueError("APPROVAL_STATE_MISMATCH")
        if current.approval is None or current.approval_simulation is None:
            raise ValueError("APPROVAL_SIMULATION_REQUIRED")
        if not self.simulator.matches(
            current.approval_simulation, current.approval, now=self.clock(), mode=current.data_mode
        ) or not self.approvals.confirmed(
            current.approval, current.route, observation, now=self.clock()
        ):
            raise ValueError("APPROVAL_NOT_CONFIRMED")
        return self.requote(current, funding_state=funding_state, allowance=observation)

    def prepare_scan(self, scan, *, evidence, funding_state, allowance, correlation_id):
        """Bind the existing Phase 7 output; no agent may create authorization facts.

        Current real scans DEFER; current DEMO uses demo:* contracts and its existing
        local manifest pipeline. Neither is converted into execution-capable EVM evidence.
        """
        if (
            scan.data_mode != self.controls.data_mode
            or scan.final_action != "BUY"
            or scan.selected_candidate is None
        ):
            raise ValueError("PHASE7_SCAN_NOT_ACTIONABLE")
        candidate = scan.selected_candidate
        if (
            evidence.decision_id != scan.run_id
            or evidence.purpose != "OPPORTUNITY"
            or evidence.budget_usd != scan.mandate.budget_usd
            or evidence.risk_budget_usd != scan.mandate.risk_budget_usd
            or evidence.notional_usd != candidate.proposed_notional_usd
        ):
            raise ValueError("PHASE7_MANDATE_OR_SIZE_MISMATCH")
        return self.prepare(
            evidence,
            funding_state,
            target_contract=candidate.contract,
            allowance=allowance,
            correlation_id=correlation_id,
        )
