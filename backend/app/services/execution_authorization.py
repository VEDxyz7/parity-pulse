"""Host-owned runtime and exact-envelope checks; no signing or transport here."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.models.execution import fingerprint
from app.services.execution_builders import current_quote
from app.services.execution_gates import LiveExecutionError


@dataclass(frozen=True)
class RuntimeExecutionPolicy:
    execution_mode: str = "DRY_RUN"
    live_trading_enabled: bool = False
    require_simulation: bool = True
    approval_mode: str = "PROPOSE_ONLY"
    data_mode: str = "LIVE_READ_ONLY"

    def require(self):
        if (
            self.execution_mode != "LIVE"
            or self.live_trading_enabled is not True
            or self.require_simulation is not True
            or self.approval_mode != "PROPOSE_ONLY"
            or self.data_mode != "LIVE_READ_ONLY"
        ):
            raise LiveExecutionError("LIVE_RUNTIME_DISABLED")


DISABLED_RUNTIME = RuntimeExecutionPolicy()


def wallet_gate_required(kind):
    if kind not in {"LOCAL_KEY", "AGENTIC_WALLET", "ALTANA"}:
        raise LiveExecutionError("SIGNER_KIND_UNSUPPORTED")
    return kind != "LOCAL_KEY"


def require_write(gates, runtime, route, *, wallet=False):
    gates.require(route, wallet=wallet)
    runtime.require()


@dataclass(frozen=True)
class TransactionAuthorization:
    """One consumed consent, exact prepared envelope and final-boundary clock checks.

    This binds opaque calldata bytes; it is NOT a calldata semantics decoder or proof
    of live simulation equivalence. Existing equivalence blockers stay mandatory.
    """

    leg: object
    consent: object
    journal: object
    clock: Callable = lambda: datetime.now(UTC)

    def check(self, tx, *, nonce):
        self.check_bindings(tx, nonce=nonce)
        from app.services.execution_simulation import ExecutionSimulationService

        if (
            not ExecutionSimulationService.matches(
                self.leg.simulation, self.leg.route, now=self.clock(), mode="LIVE_READ_ONLY"
            )
            or not self.leg.simulation.live_equivalence_verified
        ):
            raise LiveExecutionError("EXACT_ENVELOPE_SIMULATION_UNVERIFIED")
        if not self.leg.envelope.calldata_semantics_verified:
            raise LiveExecutionError("SWAP_CALLDATA_SEMANTICS_UNVERIFIED")

    def check_bindings(self, tx, *, nonce):
        """Structural checks are separately testable; never alone authorize signing."""
        now = self.clock()
        route, consent = self.leg.route, self.consent
        current_quote(route.quote, now)
        if (
            consent.action_id != self.leg.action_id
            or consent.payload_digest != self.leg.digest
            or not route.prepared_at <= consent.confirmed_at <= now < consent.expires_at
            or consent.expires_at > route.quote.expires_at
        ):
            raise LiveExecutionError("INVALID_OR_STALE_EXPLICIT_CONFIRMATION")
        if self.leg.envelope is None:
            raise LiveExecutionError("EXACT_TRANSACTION_ENVELOPE_REQUIRED")
        self.leg.envelope.matches(route, tx, nonce=nonce)
        self.journal.require_consumed_consent(consent, payload_digest=self.leg.digest, now=now)

    @property
    def payload_digest(self):
        return fingerprint(self.leg.envelope)
