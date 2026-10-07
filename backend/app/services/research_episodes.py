"""Offline historical snapshots reuse the unchanged deterministic Trust pipeline."""

import hashlib
import json
from datetime import datetime, timedelta
from decimal import localcontext
from types import SimpleNamespace

from app.clients.common import ProviderError
from app.models.data import TokenObservation
from app.models.research import (
    OpeningTarget,
    ResearchDecision,
    ResearchEpisode,
    ResearchFrame,
    ResearchPolicy,
)
from app.models.trust import TrustEpisode, TrustSample
from app.services.normalization import effective_price_per_share
from app.services.opening_target import opening_outcome
from app.services.trust import TrustService
from app.services.trust_evidence import seconds


def fingerprint(value):
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def known(record, at):
    return (
        record.source_timestamp is not None
        and record.source_timestamp <= at
        and record.ingestion_timestamp <= at
    )


def latest(records):
    return max(records, key=lambda r: (r.source_timestamp, fingerprint(r)), default=None)


class HistoricalTrustSnapshot:
    """Only analytical records known at T. No database, transport or execution client."""

    def __init__(self, frame):
        self.records = [*frame.samples, *frame.baseline_episodes]

    def save(self, record):
        # Newly completed windows use the existing EpisodeBuilder. Snapshot-local only.
        if isinstance(record, TrustSample):
            return
        if isinstance(record, TrustEpisode) and not any(
            getattr(r, "episode_id", None) == record.episode_id
            for r in self.records
            if isinstance(r, TrustEpisode)
        ):
            self.records.append(record)

    def history(self, model, *, mode, ticker, at, start):
        rows = []
        for record in self.records:
            if type(record) is not model:
                continue
            sample = record if model is TrustSample else record.sample
            available = (
                sample.features.available_at
                if model is TrustSample
                else record.outcome_available_at
            )
            if sample.data_mode == mode and sample.ticker == ticker and start <= available <= at:
                rows.append(record)
        rows.sort(key=lambda r: fingerprint(r))
        return rows[:5000], len(rows) > 5000


