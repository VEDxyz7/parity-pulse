"""Strict exact-artifact state transitions. Every production submission remains forbidden."""

from app.models.execution import ExecutionAttempt, fingerprint
from app.services.execution_builders import ApprovalService, current_quote
from app.services.execution_simulation import ExecutionSimulationService

TERMINAL = {
    "EXECUTION_CONFIRMED",
    "EXECUTION_FAILED",
    "EXECUTION_EXPIRED",
    "EXECUTION_CANCELLED",
    "BLOCKED",
}
EXTERNAL = {"EXECUTION_SUBMITTED", "EXECUTION_PENDING", "EXECUTION_UNKNOWN"}
TRANSITIONS = {
    "PROPOSAL": {"RISK_APPROVED", "BLOCKED", "EXECUTION_CANCELLED"},
    "RISK_APPROVED": {"QUOTE_CREATED", "BLOCKED", "EXECUTION_CANCELLED", "EXECUTION_EXPIRED"},
    "QUOTE_CREATED": {"ROUTE_BUILT", "BLOCKED", "EXECUTION_EXPIRED", "EXECUTION_CANCELLED"},
    "ROUTE_BUILT": {"SIMULATION_PASSED", "BLOCKED", "EXECUTION_EXPIRED", "EXECUTION_CANCELLED"},
    "SIMULATION_PASSED": {
        "APPROVAL_REQUIRED",
        "APPROVAL_CONFIRMED",
        "BLOCKED",
        "EXECUTION_EXPIRED",
        "EXECUTION_CANCELLED",
    },
    "APPROVAL_REQUIRED": {
        "APPROVAL_CONFIRMED",
        "BLOCKED",
        "EXECUTION_EXPIRED",
        "EXECUTION_CANCELLED",
    },
    "APPROVAL_CONFIRMED": {
        "EXECUTION_SUBMITTED",
        "BLOCKED",
        "EXECUTION_EXPIRED",
        "EXECUTION_CANCELLED",
    },
    "EXECUTION_SUBMITTED": {
        "EXECUTION_PENDING",
        "EXECUTION_UNKNOWN",
        "EXECUTION_CONFIRMED",
        "EXECUTION_FAILED",
        "EXECUTION_EXPIRED",
        "EXECUTION_CANCELLED",
    },
    "EXECUTION_PENDING": {
        "EXECUTION_UNKNOWN",
        "EXECUTION_CONFIRMED",
        "EXECUTION_FAILED",
        "EXECUTION_EXPIRED",
        "EXECUTION_CANCELLED",
    },
    "EXECUTION_UNKNOWN": {
        "EXECUTION_PENDING",
        "EXECUTION_CONFIRMED",
        "EXECUTION_FAILED",
        "EXECUTION_EXPIRED",
        "EXECUTION_CANCELLED",
    },
}


