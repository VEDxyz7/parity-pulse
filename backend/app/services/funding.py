"""USD notional → verified funding asset units. No wallet integration or conversion trade."""

from decimal import ROUND_CEILING, localcontext
from types import SimpleNamespace

from app.models.execution import FundingAsset, FundingCheck, FundingState, address, units


class FundingService:
    def resolve(self, market, *, symbol="USDT", contract=None, mode, now):
        # Exact symbol/chain matching and optional verified contract pin. Never choose first match.
        rows = market.search("56", contract or symbol)
        matches = [
            r
            for r in rows
            if r.binanceChainId == "56"
            and r.tokenSymbol == symbol
            and (contract is None or address(r.tokenContractAddress) == address(contract))
        ]
        if len(matches) != 1:
            raise ValueError("Funding identity unavailable/ambiguous")
        row = matches[0]
        meta = market.basic_info(SimpleNamespace(chain_id="56", contract=row.tokenContractAddress))
        if meta.tokenSymbol != symbol or address(meta.tokenContractAddress) != address(
            row.tokenContractAddress
        ):
            raise ValueError("Funding metadata mismatch")
        return FundingAsset(
            chain_id="56",
            contract=meta.tokenContractAddress,
            symbol=symbol,
            decimals=meta.decimals,
            data_mode=mode,
            observed_at=now,
            source="BINANCE_MARKET",
        )

    def check(self, notional, state, *, wallet, mode, now):
        from app.models.data import financial

        notional = financial(notional)
        if notional <= 0:
            raise ValueError("Positive USD notional required")
        if state is None:
            return FundingCheck(
                status="FAIL",
                reasons=("MISSING_WALLET_STATE",),
                state=None,
                usd_notional=notional,
                required_base_units=None,
                conversion_cost_usd=None,
                evaluated_at=now,
            )
        state = FundingState.model_validate_json(state.model_dump_json())
        reasons = []
        if (
            state.asset.data_mode != mode
            or state.wallet != address(wallet)
            or not state.identity_verified
        ):
            reasons.append("FUNDING_IDENTITY_INVALID")
        if not all(
            0 <= (now - t).total_seconds() <= 120
            for t in (
                state.asset.observed_at,
                state.price_observed_at,
                state.balance_observed_at,
                state.conversion_cost_observed_at,
                state.native_price_observed_at,
            )
        ):
            reasons.append("FUNDING_STATE_STALE")
        if state.conversion_required and not state.conversion_verified:
            reasons.append("FUNDING_CONVERSION_UNVERIFIED")
        with localcontext() as ctx:
            ctx.prec = 256
            required = int(
                (notional / state.unit_price_usd * 10**state.asset.decimals).to_integral_value(
                    rounding=ROUND_CEILING
                )
            )
        required_units = units(str(required))
        if int(state.balance_base_units) < required:
            reasons.append("INSUFFICIENT_FUNDING_BALANCE")
        if (
            int(state.native_gas_balance_wei) < int(state.gas_reserve_wei)
            or int(state.gas_reserve_wei) == 0
        ):
            reasons.append("INSUFFICIENT_OR_UNVERIFIED_NATIVE_GAS")
        return FundingCheck(
            status="FAIL" if reasons else "PASS",
            reasons=tuple(reasons),
            state=state,
            usd_notional=notional,
            required_base_units=required_units,
            conversion_cost_usd=state.conversion_cost_usd,
            evaluated_at=now,
        )

    def check_gas(self, state, transactions, *, costs_usd, now):
        """Exact maximum native gas requirement; reserve is additional untouched native balance."""
        if (
            state is None
            or not transactions
            or not 0 <= (now - state.native_price_observed_at).total_seconds() <= 120
        ):
            raise ValueError("NATIVE_GAS_PRICE_UNAVAILABLE_OR_STALE")
        with localcontext() as ctx:
            ctx.prec = 256
            gas = sum(int(tx.gas) * int(tx.gasPrice) for tx in transactions)
            usd = gas * state.native_unit_price_usd / 10**18
        if gas + int(state.gas_reserve_wei) > int(state.native_gas_balance_wei):
            raise ValueError("INSUFFICIENT_NATIVE_GAS_AND_RESERVE")
        if usd > costs_usd:
            raise ValueError("NATIVE_GAS_EXCEEDS_RISK_COST_RESERVE")
        return gas, usd
