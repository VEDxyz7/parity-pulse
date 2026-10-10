"""Compose existing read-only providers and deterministic Trust services; no trading gateway."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from uuid import uuid4

from pydantic import ValidationError

from app.clients.common import ProviderError
from app.models.trust import (
    AnalogueEvidence,
    BaselineEvidence,
    RepresentationTrust,
    TrustAssessment,
    TrustFeatures,
    TrustSample,
)
from app.repositories.trust import TrustRepository
from app.services.normalization import comparable_economics
from app.services.trust_classifier import TrustClassifier
from app.services.trust_evidence import (
    IndependentReferenceService,
    LiquidityEvidenceService,
    MarketRegimeService,
    NewsAlignmentService,
    seconds,
)
from app.services.trust_history import AnalogueService, BaselineService, EpisodeBuilder, digest

logger = logging.getLogger("parity.trust")


class TrustService:
    def __init__(self, layer, database, *, clock=None):
        self.layer = layer
        self.clock = clock or (lambda: datetime.now(UTC))
        self.repository = TrustRepository(database)
        self.regimes = MarketRegimeService(layer.calendar)
        self.references = IndependentReferenceService()
        self.liquidity = LiquidityEvidenceService()
        self.news = NewsAlignmentService()
        self.baselines = BaselineService()
        self.analogues = AnalogueService()
        self.episodes = EpisodeBuilder()
        self.classifier = TrustClassifier()

    def assess(self, ticker, *, run_id, request_id, correlation_id):
        mode = self.layer.mode
        limits = [
            "UNCALIBRATED_ENGINEERING_RULES",
            "NO_EXECUTION_AUTHORITY",
            "EARNINGS_CALENDAR_UNAVAILABLE",
            "TRADE_AND_CANDLE_UNITS_EXCLUDED",
            "TRUST_GATE_BLOCKED_PENDING_ACCOUNT_AND_HISTORY_EVIDENCE",
        ]
        representations = []
        regime = None
        resolved = None
        try:
            initial_regime = self.regimes.evaluate(self.clock())
            found = self.layer.discovery.resolve(ticker)
            if found["status"] not in {"VERIFIED", "DEMO"}:
                limits.append(found.get("reason", "ASSET_UNAVAILABLE"))
            else:
                resolved = found["asset"].ticker
                tokens = [self.layer.rwa.profile(t) for t in found["tokens"]]
                prices = [self.layer.rwa.observation(t) for t in tokens]
                self.layer.repository.save([found["asset"], *found["issuers"], *tokens, *prices])
                independent = None
                try:
                    if initial_regime.state == "REGULAR":
                        independent = self.layer.equity.get_snapshot(resolved)
                    else:
                        close = getattr(self.layer.equity, "get_previous_regular_close", None)
                        if close is not None:
                            independent = close(resolved, self.clock(), self.layer.calendar)
                        else:
                            limits.append("PREVIOUS_REGULAR_CLOSE_PROVIDER_UNAVAILABLE")
                    if independent is not None:
                        self.layer.repository.save([independent])
                except ProviderError as error:
                    limits.append("INDEPENDENT_EQUITY_" + error.kind)
                market_prices = []
                if self.layer.market is not None:
                    try:
                        market_prices = self.layer.market.prices(tokens, info=True)
                        self.layer.repository.save(market_prices)
                    except ProviderError as error:
                        limits.append("LIQUIDITY_" + error.kind)
                articles = []
                complete = False
                news_unavailable = False
                news_provider = getattr(self.layer, "news", self.layer.equity)
                try:
                    articles = news_provider.get_news(resolved, max_pages=1)
                    complete = getattr(news_provider, "last_page_complete", True)
                    self.layer.repository.save(articles)
                except ProviderError as error:
                    news_unavailable = True
                    limits.append("NEWS_" + error.kind)
                evaluated = self.clock()
                regime = self.regimes.evaluate(evaluated)
                limits.extend(self.layer.catalog_limitations().values())
                for token, price in zip(tokens, prices, strict=True):
                    info = next(
                        (
                            p
                            for p in market_prices
                            if p.chain_id == token.chain_id
                            and p.contract == token.contract
                            and p.issuer == token.platform_id
                        ),
                        None,
                    )
                    comparison_price = info or price
                    representations.append(
                        self.evaluate_representation(
                            token,
                            comparison_price,
                            independent,
                            info,
                            articles,
                            regime,
                            evaluated,
                            complete=complete,
                            news_unavailable=news_unavailable,
                            news_prefix_start=getattr(news_provider, "news_prefix_start", None),
                        )
                    )
        except ProviderError as error:
            limits.append("PROVIDER_" + error.kind)
            representations = []
        except (ValueError, ValidationError, TypeError, ArithmeticError):
            # Never render malformed input/provider payloads, including validation exception input.
            limits.append("MALFORMED_OR_CONFLICTING_TRUST_INPUT")
            representations = []
        evaluated = self.clock()
        result = TrustAssessment(
            assessment_id=uuid4(),
            run_id=run_id,
            request_id=request_id,
            correlation_id=correlation_id,
            data_mode=mode,
            evaluated_at=evaluated,
            ticker=resolved,
            status="ASSESSED" if representations else "UNAVAILABLE",
            regime=regime,
            representations=representations,
            limitations=sorted(set(limits)),
        )
        self.repository.save(result)
        logger.info(
            "TRUST_ASSESSMENT_PERSISTED",
            extra={
                "event_fields": {
                    "assessment_id": str(result.assessment_id),
                    "trust_status": result.status,
                    "run_id": run_id,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "data_mode": mode,
                }
            },
        )
        return result

    def evaluate_representation(
        self,
        token,
        price,
        independent,
        info,
        articles,
        regime,
        at,
        *,
        complete,
        news_unavailable=False,
        news_prefix_start=None,
    ):
        mode = self.layer.mode
        reference = self.references.evaluate(token, price, independent, regime, at, mode)
        liquidity = self.liquidity.evaluate(token, info, at, mode)
        economics = None
        if reference.status == "AVAILABLE":
            economics = comparable_economics(
                price.token_price, token.token_to_share_ratio, independent.price
            )
        samples, sample_truncated = self.repository.history(
            TrustSample, mode=mode, ticker=token.ticker, at=at, start=at - timedelta(days=1)
        )
        deviation = economics["deviation"] if economics else Decimal(0)
        scope = (
            mode,
            token.ticker,
            token.platform_id,
            token.chain_id,
            token.contract,
            regime.baseline_bucket,
            token.token_to_share_ratio,
            "CURRENT" if regime.state == "REGULAR" else "REGULAR_CLOSE",
            "trust-engineering-v1",
        )
        # Observed same-sign persistence, bounded by gaps and a 15-minute feature horizon.
        recent = sorted(
            [
                s
                for s in samples
                if s.scope == scope
                and at - timedelta(minutes=15) <= s.features.asof < at
                and s.features.available_at <= at
            ],
            key=lambda s: (s.features.asof, s.sample_id),
            reverse=True,
        )
        move_start = price.source_timestamp if price else at
        starting = deviation
        last_at = move_start or at
        with localcontext() as context:
            context.prec = 256
            for previous in recent:
                if (
                    not 0 <= seconds(last_at - previous.features.asof) <= 120
                    or previous.features.deviation * deviation <= 0
                ):
                    break
                starting = previous.features.deviation
                move_start = previous.features.asof
                last_at = move_start
        news = self.news.evaluate(
            articles,
            ticker=token.ticker,
            company=token.company_name,
            deviation=deviation,
            at=at,
            mode=mode,
            complete=complete,
            unavailable=news_unavailable,
            move_start=move_start,
            prefix_start=news_prefix_start,
        )
        features = None
        baseline = BaselineEvidence(
            status="INSUFFICIENT",
            sample_count=0,
            regime=regime.baseline_bucket,
            ticker=token.ticker,
            lookback_start=at - timedelta(days=180),
            decision_at=at,
        )
        analogues = AnalogueEvidence(
            status="INSUFFICIENT", eligible_sample_count=0, retrieved_sample_count=0
        )
        if economics and liquidity.status == "AVAILABLE" and not sample_truncated:
            observed = price.source_timestamp
            features = TrustFeatures(
                **economics,
                volume_24h_usd=liquidity.volume_24h_usd,
                liquidity_usd=liquidity.liquidity_usd,
                persistence_seconds=max(seconds(observed - (move_start or observed)), Decimal(0)),
                time_to_open_seconds=max(seconds(regime.next_open - at), Decimal(0)),
                starting_deviation=starting,
                ending_deviation=deviation,
                news_state=news.state,
                asof=at,
                available_at=at,
            )
            sample = TrustSample(
                sample_id=digest((*scope, observed, reference.reference_asof)),
                data_mode=mode,
                ticker=token.ticker,
                issuer=token.platform_id,
                chain_id=token.chain_id,
                contract=token.contract,
                regime=regime.baseline_bucket,
                ratio=token.token_to_share_ratio,
                reference_kind=scope[-2],
                features=features,
            )
            for episode in self.episodes.build(samples, at):
                self.repository.save(episode)
            from app.models.trust import TrustEpisode

            episodes, truncated = self.repository.history(
                TrustEpisode, mode=mode, ticker=token.ticker, at=at, start=at - timedelta(days=180)
            )
            baseline = self.baselines.evaluate(episodes, sample, at, truncated=truncated)
            analogues = self.analogues.evaluate(episodes, sample, baseline, at)
            # Do not seed incomplete news data into authoritative future histories.
            if news.coverage == "COMPLETE_REQUESTED_WINDOW":
                self.repository.save(sample)
        classification, confidence, reasons = self.classifier.classify(
            reference=reference,
            liquidity=liquidity,
            news=news,
            baseline=baseline,
            analogues=analogues,
            features=features,
            mode=mode,
        )
        if sample_truncated:
            classification, confidence = "INSUFFICIENT_EVIDENCE", None
            reasons.append("OBSERVATION_HISTORY_TRUNCATED")
        missing = reasons if classification == "INSUFFICIENT_EVIDENCE" else []
        if token.source_timestamp is None:
            reasons = [*reasons, "RATIO_SOURCE_ASOF_UNAVAILABLE_OBSERVED_AT_RECEIPT"]
        return RepresentationTrust(
            ticker=token.ticker,
            issuer=token.platform_id,
            chain_id=token.chain_id,
            contract=token.contract,
            symbol=token.token_symbol,
            token_price_usd=price.token_price if price else None,
            token_to_share_ratio=token.token_to_share_ratio,
            token_timestamp=price.source_timestamp if price else None,
            ratio_observed_at=token.ingestion_timestamp,
            ratio_source_timestamp=token.source_timestamp,
            reference=reference,
            liquidity=liquidity,
            news=news,
            baseline=baseline,
            analogues=analogues,
            economic_comparison=economics,
            features=features,
            classification=classification,
            confidence=confidence,
            evidence_quality=(
                "INSUFFICIENT"
                if missing
                else "SYNTHETIC_DEMO"
                if mode == "DEMO"
                else "LOCAL_EMPIRICAL_RESULT"
            ),
            reason_codes=sorted(set(reasons)),
            missing_evidence=sorted(set(missing)),
        )
