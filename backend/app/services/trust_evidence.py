"""Independent references, scheduled regimes, verified units and bounded news alignment."""

import re
from datetime import timedelta
from decimal import Decimal

from pydantic import ValidationError

from app.models.data import utc
from app.models.trust import LiquidityEvidence, NewsEvidence, ReferenceEvidence, RegimeEvidence
from app.services.normalization import bounded_decimal, positive


def seconds(delta):
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1000000


class MarketRegimeService:
    def __init__(self, calendar):
        self.calendar = calendar

    def evaluate(self, at):
        at = utc(at)
        status = self.calendar.status(at)
        previous_open, previous_close = self.calendar.previous_session(at)
        bucket = status.state
        if status.multi_day_closure and status.state != "REGULAR":
            bucket = "MULTI_DAY_REOPEN"
        elif status.state in {"WEEKEND", "HOLIDAY"}:
            bucket = "WEEKEND_PREOPEN"
        # Preserve exact pre/post/overnight boundaries; reopening is an explicit flag.
        return RegimeEvidence(
            state=status.state,
            baseline_bucket=bucket,
            evaluated_at=at,
            previous_regular_open=previous_open,
            previous_regular_close=previous_close,
            next_open=status.next_open,
            early_close=status.early_close,
            reopening=status.reopening,
            multi_day_closure=status.multi_day_closure,
            schedule_version=status.provider_identifier,
        )


class IndependentReferenceService:
    def evaluate(self, token, price, reference, regime, at, mode):
        reasons = []
        token_age = None
        equity_age = None
        skew = None
        asof = None
        if price is None or price.token_price is None:
            reasons.append("TOKEN_PRICE_UNAVAILABLE")
        elif price.source_timestamp is None:
            reasons.append("TOKEN_TIMESTAMP_UNAVAILABLE")
        else:
            age = seconds(at - price.source_timestamp)
            token_age = max(age, Decimal(0))
            if not 0 <= age <= 120:
                reasons.append("TOKEN_STALE_OR_FUTURE")
        if price is not None:
            if (
                price.data_mode != mode
                or token.data_mode != mode
                or (
                    token.ticker,
                    token.platform_id,
                    token.chain_id,
                    token.contract,
                    token.token_symbol,
                    token.token_to_share_ratio,
                )
                != (
                    price.ticker,
                    price.issuer,
                    price.chain_id,
                    price.contract,
                    price.token_symbol,
                    price.token_to_share_ratio,
                )
            ):
                reasons.append("TOKEN_IDENTITY_OR_MODE_CONFLICT")
            if price.kind not in {"PRICE", "PRICE_INFO"}:
                reasons.append("TOKEN_PRICE_UNITS_UNVERIFIED")
            if price.data_quality != ("DEMO" if mode == "DEMO" else "LIVE"):
                reasons.append("TOKEN_QUALITY_UNVERIFIED")
            if price.ingestion_timestamp > at:
                reasons.append("TOKEN_NOT_YET_AVAILABLE")
        if token.source not in ({"DEMO_DATA"} if mode == "DEMO" else {"BINANCE_RWA"}):
            reasons.append("RATIO_SOURCE_NOT_VERIFIED")
        if token.asset_type != 1:
            reasons.append("NOT_STOCK")
        if not 0 <= seconds(at - token.ingestion_timestamp) <= 120:
            reasons.append("RATIO_METADATA_STALE_OR_FUTURE")
        if token.source_timestamp is not None and token.source_timestamp > at:
            reasons.append("RATIO_SOURCE_IN_FUTURE")
        if mode == "LIVE" and (token.chain_id == "DEMO" or token.contract.startswith("demo:")):
            reasons.append("DEMO_IDENTITY_IN_LIVE")
        if reference is None or reference.price is None or reference.source_timestamp is None:
            reasons.append("INDEPENDENT_REFERENCE_UNAVAILABLE")
        else:
            asof = reference.source_timestamp
            if reference.ticker != token.ticker or reference.data_mode != mode:
                reasons.append("REFERENCE_IDENTITY_OR_MODE_CONFLICT")
            if reference.source not in ({"DEMO_EQUITY"} if mode == "DEMO" else {"MASSIVE"}):
                reasons.append("REFERENCE_SOURCE_NOT_INDEPENDENT_VERIFIED")
            if reference.ingestion_timestamp > at:
                reasons.append("REFERENCE_NOT_YET_AVAILABLE")
            if regime.state == "REGULAR":
                equity_age = max(seconds(at - asof), Decimal(0))
                if reference.kind not in {"QUOTE", "SNAPSHOT"}:
                    reasons.append("CURRENT_REFERENCE_REQUIRED")
                if reference.data_quality != ("DEMO" if mode == "DEMO" else "LIVE"):
                    reasons.append("CURRENT_REFERENCE_NOT_VERIFIED")
                if not 0 <= seconds(at - asof) <= 120:
                    reasons.append("REFERENCE_STALE_OR_FUTURE")
                if price is not None and price.source_timestamp is not None:
                    skew = abs(seconds(price.source_timestamp - asof))
                    if skew > 30:
                        reasons.append("TIMESTAMP_SKEW_EXCEEDED")
            else:
                # Bar timestamp is its START, so the last completed minute ends at close.
                if (
                    reference.kind != "REGULAR_CLOSE"
                    or reference.interval != "1minute"
                    or asof + timedelta(minutes=1) != regime.previous_regular_close
                    or reference.data_quality != ("DEMO" if mode == "DEMO" else "HISTORICAL")
                ):
                    reasons.append("ACTUAL_PREVIOUS_REGULAR_CLOSE_REQUIRED")
                else:
                    asof = regime.previous_regular_close
                equity_age = max(seconds(at - asof), Decimal(0))
                if price is not None and price.source_timestamp is not None:
                    skew = abs(seconds(price.source_timestamp - asof))
                # Closed-session skew is the closure age, not current-quote alignment.
        try:
            positive(token.token_to_share_ratio)
            if price is not None and price.token_price is not None:
                positive(price.token_price)
            if reference is not None and reference.price is not None:
                positive(reference.price)
        except ValueError:
            reasons.append("INVALID_FINANCIAL_INPUT")
        status = "AVAILABLE"
        if reasons:
            status = "STALE" if any("STALE" in r or "SKEW" in r for r in reasons) else "UNVERIFIED"
            if any("UNAVAILABLE" in r for r in reasons):
                status = "UNAVAILABLE"
            if any("CONFLICT" in r for r in reasons):
                status = "CONFLICTING"
        try:
            return ReferenceEvidence(
                status=status,
                observation=reference,
                reference_asof=asof,
                timestamp_skew_seconds=skew,
                token_age_seconds=token_age,
                reference_age_seconds=equity_age,
                reason_codes=reasons,
            )
        except ValueError:
            return ReferenceEvidence(
                status="CONFLICTING", reason_codes=[*reasons, "MALFORMED_REFERENCE_PROVENANCE"]
            )