class ResearchEpisodeBuilder:
    def __init__(self, calendar, policy=None):
        self.calendar = calendar
        policy = policy or ResearchPolicy()
        self.policy = ResearchPolicy.model_validate(policy.model_dump())

    def decision(self, frame):
        frame = ResearchFrame.model_validate(frame.model_dump())
        at = frame.decision_at
        layer = SimpleNamespace(mode=frame.data_mode, calendar=self.calendar)
        trust = TrustService(layer, None, clock=lambda: at)
        trust.repository = HistoricalTrustSnapshot(frame)
        # Calendar failures are explicit caller errors, never assigned an invented session.
        regime = trust.regimes.evaluate(at)
        previous_close = regime.previous_regular_close
        identity = (frame.ticker, frame.issuer, frame.chain_id, frame.contract)
        metadata = latest(
            [
                m
                for m in frame.metadata
                if known(m, at) and (m.ticker, m.platform_id, m.chain_id, m.contract) == identity
            ]
        )
        prices = [
            p
            for p in frame.tokens
            if isinstance(p, TokenObservation)
            and known(p, at)
            and (p.ticker, p.issuer, p.chain_id, p.contract) == identity
        ]
        price = latest(prices)
        info = latest([p for p in prices if p.kind == "PRICE_INFO"])
        # Last completed minute of the ACTUAL previous regular session, no extended-hours close.
        references = [
            b
            for b in frame.equities
            if known(b, at)
            and b.ticker == frame.ticker
            and b.source in {"MASSIVE", "DEMO_EQUITY"}
            and b.interval == "1minute"
            and b.kind in {"BAR", "REGULAR_CLOSE"}
            and b.source_timestamp + timedelta(minutes=1) == previous_close
        ]
        reference = latest(references)
        reasons = []
        if len({(b.close or b.price, b.adjusted) for b in references}) > 1:
            reasons.append("CONFLICTING_REGULAR_CLOSE_REVISIONS")
        used_proofs = []

        def proof(record, code):
            matches = [
                p
                for p in frame.proofs
                if p.record_digest == fingerprint(record)
                and p.effective_at <= at
                and p.available_at <= at
            ]
            if not matches:
                reasons.append(code)
            else:
                used_proofs.append(min(matches, key=lambda p: (p.available_at, fingerprint(p))))

        if metadata is None:
            reasons.append("ASOF_TOKEN_SHARE_RATIO_UNAVAILABLE")
        else:
            proof(metadata, "ASOF_TOKEN_SHARE_RATIO_UNVERIFIED")
        if reference is None:
            reasons.append("KNOWN_PREVIOUS_REGULAR_CLOSE_UNAVAILABLE")
        else:
            proof(reference, "ASOF_EQUITY_REVISION_UNVERIFIED")
        calendar_available = datetime.fromisoformat(self.calendar.data["verified_at"])
        if calendar_available > at:
            reasons.append("CALENDAR_VERSION_NOT_YET_VERIFIED")
        if regime.state == "REGULAR" or at >= regime.next_open:
            reasons.append("OPENING_MODEL_REQUIRES_OFF_HOURS_DECISION")
        representation = None
        sample = None
        volume_percentile = None
        if metadata is not None and price is not None:
            adapted = (
                reference.model_copy(
                    update={
                        "kind": "REGULAR_CLOSE",
                        "price": reference.close or reference.price,
                    }
                )
                if reference
                else None
            )
            complete = (
                frame.news_coverage_available_at is not None
                and frame.news_coverage_available_at <= at
            )
            representation = trust.evaluate_representation(
                metadata,
                price,
                adapted,
                info,
                [
                    n
                    for n in frame.news
                    if n.published_timestamp <= at and n.ingestion_timestamp <= at
                ],
                regime,
                at,
                complete=complete,
                news_unavailable=not complete,
                news_prefix_start=frame.news_prefix_start,
            )
            if representation.features is not None:
                sample = TrustSample(
                    sample_id=fingerprint(representation.features),
                    data_mode=frame.data_mode,
                    ticker=frame.ticker,
                    issuer=frame.issuer,
                    chain_id=frame.chain_id,
                    contract=frame.contract,
                    regime=regime.baseline_bucket,
                    ratio=metadata.token_to_share_ratio,
                    reference_kind="REGULAR_CLOSE",
                    features=representation.features,
                )
            volume_percentile = representation.baseline.volume_percentile
            if representation.reference.status != "AVAILABLE":
                reasons.extend(representation.reference.reason_codes)
            if representation.liquidity.status != "AVAILABLE":
                reasons.append("AUTHORITATIVE_LIQUIDITY_UNAVAILABLE")
            if representation.news.coverage != "COMPLETE_REQUESTED_WINDOW":
                reasons.append("DECISION_TIME_NEWS_COVERAGE_UNVERIFIED")
            if representation.baseline.status != "SUFFICIENT":
                reasons.append("BASELINE_" + representation.baseline.status)
        else:
            reasons.append("KNOWN_TOKEN_PRICE_OR_METADATA_UNAVAILABLE")
        if sample is None or volume_percentile is None:
            reasons.append("REQUIRED_FEATURES_UNAVAILABLE")
        # Optional opening-model movement input: two independently verified as-of ratios,
        # normalized at each endpoint. No constant-ratio assumption or current-ratio backfill.
        closure_token = None
        off_hours_return = None
        anchor = latest(
            [
                p
                for p in prices
                if known(p, previous_close)
                and p.kind in {"PRICE", "PRICE_INFO"}
                and p.source in {"BINANCE_MARKET", "BINANCE_RWA", "DEMO_MARKET", "DEMO_DATA"}
                and p.token_price is not None
                and 0 <= seconds(previous_close - p.source_timestamp) <= 120
            ]
        )
        anchor_metadata = latest(
            [
                m
                for m in frame.metadata
                if known(m, previous_close)
                and (m.ticker, m.platform_id, m.chain_id, m.contract) == identity
            ]
        )
        if anchor is not None and anchor_metadata is not None and sample is not None:
            anchor_proofs = [
                p
                for p in frame.proofs
                if p.record_digest == fingerprint(anchor_metadata)
                and p.available_at <= previous_close
                and p.effective_at <= anchor.source_timestamp
            ]
            if (
                anchor_proofs
                and anchor.token_to_share_ratio == anchor_metadata.token_to_share_ratio
                and anchor.data_quality == ("DEMO" if frame.data_mode == "DEMO" else "LIVE")
                and any(p.record_digest == fingerprint(metadata) for p in used_proofs)
            ):
                closure_token = anchor
                used_proofs.extend(anchor_proofs)
                with localcontext() as context:
                    context.prec = 256
                    start = effective_price_per_share(
                        anchor.token_price, anchor_metadata.token_to_share_ratio
                    )
                    off_hours_return = sample.features.effective_price_per_share_usd / start - 1
        payload = dict(
            decision_at=at,
            data_mode=frame.data_mode,
            ticker=frame.ticker,
            issuer=frame.issuer,
            chain_id=frame.chain_id,
            contract=frame.contract,
            regime=regime.baseline_bucket,
            opening_at=regime.next_open,
            previous_close_at=previous_close,
            token=price,
            independent_equity=reference,
            trust=representation,
            sample=sample,
            volume_percentile=volume_percentile,
            off_hours_return=off_hours_return,
            closure_token=closure_token,
            data_quality="REJECTED" if reasons else "ELIGIBLE",
            reasons=tuple(sorted(set(reasons))),
            provenance=tuple(used_proofs),
            policy=self.policy,
        )
        provisional = ResearchDecision(decision_id="", **payload)
        return provisional.model_copy(update={"decision_id": fingerprint(provisional)})

    def target(self, decision, bars, proofs=()):
        opening = decision.opening_at
        end = opening + timedelta(minutes=self.policy.opening_minutes)
        bars = [
            b for b in bars if b.ticker == decision.ticker and b.data_mode == decision.data_mode
        ]
        # Shared outcome routine only accepts independent Massive LIVE history. DEMO is an
        # explicitly marked test adapter, never a provider or production-evidence substitution.
        if decision.data_mode == "DEMO":
            bars_for_calculation = [
                b.model_copy(
                    update={"source": "MASSIVE", "data_mode": "LIVE", "data_quality": "HISTORICAL"}
                )
                for b in bars
                if b.source == "DEMO_EQUITY"
            ]
        else:
            bars_for_calculation = bars
        outcome = opening_outcome(bars_for_calculation, decision.previous_close_at, opening)
        if outcome["status"] == "UNSCORABLE":
            return OpeningTarget(
                status="UNSCORABLE",
                opening_at=opening,
                completed_at=end,
                reasons=(outcome["reason"],),
            )
        relevant = [
            b
            for b in bars
            if b.source_timestamp in {decision.previous_close_at - timedelta(minutes=1), opening}
            and b.interval in {"1minute", f"{self.policy.opening_minutes}minute"}
        ]
        bound = [p for p in proofs if p.record_digest in {fingerprint(b) for b in relevant}]
        verified = {p.record_digest for p in bound}
        has_proofs = all(fingerprint(b) in verified for b in relevant) and len(relevant) >= 2
        available = max(
            [datetime.fromisoformat(outcome["target_available_at"])]
            + [b.ingestion_timestamp for b in relevant]
            + [p.available_at for p in bound]
        )
        return OpeningTarget(
            status="AVAILABLE" if has_proofs else "POSTHOC_ONLY",
            opening_at=opening,
            completed_at=end,
            available_at=available,
            previous_close=outcome["previous_close"],
            first_bar_close=outcome["first_5m_close"],
            opening_return=outcome["opening_return"],
            provenance=tuple(bound),
            reasons=() if has_proofs else ("POINT_IN_TIME_OUTCOME_REVISION_UNVERIFIED",),
        )

    def build(self, frame):
        decision = self.decision(frame)
        target = self.target(decision, frame.equities, frame.proofs)
        identifier = fingerprint(
            {
                "decision_id": decision.decision_id,
                "opening": decision.opening_at.isoformat(),
                "target_version": self.policy.target_version,
            }
        )
        return ResearchEpisode(
            episode_id=identifier,
            decision=decision,
            target=target,
            evidence_kind="SYNTHETIC_TEST" if frame.data_mode == "DEMO" else "LOCAL_OBSERVATIONS",
        )


