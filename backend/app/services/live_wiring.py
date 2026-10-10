"""Host-only gated worker attachment. Startup never creates a signer/write transport.

The audited branch's perpetual-index equity source and trust-disable configuration are
intentionally excluded. Existing admitted data/Trust/portfolio services stay authoritative.
"""

from app.services.execution_gates import LIVE_GATES


class LiveRuntime:
    def __init__(self, journal):
        self.journal = journal
        self.executor = None
        self.prepared = {}  # host-owned immutable preparations; never loaded from HTTP

    def attach(self, portfolio, trading, rpc, signer, *, route, **limits):
        LIVE_GATES.require(route, wallet=signer.kind != "LOCAL_KEY")
        from app.services.live_execution import LiveRebalanceExecutor

        self.executor = LiveRebalanceExecutor(
            portfolio, trading, rpc, signer, self.journal, **limits
        )
        return self.executor

    def status(self):
        return {
            "gates": LIVE_GATES.statuses(),
            "live_execution": False,
            "execution_mode": "DRY_RUN",
            "approval_mode": "PROPOSE_ONLY",
            "require_simulation": True,
            "worker_attached": self.executor is not None,
        }

    def close(self):
        self.journal.close()
