"""Decimal baselines and cosine retrieval; outcomes never enter similarity vectors."""

import hashlib
from datetime import timedelta
from decimal import Decimal, localcontext

from app.models.trust import AnalogueEvidence, BaselineEvidence, Distribution, TrustEpisode
from app.services.trust_evidence import seconds


def digest(parts):
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def percentile(values, probability):
    ordered = sorted(values)
    with localcontext() as context:
        context.prec = 256
        position = (len(ordered) - 1) * probability
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values):
    with localcontext() as context:
        context.prec = 256
        mean = sum(values) / len(values)
        median = percentile(values, Decimal("0.5"))
        return Distribution(
            mean=mean,
            median=median,
            mad=percentile([abs(v - median) for v in values], Decimal("0.5")),
            standard_deviation=(sum((v - mean) ** 2 for v in values) / len(values)).sqrt(),
            quantiles={
                str(q): percentile(values, Decimal(q) / 100) for q in [25, 50, 75, 90, 95, 99]
            },
        )


def rank(values, value):
    with localcontext() as context:
        context.prec = 256
        return Decimal(sum(v <= value for v in values)) / len(values)


def eligible_episodes(episodes, sample, at):
    start = at - timedelta(days=180)
    return sorted(
        [
            e
            for e in episodes
            if e.sample.scope == sample.scope
            and start <= e.sample.features.asof < at
            and e.ended_at <= at
            and e.outcome_available_at <= at
            and e.sample.features.available_at <= at
            and e.episode_id != digest((*sample.scope, bucket_start(at)))
        ],
        key=lambda e: (e.sample.features.asof, e.episode_id),
    )


