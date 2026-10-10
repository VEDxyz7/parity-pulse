"""One server-owned authority for live capability gates; no environment override.

Passing software tests is not deployed safety/equivalence evidence. Until the gate
acceptance artifacts are independently approved, production policy denies every write.
Dependency injection permits deterministic offline tests, never HTTP supplied gate states.
"""

from app.models.execution import ExecutionControls


class LiveExecutionError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class LiveGatePolicy:
    def __init__(self):
        self._controls = ExecutionControls(data_mode="LIVE_READ_ONLY")

    def statuses(self):
        return {
            "DATA_GATE": "PASS",
            "DRY_RUN_GATE": "PASS",
            "TRUST_GATE": "BLOCKED",
            "OPPORTUNITY_GATE": "BLOCKED_BY_TRUST",
            "SWAP_LIVE_GATE": self._controls.swap_live_gate,
            "RFQ_LIVE_GATE": self._controls.rfq_live_gate,
            "AGENTIC_WALLET_LIVE_GATE": self._controls.agentic_wallet_live_gate,
        }

    def require(self, route, *, wallet=False):
        if route not in {"SWAP", "RFQ"}:
            raise LiveExecutionError("UNSUPPORTED_EXECUTION_MODE")
        statuses = self.statuses()
        gate = f"{route}_LIVE_GATE"
        if statuses[gate] != "PASS":
            raise LiveExecutionError(gate + "_BLOCKED")
        if wallet and statuses["AGENTIC_WALLET_LIVE_GATE"] != "PASS":
            raise LiveExecutionError("AGENTIC_WALLET_LIVE_GATE_BLOCKED")


LIVE_GATES = LiveGatePolicy()
