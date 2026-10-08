"""Transport-independent adapter. No execution gateway is granted to a tool handler."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.clients.common import ProviderError
from app.models.agent_api import (
    INPUTS,
    PROPOSALS,
    PublicScan,
    ToolError,
    ToolResult,
    project_portfolio,
)
from app.models.opportunity_scan import OpportunityRequest
from app.models.portfolio import portfolio_fingerprint
from app.models.scorecard import AuditEvent
from app.models.terminal import TerminalQuery
from app.services.audit import safe_record


def output_schema():
    schema = ToolResult.model_json_schema(mode="serialization")

    # Existing Decimal serializers can emit exponents. Match their actual JSON lexemes.
    def visit(value):
        if isinstance(value, dict):
            if value.get("pattern") == r"^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$":
                value["pattern"] = r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema


def inventory():
    return {
        "schema_version": "agent-api-1",
        "transport": "HTTP_JSON_AND_MCP_STDIO",
        "authority": "EXISTING_BACKEND_SERVICES",
        "execution_ready": False,
        "tools": [
            {
                "name": name,
                "description": (
                    "Non-executable decision/proposal through the existing backend."
                    if name in PROPOSALS
                    else "Analytical inspection through the existing backend."
                ),
                "inputSchema": model.model_json_schema(),
                "outputSchema": output_schema(),
                "annotations": {
                    "readOnlyHint": name not in PROPOSALS,
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": True,
                },
            }
            for name, model in INPUTS.items()
        ],
    }


class AgentAPI:
    def __init__(self, state, receipts, *, clock=lambda: datetime.now(UTC)):
        self.state, self.receipts, self.clock = state, receipts, clock
        self.mode = state.settings.data_mode
        self.secrets = state.settings.redaction_values()

    def result(self, name, ids, **values):
        now = self.clock()
        return ToolResult(
            tool=name,
            **ids,
            origin_request_id=ids["request_id"],
            origin_correlation_id=ids["correlation_id"],
            generated_at=now,
            as_of=now,
            data_mode=self.mode,
            data_quality="DEMO" if self.mode == "DEMO" else "UNKNOWN",
            source="EXISTING_BACKEND_SERVICES",
            status="UNAVAILABLE",
            **values,
        )

    def error(self, name, ids, code, category, *, reasons=()):
        return self.result(
            name,
            ids,
            error=ToolError(
                code=code,
                category=category,
                retry_policy="CORRECT_INPUT"
                if category == "CALLER"
                else ("DO_NOT_RESUBMIT_WITH_NEW_KEY" if name in PROPOSALS else "READ_ONLY_RETRY"),
            ),
            reason_codes=tuple(dict.fromkeys((code, *reasons))),
        )

    def audit(self, result, inputs=None, *, phase="COMPLETED"):
        # Actual bounded invocation events, distinct from Phase 13's source projections.
        now = self.clock()
        event = AuditEvent(
            event_id="pending",
            data_mode=self.mode,
            decision_id=result.decision_id or str(result.invocation_id),
            correlation_id=str(result.correlation_id),
            run_id=result.run_id,
            ticker=getattr(inputs, "ticker", None),
            timestamp=now,
            recorded_at=now,
            event_type="TOOL_INVOCATION",
            actor="DETERMINISTIC_BACKEND",
            source="AGENT_API",
            source_digest=portfolio_fingerprint(result),
            capture_kind="OBSERVED_TOOL_INVOCATION",
            status=phase,
            input_summary={
                "tool": result.tool,
                "request_id": str(result.request_id),
                "invocation_id": str(result.invocation_id),
                "input_digest": portfolio_fingerprint(inputs) if inputs is not None else None,
                "ticker": getattr(inputs, "ticker", None),
                "mode": getattr(inputs, "mode", None),
                "amount_usd": str(inputs.amount_usd) if hasattr(inputs, "amount_usd") else None,
                "risk_budget_usd": str(inputs.risk_budget_usd)
                if hasattr(inputs, "risk_budget_usd")
                else None,
            },
            output_summary={
                "status": result.status,
                "error_code": result.error.code if result.error else None,
                "replayed": result.replayed,
                "broadcast": False,
            },
            reasons=result.reason_codes,
        )
        event = event.model_copy(
            update={
                "event_id": portfolio_fingerprint(
                    event.model_dump(exclude={"event_id", "recorded_at"})
                )
            }
        )
        self.state.scorecard.audit.append((), (event,))

    async def call(self, name, arguments, *, request_id, correlation_id, run_id):
        ids = dict(
            request_id=UUID(str(request_id)),
            correlation_id=UUID(str(correlation_id)),
            run_id=run_id,
            invocation_id=uuid4(),
        )
        inputs, key, digest = None, None, None
        try:
            inputs = INPUTS[name].model_validate(arguments)
            safe_record(inputs, self.secrets)
            if inputs.data_mode is not None and inputs.data_mode != self.mode:
                raise ValueError("Mode mismatch")
            if (
                getattr(inputs, "demo_scenario", None)
                and self.state.settings.runtime_mode != "DEMO"
            ):
                raise ValueError("Sandbox unavailable")
        except (ValidationError, ValueError, TypeError):
            result = self.error(name, ids, "INVALID_INPUT", "CALLER")
            self.audit(result)
            return result
        if name in PROPOSALS:
            key = f"{self.mode}:{name}:{inputs.idempotency_key}"
            digest = portfolio_fingerprint(inputs)
            try:
                previous = self.receipts.claim(key, digest)
                if previous:
                    # Preserve original evidence IDs; correlate this delivery separately.
                    result = previous.model_copy(update={"replayed": True, **ids})
                    safe_record(result, self.secrets)
                    self.audit(result, inputs, phase="REPLAYED")
                    return result
            except LookupError:
                result = self.error(name, ids, "RECONCILIATION_REQUIRED", "SAFETY")
                self.audit(result, inputs)
                return result
            except ValueError:
                result = self.error(name, ids, "IDEMPOTENCY_CONFLICT", "SAFETY")
                self.audit(result, inputs)
                return result
        self.audit(self.result(name, ids), inputs, phase="STARTED")
        try:
            if getattr(inputs, "mode", None) == "LIVE":
                result = self.error(name, ids, "EXECUTION_BLOCKED", "EXECUTION_CAPABILITY")
            else:
                values = await self.dispatch(name, inputs, ids)
                result = self.result(name, ids).model_copy(update=values)
                result = ToolResult.model_validate_json(result.model_dump_json())
                safe_record(result, self.secrets)
                if result.decision_id and name in PROPOSALS:
                    await asyncio.to_thread(self.state.scorecard.capture)
        except ProviderError:
            result = self.error(name, ids, "DATA_UNAVAILABLE", "DATA_PROVIDER")
        except (ValueError, TypeError, LookupError, ArithmeticError, OSError):
            result = self.error(name, ids, "DATA_UNAVAILABLE", "DATA_PROVIDER")
        except Exception:
            # Never return provider exceptions, validation payloads or tracebacks to clients.
            result = self.error(name, ids, "DATA_UNAVAILABLE", "DATA_PROVIDER")
        safe_record(result, self.secrets)
        self.audit(result, inputs)
        if key:
            self.receipts.finish(key, digest, result)
        return result

    async def dispatch(self, name, body, ids):
        s = self.state
        context = {k: str(ids[k]) for k in ("request_id", "correlation_id", "run_id")}
        if name in {"get_portfolio", "get_autopilot_status"}:
            raw = await asyncio.to_thread(s.portfolio.state)
            state = project_portfolio(raw)
            return dict(
                status="AVAILABLE",
                portfolio=state,
                source="DETERMINISTIC_PORTFOLIO_SERVICE",
                as_of=state.latest_decision.updated_at if state.latest_decision else self.clock(),
            )
        if name == "compare_stock_tokens":
            page = await asyncio.to_thread(
                s.terminal.issuers,
                TerminalQuery(ticker=body.ticker, limit=body.limit, offset=body.offset),
                self.clock(),
            )
            return dict(
                status="AVAILABLE" if page.items else "UNAVAILABLE",
                comparison=page,
                source="EXISTING_NORMALIZATION_AND_TERMINAL",
                reason_codes=page.reasons,
            )
        if name == "get_stock_trust":
            trust = await asyncio.to_thread(s.trust.assess, body.ticker, **context)
            return dict(
                status="AVAILABLE" if trust.status == "ASSESSED" else "UNAVAILABLE",
                trust=trust,
                as_of=trust.evaluated_at,
                source="DETERMINISTIC_TRUST_SERVICE",
                reason_codes=tuple(
                    dict.fromkeys(
                        code for row in trust.representations for code in row.reason_codes
                    )
                ),
            )
        if name in {"get_route", "buy_stock_exposure"}:
            # Use the UI's exact discovery/normalization/router authority. No financial math here.
            trust = None
            if name == "buy_stock_exposure":
                trust = await asyncio.to_thread(s.trust.assess, body.ticker, **context)
            proposal = await asyncio.to_thread(
                s.exposure.propose,
                f"Buy ${format(body.amount_usd, 'f')} of {body.ticker}",
                **context,
                persist=name == "buy_stock_exposure",
            )
            values = dict(
                status="PROPOSAL" if proposal.status == "DRY_RUN" else "REJECTED",
                route=proposal.route_decision,
                source="EXISTING_EXPOSURE_AND_SHARED_ROUTER",
                as_of=proposal.created_at,
                simulation_status="UNAVAILABLE",
                reason_codes=tuple(proposal.execution_blockers),
                data_quality=proposal.selected.price_quality if proposal.selected else "MISSING",
            )
            if name == "buy_stock_exposure":
                # Phase 1 indicative estimates are not Risk-approved executable BUY decisions.
                values.update(
                    proposal=proposal,
                    trust=trust,
                    decision_id=str(proposal.proposal_id),
                    requested_risk_budget_usd=body.risk_budget_usd,
                    status="DEFERRED" if proposal.status == "DRY_RUN" else "REJECTED",
                    reason_codes=tuple(
                        dict.fromkeys(
                            (
                                *proposal.execution_blockers,
                                "RISK_INPUTS_UNAVAILABLE",
                                "EXECUTION_BLOCKED",
                            )
                        )
                    ),
                )
            elif proposal.status != "DRY_RUN":
                values["status"] = "UNAVAILABLE"
            return values
        if name == "find_opportunity":
            if s.opportunity_scan_lock.locked():
                return dict(status="BLOCKED", reason_codes=("SCAN_IN_PROGRESS",))
            request = OpportunityRequest(
                budget_usd=body.budget_usd,
                risk_budget_usd=body.risk_budget_usd,
                time_window=body.time_window,
                universe=body.universe,
                demo_scenario=body.demo_scenario,
                correlation_id=str(ids["correlation_id"]),
            )
            async with s.opportunity_scan_lock:
                snapshot = await asyncio.to_thread(
                    s.opportunity_source.capture, request, s.opportunity_scan.policy
                )
                scan = await s.opportunity_scan.scan(request, snapshot)
            fields = set(PublicScan.model_fields) - {"agent_decision", "llm_calls"}
            public = PublicScan(
                **{k: getattr(scan, k) for k in fields},
                agent_decision=scan.agent_run.decision if scan.agent_run else None,
                llm_calls=scan.agent_run.llm_calls if scan.agent_run else 0,
            )
            return dict(
                opportunity=public,
                decision_id=scan.decision_id,
                as_of=scan.timestamp,
                source="EXISTING_OPPORTUNITY_SCAN_SERVICE",
                simulation_status="UNAVAILABLE",
                status="PROPOSAL"
                if scan.final_action == "BUY"
                else "DEFERRED"
                if scan.final_action == "DEFER"
                else "REJECTED",
                reason_codes=scan.blockers,
            )
        raise ValueError("Tool not allowlisted")