class LiquidityEvidenceService:
    def evaluate(self, token, observation, at, mode):
        if observation is None:
            return LiquidityEvidence(status="UNAVAILABLE", reason_codes=["PRICE_INFO_UNAVAILABLE"])
        if observation.kind != "PRICE_INFO" or observation.volume_unit != "USD":
            return LiquidityEvidence(
                status="AMBIGUOUS", reason_codes=["LIQUIDITY_UNITS_UNVERIFIED"]
            )
        if (
            observation.data_mode != mode
            or observation.ticker != token.ticker
            or observation.issuer != token.platform_id
            or observation.chain_id != token.chain_id
            or observation.contract != token.contract
            or observation.token_to_share_ratio != token.token_to_share_ratio
            or observation.source != ("DEMO_MARKET" if mode == "DEMO" else "BINANCE_MARKET")
        ):
            return LiquidityEvidence(
                status="CONFLICTING", reason_codes=["LIQUIDITY_IDENTITY_CONFLICT"]
            )
        if (
            observation.source_timestamp is None
            or observation.ingestion_timestamp > at
            or not 0 <= seconds(at - observation.source_timestamp) <= 120
            or observation.data_quality != ("DEMO" if mode == "DEMO" else "LIVE")
        ):
            return LiquidityEvidence(status="STALE", reason_codes=["LIQUIDITY_NOT_FRESH_VERIFIED"])
        fields = {
            "liquidity_usd": "liquidity",
            "buy_volume_24h_usd": "buyVolume24H",
            "sell_volume_24h_usd": "sellVolume24H",
            "buy_transactions_24h": "buyTxs24H",
            "sell_transactions_24h": "sellTxs24H",
        }
        try:
            values = {k: observation.provider_metadata.get(v) for k, v in fields.items()}
            result = LiquidityEvidence(
                status="AVAILABLE",
                source=observation.source,
                observed_at=observation.source_timestamp,
                volume_24h_usd=observation.volume,
                trade_count_24h=observation.trade_count,
                **values,
            )
            for value in [
                result.volume_24h_usd,
                result.liquidity_usd,
                result.buy_volume_24h_usd,
                result.sell_volume_24h_usd,
            ]:
                bounded_decimal(value)
            if result.volume_24h_usd is None or result.liquidity_usd is None:
                return result.model_copy(
                    update={
                        "status": "UNAVAILABLE",
                        "reason_codes": ["VOLUME_OR_LIQUIDITY_UNAVAILABLE"],
                    }
                )
            return result
        except (ValueError, ValidationError):
            return LiquidityEvidence(status="CONFLICTING", reason_codes=["MALFORMED_LIQUIDITY"])