def bucket_start(at):
    return at.replace(minute=at.minute // 30 * 30, second=0, microsecond=0)


class BaselineService:
    def evaluate(self, episodes, sample, at, *, truncated=False):
        eligible = eligible_episodes(episodes, sample, at)
        result = dict(
            status="TRUNCATED" if truncated else "INSUFFICIENT",
            sample_count=len(eligible),
            regime=sample.regime,
            ticker=sample.ticker,
            lookback_start=at - timedelta(days=180),
            decision_at=at,
        )
        if len(eligible) < 30 or truncated:
            return BaselineEvidence(**result)
        fields = {
            "deviation": "deviation",
            "absolute_deviation": "absolute_deviation",
            "volume": "volume_24h_usd",
            "liquidity": "liquidity_usd",
            "persistence": "persistence_seconds",
        }
        series = {
            key: [getattr(e.sample.features, attr) for e in eligible]
            for key, attr in fields.items()
        }
        stats = {key: distribution(values) for key, values in series.items()}
        std = stats["deviation"].standard_deviation
        result["status"] = "SUFFICIENT" if std > 0 else "DEGENERATE"
        with localcontext() as context:
            context.prec = 256
            return BaselineEvidence(
                **result,
                **stats,
                deviation_percentile=rank(
                    series["absolute_deviation"], sample.features.absolute_deviation
                ),
                volume_percentile=rank(series["volume"], sample.features.volume_24h_usd),
                z_score=(sample.features.deviation - stats["deviation"].mean) / std
                if std
                else None,
            )


class EpisodeBuilder:
    """Completed UTC windows only, bounded gaps and at least 26 minutes of coverage."""

    def build(self, samples, at):
        groups = {}
        for sample in samples:
            feature = sample.features
            if feature.asof <= at and feature.available_at <= at:
                key = (*sample.scope, bucket_start(feature.asof))
                groups.setdefault(key, []).append(sample)
        episodes = []
        for key, group in groups.items():
            start = key[-1]
            end = start + timedelta(minutes=30)
            if end > at:
                continue
            ordered = sorted(group, key=lambda s: (s.features.asof, s.sample_id))
            # At most one observation per source timestamp; repeated API calls cannot add history.
            unique = {s.features.asof: s for s in ordered}
            ordered = list(unique.values())
            if (
                len(ordered) < 2
                or ordered[0].features.asof > start + timedelta(seconds=120)
                or ordered[-1].features.asof < end - timedelta(seconds=120)
                or any(
                    seconds(b.features.asof - a.features.asof) > 120
                    for a, b in zip(ordered, ordered[1:], strict=False)
                )
            ):
                continue
            middle = [s for s in ordered if s.features.asof <= start + timedelta(minutes=15)]
            if not middle:
                continue
            feature = middle[-1]
            initial = feature.features.deviation
            final = ordered[-1].features.deviation
            with localcontext() as context:
                context.prec = 256
                outcome = (
                    "REVERSED"
                    if initial != 0 and (initial * final <= 0 or abs(final) <= abs(initial) / 2)
                    else "PERSISTED"
                    if initial * final > 0 and abs(final) >= abs(initial)
                    else "MIXED"
                )
            episodes.append(
                TrustEpisode(
                    episode_id=digest(key),
                    sample=feature,
                    started_at=start,
                    ended_at=end,
                    outcome_available_at=at,
                    outcome_deviation=final,
                    outcome=outcome,
                    observation_count=len(ordered),
                )
            )
        return sorted(episodes, key=lambda e: (e.started_at, e.episode_id))


class AnalogueService:
    @staticmethod
    def vector(sample, baseline):
        feature = sample.features
        # Same scope fixes the categorical regime. One-hot news states are exact indicators.
        scales = [
            baseline.deviation.standard_deviation,
            baseline.absolute_deviation.quantiles["95"],
            baseline.volume.quantiles["95"],
            baseline.persistence.quantiles["95"],
            Decimal(86400),
            baseline.absolute_deviation.quantiles["95"],
            baseline.absolute_deviation.quantiles["95"],
        ]
        values = [
            feature.deviation,
            feature.absolute_deviation,
            feature.volume_24h_usd,
            feature.persistence_seconds,
            feature.time_to_open_seconds,
            feature.starting_deviation,
            feature.ending_deviation,
        ]
        with localcontext() as context:
            context.prec = 256
            result = [
                value / scale if scale else Decimal(0)
                for value, scale in zip(values, scales, strict=True)
            ]
            result += [
                Decimal(feature.news_state == state)
                for state in [
                    "NO_RELEVANT_NEWS",
                    "RELEVANT_NEWS",
                    "CORROBORATING",
                    "CONFLICTING",
                    "PARTIAL",
                    "UNAVAILABLE",
                ]
            ]
            norm = sum(v * v for v in result).sqrt()
            return [v / norm for v in result] if norm else None

    def evaluate(self, episodes, sample, baseline, at):
        eligible = eligible_episodes(episodes, sample, at)
        matches = []
        if baseline.status == "SUFFICIENT":
            with localcontext() as context:
                context.prec = 256
                current = self.vector(sample, baseline)
                if current is not None:
                    for episode in eligible:
                        vector = self.vector(episode.sample, baseline)
                        if vector is None:
                            continue
                        similarity = sum(a * b for a, b in zip(current, vector, strict=True))
                        if similarity >= Decimal("0.8"):
                            matches.append(
                                {
                                    "episode_id": episode.episode_id,
                                    "similarity": min(similarity, Decimal(1)),
                                    "feature_at": episode.sample.features.asof.isoformat(),
                                    "feature_available_at": (
                                        episode.sample.features.available_at.isoformat()
                                    ),
                                    "completed_at": episode.ended_at.isoformat(),
                                    "outcome_available_at": (
                                        episode.outcome_available_at.isoformat()
                                    ),
                                    "outcome": episode.outcome,
                                    "evidence_kind": episode.evidence_kind,
                                }
                            )
            matches.sort(key=lambda m: (m["similarity"].copy_negate(), m["episode_id"]))
            matches = matches[:3]
        return AnalogueEvidence(
            status="SUFFICIENT" if len(matches) >= 3 else "INSUFFICIENT",
            eligible_sample_count=len(eligible),
            retrieved_sample_count=len(matches),
            matches=matches,
        )
