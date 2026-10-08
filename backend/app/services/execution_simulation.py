"""Provider simulation bound to the exact prepared fingerprint; RFQ settlement fails closed."""

from app.clients.common import ProviderError
from app.models.execution import (
    ExecutionSimulation,
    PreparedApproval,
    PreparedRoute,
    SimulationResponse,
    fingerprint,
)
from app.services.execution_builders import current_quote


def allowance_envelope_valid(artifact, response):
    """No implicit unlimited approval. Swap may only consume the bound allowance."""
    changes = response.allowanceChanges
    if isinstance(artifact, PreparedApproval):
        if len(changes) != 1:
            return False
        c = changes[0]
        return (
            (c.tokenAddress, c.owner, c.spender)
            == (artifact.token, artifact.transaction.sender, artifact.spender)
            and c.preAmount == artifact.pre_allowance_amount
            and c.postAmount == artifact.amount
            and int(c.preAmount) < int(c.postAmount) < 2**256 - 1
        )
    if not changes:
        return True
    if len(changes) != 1 or artifact.allowance is None:
        return False
    c, a = changes[0], artifact.allowance
    return (
        (c.tokenAddress, c.owner, c.spender) == (a.token, a.owner, a.spender)
        and c.preAmount == a.amount
        and max(0, int(a.amount) - int(artifact.quote.request.amount))
        <= int(c.postAmount)
        <= int(c.preAmount)
    )


class ExecutionSimulationService:
    def __init__(self, provider):
        self.provider = provider

    def simulate(self, artifact, *, now, mode=None):
        if isinstance(artifact, PreparedRoute):
            route = PreparedRoute.model_validate_json(artifact.model_dump_json())
            mode = route.quote.data_mode
            current_quote(route.quote, now)
            if route.quote.route.executionMode == "RFQ":
                return ExecutionSimulation(
                    fingerprint=route.fingerprint,
                    payload_digest=fingerprint(route.build.rfq),
                    data_mode=mode,
                    source=route.quote.source,
                    evaluated_at=now,
                    status="UNAVAILABLE",
                    response=None,
                    reason_codes=("RFQ_FINAL_SETTLEMENT_NOT_SIMULATABLE",),
                    coverage="RFQ_SETTLEMENT_UNAVAILABLE",
                )
            tx = route.build.tx
            source = route.quote.source
        else:
            artifact = PreparedApproval.model_validate_json(artifact.model_dump_json())
            tx = artifact.transaction
            source = "TEST_FIXTURE" if mode == "DEMO" else "BINANCE_WEB3"
            if mode not in ("DEMO", "LIVE_READ_ONLY"):
                raise ValueError("Approval simulation mode is mandatory")
        payload_digest = fingerprint({"binanceChainId": "56", "evmTx": tx.evm_payload()})
        fixture_provider = getattr(self.provider, "fixture_only", False) is True
        if fixture_provider != (source == "TEST_FIXTURE"):
            raise ValueError("SIMULATION_PROVIDER_MODE_MISMATCH")
        try:
            response, received = self.provider.simulate(tx, mode=mode)
            response = SimulationResponse.model_validate_json(response.model_dump_json())
            if not 0 <= (received - now).total_seconds() <= 30:
                raise ValueError("Invalid simulation receipt")
            safe_allowance = allowance_envelope_valid(artifact, response)
            status = "PASS" if response.status == "SUCCESS" and safe_allowance else "FAIL"
            reasons = (
                ()
                if status == "PASS"
                else (
                    "ALLOWANCE_SAFETY_ENVELOPE_VIOLATED"
                    if not safe_allowance
                    else "PROVIDER_SIMULATION_FAILED",
                )
            )
        except ProviderError:
            response, received, status, reasons = (
                None,
                now,
                "UNAVAILABLE",
                ("SIMULATION_UNAVAILABLE_OR_INVALID",),
            )
        except (ValueError, TypeError, AttributeError):
            response, received, status, reasons = (
                None,
                now,
                "FAIL",
                ("SIMULATION_SCHEMA_OR_ALLOWANCE_INVALID",),
            )
        return ExecutionSimulation(
            fingerprint=artifact.fingerprint,
            payload_digest=payload_digest,
            data_mode=mode,
            source=source,
            evaluated_at=received,
            status=status,
            response=response,
            reason_codes=reasons,
            coverage="EVM_FROM_TO_VALUE_DATA_ONLY",
        )

    @staticmethod
    def matches(simulation, artifact, *, now, mode):
        simulation = ExecutionSimulation.model_validate_json(simulation.model_dump_json())
        if isinstance(artifact, PreparedRoute):
            artifact = PreparedRoute.model_validate_json(artifact.model_dump_json())
            current_quote(artifact.quote, now)
            tx = artifact.build.tx
        else:
            artifact = PreparedApproval.model_validate_json(artifact.model_dump_json())
            tx = artifact.transaction
        return (
            tx is not None
            and simulation.status == "PASS"
            and simulation.response is not None
            and simulation.response.status == "SUCCESS"
            and not simulation.response.failReason
            and allowance_envelope_valid(artifact, simulation.response)
            and simulation.fingerprint == artifact.fingerprint
            and simulation.data_mode == mode
            and (
                not isinstance(artifact, PreparedRoute)
                or simulation.source == artifact.quote.source
            )
            and 0 <= (now - simulation.evaluated_at).total_seconds() <= 120
            and simulation.payload_digest
            == fingerprint({"binanceChainId": "56", "evmTx": tx.evm_payload()})
        )