class ExecutionStateMachine:
    def transition(self, attempt, target, *, now, **updates):
        attempt = ExecutionAttempt.model_validate_json(attempt.model_dump_json())
        if target not in TRANSITIONS.get(attempt.state, set()):
            raise ValueError("ILLEGAL_EXECUTION_TRANSITION")
        if target == "EXECUTION_SUBMITTED":
            raise ValueError("LIVE_EXECUTION_GATES_BLOCKED")
        if now < attempt.updated_at:
            raise ValueError("EXECUTION_CLOCK_REGRESSION")
        immutable = {
            "execution_id",
            "request_id",
            "decision_id",
            "correlation_id",
            "data_mode",
            "source",
            "version",
            "generation",
            "created_at",
            "state",
            "updated_at",
        }
        if immutable.intersection(updates):
            raise ValueError("IMMUTABLE_ATTEMPT_IDENTITY")
        values = {
            **attempt.model_dump(),
            **updates,
            "state": target,
            "updated_at": now,
            "version": attempt.version + 1,
        }
        result = ExecutionAttempt.model_validate(values)
        if attempt.state in EXTERNAL and target in TERMINAL:
            expected = {
                "EXECUTION_CONFIRMED": {"FILLED", "success"},
                "EXECUTION_FAILED": {"FAILED", "failed"},
                "EXECUTION_EXPIRED": {"EXPIRED"},
                "EXECUTION_CANCELLED": {"CANCELLED"},
            }
            if (
                not result.external_tracking_only
                or "external_status" not in updates
                or result.external_status not in expected.get(target, set())
            ):
                raise ValueError("DOCUMENTED_EXTERNAL_TERMINAL_EVIDENCE_REQUIRED")
        preparation = {
            "QUOTE_CREATED",
            "ROUTE_BUILT",
            "SIMULATION_PASSED",
            "APPROVAL_REQUIRED",
            "APPROVAL_CONFIRMED",
        }
        if target in preparation:
            from app.services.risk import RiskEngine

            if (
                result.risk is None
                or result.risk.status != "PASS"
                or result.funding is None
                or result.funding.status != "PASS"
                or RiskEngine().evaluate_execution(result.evidence, now=now).status != "PASS"
            ):
                raise ValueError("CURRENT_RISK_AND_FUNDING_REQUIRED")
        if target == "RISK_APPROVED" and not (
            result.risk
            and result.risk.status == "PASS"
            and result.risk.evaluated_at == now
            and result.funding
            and result.funding.status == "PASS"
            and result.funding.evaluated_at == now
        ):
            raise ValueError("MATCHING_CURRENT_RISK_AND_FUNDING_REQUIRED")
        if target == "QUOTE_CREATED":
            if result.quote is None or result.funding is None or result.funding.state is None:
                raise ValueError("QUOTE_AND_FUNDING_REQUIRED")
            current_quote(result.quote, now)
            q, s = result.quote, result.funding.state
            if (
                q.request.amount,
                q.request.fromTokenAddress,
                q.request.userWalletAddress,
                int(q.route.fromToken.decimal),
            ) != (result.funding.required_base_units, s.asset.contract, s.wallet, s.asset.decimals):
                raise ValueError("QUOTE_FUNDING_BINDING_MISMATCH")
        if target == "ROUTE_BUILT":
            if result.route is None:
                raise ValueError("EXACT_ROUTE_REQUIRED")
            current_quote(result.quote, now)
        if target == "SIMULATION_PASSED":
            if result.simulation is None or not ExecutionSimulationService.matches(
                result.simulation, result.route, now=now, mode=result.data_mode
            ):
                raise ValueError("EXACT_SUCCESSFUL_SIMULATION_REQUIRED")
        if target == "APPROVAL_REQUIRED" and (
            result.route is None or not result.route.approval_required
        ):
            raise ValueError("APPROVAL_NOT_REQUIRED")
        if target == "APPROVAL_CONFIRMED":
            current_quote(result.quote, now)
            if not ExecutionSimulationService.matches(
                result.simulation, result.route, now=now, mode=result.data_mode
            ):
                raise ValueError("EXACT_TRADE_SIMULATION_REQUIRED")
            if result.route.approval_required:
                if (
                    result.approval is None
                    or result.approval_simulation is None
                    or result.approval_allowance is None
                ):
                    raise ValueError("APPROVAL_NOT_CONFIRMED")
                if not ExecutionSimulationService.matches(
                    result.approval_simulation, result.approval, now=now, mode=result.data_mode
                ) or not ApprovalService().confirmed(
                    result.approval, result.route, result.approval_allowance, now=now
                ):
                    raise ValueError("APPROVAL_NOT_CONFIRMED")
            elif (
                result.route.allowance is None
                or not 0 <= (now - result.route.allowance.observed_at).total_seconds() <= 120
            ):
                raise ValueError("CURRENT_ALLOWANCE_REQUIRED")
        if target == "EXECUTION_SUBMITTED":
            # Even correctly simulated fixture evidence cannot generate a production grant.
            raise ValueError("LIVE_EXECUTION_GATES_BLOCKED")
        if target == "EXECUTION_CONFIRMED" and not result.external_tracking_only:
            raise ValueError("EXTERNAL_TERMINAL_EVIDENCE_REQUIRED")
        return result

    def invalidate(self, attempt, *, now, evidence, risk, funding):
        """Explicit pre-submission refresh; clears every old quote/simulation/approval/consent.

        Same attempt/requestId survives retries. Any observed submission/unknown blocks refresh.
        """
        if (
            attempt.external_tracking_only
            or attempt.state in EXTERNAL
            or attempt.state == "EXECUTION_CONFIRMED"
        ):
            raise ValueError("RECONCILE_EXISTING_ATTEMPT_NEVER_DUPLICATE")
        if attempt.rfq_request_digest is not None:
            raise ValueError("RFQ_REQUEST_ALREADY_BOUND_RECONCILE_BEFORE_NEW_ORDER")
        if (
            risk.status != "PASS"
            or funding.status != "PASS"
            or fingerprint(evidence) != risk.evidence_digest
        ):
            raise ValueError("REVALIDATED_RISK_AND_FUNDING_REQUIRED")
        if risk.evaluated_at != now or funding.evaluated_at != now or now < attempt.updated_at:
            raise ValueError("CURRENT_REVALIDATION_REQUIRED")
        values = {
            **attempt.model_dump(),
            "evidence": evidence,
            "risk": risk,
            "funding": funding,
            "state": "RISK_APPROVED",
            "generation": attempt.generation + 1,
            "version": attempt.version + 1,
            "updated_at": now,
            "quote": None,
            "route": None,
            "simulation": None,
            "approval": None,
            "approval_simulation": None,
            "approval_allowance": None,
            "user_confirmation": None,
            "reason_codes": ("REQUOTE_REBUILD_REFINGERPRINT_RESIMULATE",),
        }
        return ExecutionAttempt.model_validate(values)
