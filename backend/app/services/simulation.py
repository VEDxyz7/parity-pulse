"""Pure local DEMO constraint evaluation, not an EVM, Binance or wallet simulation."""

from decimal import Decimal, localcontext
from fractions import Fraction

from app.models.demo_execution import DemoSimulation, artifact_digest, artifact_id, digest
from app.models.risk import RiskCheck
from app.services.demo_sandbox import MARKER
from app.services.opportunity import rounded


class SimulationService:
    def simulate(self, transaction, quote, risk, token, *, context_sha256, now):
        checks = []

        def check(code, passed, detail):
            checks.append(RiskCheck(code=code, passed=bool(passed), detail=detail))

        p = transaction.parameters
        check(
            "QUOTE_VALID",
            quote.quoted_at <= now < quote.valid_until,
            "The DEMO quote must be unexpired and not from the future.",
        )
        check(
            "REQUEST_VALID",
            transaction.prepared_at <= now < transaction.valid_until
            and transaction.valid_until == quote.valid_until,
            "Prepared request validity must remain bound to its quote.",
        )
        check(
            "CURRENT_INPUTS_UNCHANGED",
            context_sha256 == quote.context_sha256 == transaction.context_sha256,
            "Any market/economic/mandate/policy change requires a fresh quote and preparation.",
        )
        check(
            "QUOTE_FINGERPRINT",
            artifact_digest(quote, "quote_id") == quote.fingerprint
            and quote.quote_id == artifact_id("quote", quote.fingerprint),
            "Canonical quote content and ID must match their fingerprint.",
        )
        check(
            "TRANSACTION_FINGERPRINT",
            artifact_digest(transaction, "transaction_id") == transaction.fingerprint
            and transaction.transaction_id == artifact_id("request", transaction.fingerprint),
            "Canonical request content and ID must match their fingerprint.",
        )
        check(
            "QUOTE_BINDING",
            transaction.quote_id == p.quote_id == quote.quote_id
            and transaction.quote_fingerprint == quote.fingerprint
            and transaction.opportunity_id == quote.opportunity_id,
            "The exact quote and Opportunity must bind every prepared parameter.",
        )
        identity = (
            quote.ticker,
            quote.issuer,
            quote.chain_id,
            quote.contract,
            quote.symbol,
            quote.decimals,
        )
        check(
            "REPRESENTATION_VALID",
            identity
            == (p.ticker, p.issuer, p.chain_id, p.target_token, p.token_symbol, p.token_decimals)
            == (
                token.ticker,
                token.platform_id,
                token.chain_id,
                token.contract,
                token.token_symbol,
                token.decimals,
            )
            and token.open_state is True
            and token.market_state == "regular"
            and token.data_mode == "DEMO"
            and token.data_quality == "DEMO"
            and token.token_to_share_ratio == quote.token_to_share_ratio,
            "Only the same enabled synthetic representation, decimals and ratio are allowed.",
        )
        check(
            "RISK_REVALIDATION",
            risk.status == "PASS"
            and risk.approved_for_demo_analysis
            and risk.opportunity_id == quote.opportunity_id
            and risk.evaluated_at == now,
            "Current financial Risk must independently pass for the quoted Opportunity.",
        )
        with localcontext() as context:
            context.prec = 256
            check(
                "ALLOWED_SIZE",
                risk.status == "PASS"
                and p.base_notional_usd <= risk.maximum_allowed_notional_usd
                and p.quantity <= risk.proposed_token_quantity
                and p.quantity == quote.output_token_quantity,
                "Requested size must equal the quote and remain within revalidated Risk limits.",
            )
            check(
                "SLIPPAGE_LIMIT",
                p.maximum_slippage_bps == quote.slippage_bps
                and quote.slippage_bps == quote.economics_inputs.slippage_bps
                and quote.slippage_bps <= risk.policy.max_slippage_bps,
                "The quoted slippage assumption cannot change or exceed current tolerance.",
            )
            check(
                "LIQUIDITY_LIMIT",
                p.base_notional_usd <= risk.liquidity_notional_cap_usd,
                "Mark notional must remain inside the synthetic liquidity participation cap.",
            )
            check(
                "EXECUTION_PRICE",
                quote.execution_price_usd
                == quote.mark_price_usd * (1 + quote.slippage_bps / Decimal(10000)),
                "The synthetic BUY price must include the declared slippage exactly once.",
            )
            check(
                "AMOUNT_EQUIVALENCE",
                p.maximum_input_usd
                == quote.input_amount_usd
                == quote.output_token_quantity * quote.execution_price_usd
                and p.base_notional_usd
                == quote.base_notional_usd
                == quote.output_token_quantity * quote.mark_price_usd
                and p.minimum_output_tokens == p.quantity == quote.output_token_quantity,
                "Input, output, mark notional and minimum output must match the quote.",
            )
            check(
                "BASE_UNITS",
                p.token_base_units == str(int(Fraction(p.quantity) * 10**p.token_decimals)),
                "Smallest-unit amount must match the exact quantity and declared decimals.",
            )
            fixed = quote.fees_usd + quote.gas_usd + quote.execution_buffer_usd
            net = rounded(
                quote.output_token_quantity
                * quote.economics_inputs.target_share_price_usd
                * quote.token_to_share_ratio
                - quote.input_amount_usd
                - fixed
            )
            check(
                "QUOTED_NET_EDGE",
                quote.net_hypothetical_edge_usd == net
                and net
                >= max(risk.policy.min_net_edge_usd, quote.economics_inputs.minimum_net_edge_usd),
                "Recomputed cost-adjusted hypothetical edge must match and meet current minima.",
            )
            check(
                "EXPECTED_COSTS",
                (p.fees_usd, p.gas_usd, p.execution_buffer_usd)
                == (quote.fees_usd, quote.gas_usd, quote.execution_buffer_usd)
                == (
                    quote.economics_inputs.fees_usd,
                    quote.economics_inputs.gas_usd,
                    quote.economics_inputs.execution_buffer_usd,
                )
                and p.total_cash_required_usd
                == quote.total_cash_required_usd
                == quote.input_amount_usd + fixed
                and quote.estimated_slippage_usd
                == quote.input_amount_usd - quote.base_notional_usd,
                "Costs/reserve must bind the exact quote without double-charging slippage.",
            )
            check(
                "CASH_LIMITS",
                p.total_cash_required_usd
                <= min(risk.inputs.budget_usd, risk.inputs.wallet_available_usd),
                "Including costs/reserve, required cash must fit DEMO budget and wallet limits.",
            )
        check(
            "NO_EXECUTION",
            transaction.signed
            is transaction.transaction_broadcast
            is transaction.funds_moved
            is False
            and transaction.calldata is transaction.signature is None
            and not transaction.broadcastable,
            "This manifest has no signature, calldata, broadcast or moved funds.",
        )
        passed = all(c.passed for c in checks)
        fingerprint = digest(
            {
                "transaction": transaction.fingerprint,
                "quote": quote.fingerprint,
                "context": context_sha256,
                "now": now.isoformat(),
                "checks": [c.model_dump() for c in checks],
            }
        )
        return DemoSimulation(
            **MARKER,
            simulation_id=artifact_id("simulation", fingerprint),
            transaction_id=transaction.transaction_id,
            transaction_fingerprint=transaction.fingerprint,
            quote_id=quote.quote_id,
            quote_fingerprint=quote.fingerprint,
            evaluated_at=now,
            valid_until=quote.valid_until,
            status="SIMULATION_PASS" if passed else "SIMULATION_FAIL",
            reason_codes=["ALL_LOCAL_DEMO_CONSTRAINTS_PASSED"]
            if passed
            else [c.code for c in checks if not c.passed],
            checks=checks,
            risk_revalidation=risk,
        )
