"""The sole prepared → execution boundary. Phase 8 supplies only a dry-run gateway."""

from abc import ABC, abstractmethod

from app.models.execution import ExecutionAttempt, ExecutionControls, UserConfirmation, fingerprint
from app.services.execution_builders import current_quote
from app.services.execution_simulation import ExecutionSimulationService
from app.services.funding import FundingService
from app.services.risk import RiskEngine


class ExecutionGateway(ABC):
    @abstractmethod
    def submit(self, attempt, *, now, funding_state):
        """Return blocking reasons or use a separately verified future execution mechanism."""


class DryRunExecutionGateway(ExecutionGateway):
    def __init__(self, controls):
        self.controls = ExecutionControls.model_validate_json(controls.model_dump_json())

    def submit(self, attempt, *, now, funding_state):
        """All hard controls evaluated independently. No transport/signer exists here."""
        attempt = ExecutionAttempt.model_validate_json(attempt.model_dump_json())
        reasons = []
        controls = self.controls
        if attempt.data_mode != controls.data_mode:
            reasons.append("MODE_MISMATCH")
        if attempt.external_tracking_only or attempt.state in {
            "EXECUTION_SUBMITTED",
            "EXECUTION_PENDING",
            "EXECUTION_UNKNOWN",
        }:
            reasons.append("RECONCILE_EXISTING_ATTEMPT_NEVER_RESUBMIT")
        if attempt.state != "APPROVAL_CONFIRMED":
            reasons.append("EXECUTION_STATE_NOT_READY")
        risk = RiskEngine().evaluate_execution(attempt.evidence, now=now)
        if (
            risk.status != "PASS"
            or attempt.risk is None
            or attempt.risk.status != "PASS"
            or attempt.risk.evidence_digest != fingerprint(attempt.evidence)
        ):
            reasons.append("RISK_NOT_APPROVED")
        quote = attempt.quote
        route = attempt.route
        if quote is None or route is None:
            reasons.append("ROUTE_UNAVAILABLE")
        else:
            try:
                current_quote(quote, now)
            except ValueError:
                reasons.append("QUOTE_EXPIRED_REQUOTE_REBUILD_RESIMULATE")
            if fingerprint(route.critical()) != route.fingerprint or route.quote != quote:
                reasons.append("ROUTE_FINGERPRINT_MISMATCH")
            check = FundingService().check(
                attempt.evidence.notional_usd,
                funding_state,
                wallet=quote.request.userWalletAddress,
                mode=attempt.data_mode,
                now=now,
            )
            if (
                check.status != "PASS"
                or check.required_base_units != quote.request.amount
                or attempt.funding is None
                or fingerprint(check.state) != fingerprint(attempt.funding.state)
            ):
                reasons.append("FUNDING_REVALIDATION_FAILED")
            if route.build.tx is not None and check.state is not None:
                transactions = (route.build.tx,) + (
                    (attempt.approval.transaction,) if attempt.approval is not None else ()
                )
                try:
                    FundingService().check_gas(
                        check.state, transactions, costs_usd=attempt.evidence.costs_usd, now=now
                    )
                except ValueError:
                    reasons.append("NATIVE_GAS_FUNDING_OR_COST_INVALID")
            if attempt.simulation is None:
                reasons.append("SIMULATION_REQUIRED")
            else:
                try:
                    matches = ExecutionSimulationService.matches(
                        attempt.simulation, route, now=now, mode=attempt.data_mode
                    )
                except ValueError:
                    matches = False
                if not matches:
                    reasons.append("EXACT_SIMULATION_REQUIRED")
                if not attempt.simulation.live_equivalence_verified:
                    reasons.append("LIVE_EQUIVALENCE_NOT_VERIFIED")
            if route.approval_required:
                from app.services.execution_builders import ApprovalService

                if (
                    attempt.approval is None
                    or attempt.approval_allowance is None
                    or attempt.approval_simulation is None
                ):
                    reasons.append("APPROVAL_NOT_CONFIRMED")
                elif not ApprovalService().confirmed(
                    attempt.approval, route, attempt.approval_allowance, now=now
                ) or not ExecutionSimulationService.matches(
                    attempt.approval_simulation, attempt.approval, now=now, mode=attempt.data_mode
                ):
                    reasons.append("EXACT_APPROVAL_SIMULATION_OR_CONFIRMATION_REQUIRED")
            elif (
                route.allowance is None
                or not 0 <= (now - route.allowance.observed_at).total_seconds() <= 120
            ):
                reasons.append("ALLOWANCE_STALE")
            if quote.route.executionMode == "RFQ":
                reasons.append("RFQ_SETTLEMENT_EQUIVALENCE_UNVERIFIED")
            if controls.approval_mode == "PROPOSE_ONLY":
                confirmation = attempt.user_confirmation
                if confirmation is None or not self.confirmation_valid(confirmation, attempt, now):
                    reasons.append("EXPLICIT_USER_CONFIRMATION_REQUIRED")
            reasons.append(
                "RFQ_LIVE_GATE_BLOCKED"
                if quote.route.executionMode == "RFQ"
                else "SWAP_LIVE_GATE_BLOCKED"
            )
        # A config toggle or successful fixture can never reach a transport.
        reasons.extend(
            (
                "DRY_RUN_STOP_NO_EXECUTION",
                "LIVE_TRADING_DISABLED",
                "AGENTIC_WALLET_LIVE_GATE_BLOCKED",
            )
        )
        return tuple(dict.fromkeys(reasons))

    @staticmethod
    def confirmation_valid(confirmation, attempt, now):
        confirmation = UserConfirmation.model_validate_json(confirmation.model_dump_json())
        return (
            attempt.route is not None
            and confirmation.route_fingerprint == attempt.route.fingerprint
            and confirmation.decision_id == attempt.decision_id
            and attempt.route.prepared_at
            <= confirmation.confirmed_at
            <= now
            < confirmation.expires_at
            <= attempt.quote.expires_at
        )