class NewsAlignmentService:
    """Conservative headline evidence; never reads provider LLM insights or guesses causality."""

    positive = re.compile(r"\b(?:raises guidance|raises outlook|beats estimates)\b", re.I)
    negative = re.compile(r"\b(?:cuts guidance|cuts outlook|misses estimates)\b", re.I)

    def evaluate(
        self,
        articles,
        *,
        ticker,
        company,
        deviation,
        at,
        mode,
        complete,
        unavailable=False,
        move_start=None,
        prefix_start=None,
    ):
        start = (move_start or at) - timedelta(hours=1)
        invalid_source = any(
            a.data_mode != mode
            or a.source != ("DEMO_NEWS" if mode == "DEMO" else "MASSIVE_NEWS")
            or a.data_quality != ("DEMO" if mode == "DEMO" else "HISTORICAL")
            for a in articles
            if a.published_timestamp <= at and a.ingestion_timestamp <= at
        )
        full_history_complete = complete
        prefix_covers_window = (
            not unavailable
            and prefix_start is not None
            and bool(articles)
            and prefix_start == articles[-1].published_timestamp
            and prefix_start < start
            and all(
                a.data_mode == mode
                and a.source == ("DEMO_NEWS" if mode == "DEMO" else "MASSIVE_NEWS")
                and a.data_quality == ("DEMO" if mode == "DEMO" else "HISTORICAL")
                and a.ticker == ticker
                and a.published_timestamp <= at
                and a.ingestion_timestamp <= at
                for a in articles
            )
            and all(
                a.published_timestamp >= b.published_timestamp
                for a, b in zip(articles, articles[1:], strict=False)
            )
        )
        complete = (complete or prefix_covers_window) and not invalid_source
        eligible = [
            a
            for a in articles
            if a.data_mode == mode
            and a.source == ("DEMO_NEWS" if mode == "DEMO" else "MASSIVE_NEWS")
            and a.data_quality == ("DEMO" if mode == "DEMO" else "HISTORICAL")
            and a.ticker == ticker
            and start <= a.published_timestamp <= at
            and a.ingestion_timestamp <= at
        ]
        eligible.sort(key=lambda a: (a.published_timestamp, a.provider_identifier))
        directional = []
        corroborating = False
        conflicting = False
        for article in eligible:
            headline = article.headline
            identified = re.search(r"\b" + re.escape(ticker) + r"\b", headline) is not None or (
                bool(company.strip()) and company.casefold() in headline.casefold()
            )
            if not identified or re.search(
                r"\b(?:not|no|never|may|might|could|rumor|rumour|expected|expects|will|plans)\b",
                headline,
                re.I,
            ):
                continue
            positive = bool(self.positive.search(headline))
            negative = bool(self.negative.search(headline))
            if positive == negative:
                if positive:
                    conflicting = True
                continue
            directional.append(article.provider_identifier)
            sign = Decimal(1) if positive else Decimal(-1)
            if deviation != 0:
                corroborating |= deviation * sign > 0
                conflicting |= deviation * sign < 0
        direction = (
            "CONFLICTING" if conflicting else "CORROBORATING" if corroborating else "UNKNOWN"
        )
        coverage = (
            "UNAVAILABLE"
            if unavailable
            else ("COMPLETE_REQUESTED_WINDOW" if complete else "PARTIAL")
        )
        state = (
            "UNAVAILABLE"
            if unavailable
            else "PARTIAL"
            if not complete
            else (
                direction
                if direction != "UNKNOWN"
                else "RELEVANT_NEWS"
                if eligible
                else "NO_RELEVANT_NEWS"
            )
        )
        reasons = ["HEADLINE_RULES_ARE_HEURISTIC_NOT_CAUSAL", "NEWS_NOT_EXHAUSTIVE_MARKET_COVERAGE"]
        if not full_history_complete:
            reasons.append("BOUNDED_NEWS_HISTORY")
        if prefix_covers_window and not full_history_complete:
            reasons.append("DESCENDING_PREFIX_COVERS_REQUESTED_WINDOW")
        if mode == "LIVE":
            reasons.append("SOURCE_UPDATED_HOURLY_NOT_REALTIME_NEWS")
        if not eligible:
            reasons.append("NO_NEWS_IS_NOT_PROOF_OF_NO_INFORMATION")
        return NewsEvidence(
            state=state,
            directional_state=direction,
            coverage=coverage,
            window_start=start,
            window_end=at,
            article_ids=[a.provider_identifier for a in eligible],
            published_timestamps=[a.published_timestamp for a in eligible],
            first_seen_timestamps=[a.ingestion_timestamp for a in eligible],
            directional_article_ids=directional,
            reason_codes=reasons,
        )