def candidate_frames(calendar, *, metadata, tokens, equities, news=(), mode="LIVE"):
    """Enumerate every captured representation/reopening; never pad sparse raw history."""
    groups = sorted({(p.ticker, p.issuer, p.chain_id, p.contract) for p in tokens})
    dates = sorted(
        {
            b.source_timestamp.astimezone(calendar.zone).date()
            for b in equities
            if b.source_timestamp and b.interval == "5minute" and b.kind == "BAR"
        }
    )
    for ticker, issuer, chain, contract in groups:
        for day in dates:
            try:
                session = calendar.session(day)
                if session is None:
                    continue
                opening = session[0]
                close = calendar.previous_session(opening)[1]
            except ProviderError:
                continue
            # One pre-opening decision per observed reopening; includes every date with raw
            # closure observations, even when density or first availability subsequently fails.
            if not any(
                p.ticker == ticker
                and p.issuer == issuer
                and p.contract == contract
                and p.source_timestamp
                and close <= p.source_timestamp < opening
                for p in tokens
            ):
                continue
            yield ResearchFrame(
                decision_at=opening - timedelta(seconds=1),
                ticker=ticker,
                issuer=issuer,
                chain_id=chain,
                contract=contract,
                data_mode=mode,
                metadata=tuple(metadata),
                tokens=tuple(tokens),
                equities=tuple(equities),
                news=tuple(news),
            )
