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
            status = "PASS" if response.status == "SUCCESS" else "FAIL"
            reasons = () if status == "PASS" else ("PROVIDER_SIMULATION_FAILED",)
        except (ProviderError, ValueError, TypeError):
            response, received, status, reasons = (
                None,
                now,
                "UNAVAILABLE",
                ("SIMULATION_UNAVAILABLE_OR_INVALID",),
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
