"""Versioned deterministic vectors, point-in-time retrieval and rolling Decimal QR OLS."""

from datetime import timedelta
from decimal import Decimal, localcontext

from app.models.research import (
    NEWS,
    REGIMES,
    AnalogueMatch,
    OpeningPrediction,
    ResearchDecision,
    ResearchEpisode,
    ResearchPolicy,
    RetrievalResult,
)
from app.services.research_episodes import fingerprint


def direction(value):
    return "UP" if value > 0 else "DOWN" if value < 0 else "FLAT"


def feature_values(decision, policy):
    if decision.data_quality != "ELIGIBLE" or decision.sample is None:
        raise ValueError("Eligible complete features are required")
    f = decision.sample.features
    with localcontext() as context:
        context.prec = 256
        return {
            "deviation": f.deviation / policy.deviation_scale,
            "absolute_deviation": f.absolute_deviation / policy.deviation_scale,
            "volume_percentile": decision.volume_percentile,
            "persistence": f.persistence_seconds / policy.persistence_scale,
            "time_to_open": f.time_to_open_seconds / policy.time_scale,
            "starting_deviation": f.starting_deviation / policy.deviation_scale,
            "ending_deviation": f.ending_deviation / policy.deviation_scale,
            "news_flag": Decimal(f.news_state in {"CORROBORATING", "RELEVANT_NEWS"}),
            "off_hours_return": decision.off_hours_return,
        }


def vector(decision, policy=None):
    policy = policy or ResearchPolicy()
    values = feature_values(decision, policy)
    f = decision.sample.features
    with localcontext() as context:
        context.prec = 256
        result = [
            values[k]
            for k in (
                "deviation",
                "absolute_deviation",
                "volume_percentile",
                "persistence",
                "time_to_open",
                "starting_deviation",
                "ending_deviation",
            )
        ]
        result.extend(Decimal(decision.regime == state) for state in REGIMES)
        result.extend(Decimal(f.news_state == state) for state in NEWS)
        norm = sum(v * v for v in result).sqrt()
        if norm == 0:
            raise ValueError("Zero vector")
        return tuple(v / norm for v in result)


def cosine(left, right):
    if len(left) != len(right) or not left:
        raise ValueError("Matching nonempty vectors required")
    with localcontext() as context:
        context.prec = 256
        denominator = (sum(v * v for v in left) * sum(v * v for v in right)).sqrt()
        if denominator == 0:
            raise ValueError("Zero norm")
        return max(
            Decimal(-1),
            min(Decimal(1), sum(a * b for a, b in zip(left, right, strict=True)) / denominator),
        )


def eligible(episodes, current, policy):
    """Count independent opening outcomes within exact representation/ratio/regime scope."""
    current = ResearchDecision.model_validate(current.model_dump())
    by_id = {}
    rejected = {}
    conflicts = set()
    at = current.decision_at
    for raw in episodes:
        # Do not even inspect future decisions/outcome values or publish their IDs at T.
        if raw.decision.decision_at >= at:
            continue
        if (
            raw.target.available_at is None
            or raw.target.available_at > at
            or raw.target.completed_at > at
        ):
            rejected[raw.episode_id] = ("FUTURE_OR_UNAVAILABLE_OUTCOME",)
            continue
        episode = ResearchEpisode.model_validate(raw.model_dump())
        prior = by_id.get(episode.episode_id)
        if prior and fingerprint(prior) != fingerprint(episode):
            conflicts.add(episode.episode_id)
        by_id[episode.episode_id] = episode
    choices = []
    for identifier, e in sorted(by_id.items()):
        reasons = []
        d, target = e.decision, e.target
        if identifier in conflicts:
            reasons.append("CONFLICTING_EPISODE_ID")
        if d.data_quality != "ELIGIBLE":
            reasons.append("REJECTED_FEATURES")
        if current.scope is None or d.scope != current.scope:
            reasons.append("SCOPE_MISMATCH")
        if not at - timedelta(days=policy.lookback_days) <= d.decision_at < at:
            reasons.append("OUTSIDE_PAST_LOOKBACK")
        if target.status != "AVAILABLE" or target.target_version != policy.target_version:
            reasons.append("INVALID_OR_UNVERIFIED_TARGET")
        if target.available_at is None or target.available_at > at or target.completed_at > at:
            reasons.append("FUTURE_OR_UNAVAILABLE_OUTCOME")
        if e.evidence_kind == "SYNTHETIC_TEST" and current.data_mode != "DEMO":
            reasons.append("SYNTHETIC_EVIDENCE_FORBIDDEN")
        if reasons:
            rejected[identifier] = tuple(reasons)
        else:
            choices.append(e)
    # Multiple decisions before the same stock opening are NOT independent model samples.
    unique = {}
    for e in sorted(choices, key=lambda e: (e.decision.decision_at, e.episode_id)):
        key = (e.decision.ticker, e.target.opening_at)
        previous = unique.get(key)
        if previous:
            rejected[previous.episode_id] = ("DUPLICATE_UNDERLYING_OPENING",)
        unique[key] = e
    return sorted(unique.values(), key=lambda e: (e.decision.decision_at, e.episode_id)), rejected


class HistoricalRetrieval:
    def __init__(self, policy=None):
        self.policy = policy or ResearchPolicy()

    def evaluate(self, episodes, current):
        try:
            current = ResearchDecision.model_validate(current.model_dump())
            candidates, rejected = eligible(episodes, current, self.policy)
        except (ValueError, TypeError, AttributeError):
            return RetrievalResult(status="NOT_READY", eligible_count=0, retrieved_count=0)
        if current.data_quality != "ELIGIBLE":
            return RetrievalResult(
                status="NOT_READY",
                eligible_count=len(candidates),
                retrieved_count=0,
                rejected=rejected,
            )
        matches = []
        query = vector(current, self.policy)
        for e in candidates:
            similarity = cosine(query, vector(e.decision, self.policy))
            if similarity >= self.policy.similarity_floor:
                matches.append(
                    AnalogueMatch(
                        episode_id=e.episode_id,
                        similarity=similarity,
                        opening_return=e.target.opening_return,
                        pattern=direction(e.target.opening_return),
                        outcome_available_at=e.target.available_at,
                        feature_at=e.decision.decision_at,
                        feature_available_at=e.decision.sample.features.available_at,
                        provenance=(*e.decision.provenance, *e.target.provenance),
                        evidence_kind=e.evidence_kind,
                    )
                )
            else:
                rejected[e.episode_id] = ("BELOW_SIMILARITY_FLOOR",)
        matches.sort(key=lambda m: (m.similarity.copy_negate(), m.episode_id))
        selected = tuple(matches[: self.policy.top_k])
        sufficient = len(selected) >= self.policy.min_analogues
        patterns = [m.pattern for m in selected]
        return RetrievalResult(
            status="SUFFICIENT" if sufficient else "INSUFFICIENT_DATA",
            eligible_count=len(candidates),
            retrieved_count=len(selected),
            matches=selected,
            rejected=rejected,
            historical_pattern=(
                max(sorted(set(patterns)), key=patterns.count)
                if sufficient
                else "INSUFFICIENT_DATA"
            ),
        )


def qr_fit(matrix, targets, tolerance):
    """Twice-reorthogonalized modified Gram-Schmidt, avoiding normal-equation squaring."""
    n, p = len(matrix), len(matrix[0])
    q = []
    r = [[Decimal(0) for _ in range(p)] for _ in range(p)]
    for j in range(p):
        column = [row[j] for row in matrix]
        original_norm = sum(v * v for v in column).sqrt()
        for _ in range(2):
            for i, basis in enumerate(q):
                coefficient = sum(a * b for a, b in zip(basis, column, strict=True))
                r[i][j] += coefficient
                column = [a - coefficient * b for a, b in zip(column, basis, strict=True)]
        norm = sum(v * v for v in column).sqrt()
        if norm <= tolerance * max(Decimal(1), original_norm):
            raise ValueError("RANK_DEFICIENT_DESIGN")
        r[j][j] = norm
        q.append([v / norm for v in column])

    def solve(rhs):
        result = [Decimal(0)] * p
        for i in reversed(range(p)):
            result[i] = (rhs[i] - sum(r[i][j] * result[j] for j in range(i + 1, p))) / r[i][i]
        return result

    beta = solve([sum(a * b for a, b in zip(column, targets, strict=True)) for column in q])
    inverse_columns = [solve([Decimal(i == j) for i in range(p)]) for j in range(p)]
    inverse = [[inverse_columns[j][i] for j in range(p)] for i in range(p)]
    residuals = [
        y - sum(a * b for a, b in zip(row, beta, strict=True))
        for row, y in zip(matrix, targets, strict=True)
    ]
    variance = sum(v * v for v in residuals) / (n - p)
    return beta, inverse, variance


class RollingOpeningModel:
    def __init__(self, policy=None):
        policy = policy or ResearchPolicy()
        self.policy = ResearchPolicy.model_validate(policy.model_dump())

    def predict(self, episodes, current):
        try:
            current = ResearchDecision.model_validate(current.model_dump())
            candidates, _ = eligible(episodes, current, self.policy)
        except (ValueError, TypeError, AttributeError):
            return OpeningPrediction(
                status="NOT_READY",
                reason="MALFORMED_OR_INVALID_RESEARCH_INPUT",
                eligible_count=0,
                sample_count=0,
                evidence_kind="SYNTHETIC_TEST"
                if getattr(current, "data_mode", None) == "DEMO"
                else "LOCAL_EMPIRICAL_RESULT",
            )
        rows = candidates[-self.policy.rolling_window :]
        common = dict(
            eligible_count=len(candidates),
            sample_count=len(rows),
            training_ids=tuple(e.episode_id for e in rows),
            evidence_kind="SYNTHETIC_TEST"
            if current.data_mode == "DEMO"
            else "LOCAL_EMPIRICAL_RESULT",
        )
        if current.data_quality != "ELIGIBLE":
            return OpeningPrediction(
                status="NOT_READY", reason="REJECTED_CURRENT_FEATURES", **common
            )
        if len(rows) < self.policy.min_model_samples:
            return OpeningPrediction(
                status="INSUFFICIENT_DATA", reason="MINIMUM_30_NOT_MET", **common
            )
        keys = self.policy.model_features
        if len(rows) <= len(keys) + 1:
            return OpeningPrediction(status="NOT_READY", reason="NO_RESIDUAL_DOF", **common)
        with localcontext() as context:
            context.prec = 256
            values = [feature_values(e.decision, self.policy) for e in rows]
            query = feature_values(current, self.policy)
            if any(query[k] is None or any(v[k] is None for v in values) for k in keys):
                return OpeningPrediction(
                    status="NOT_READY", reason="MISSING_MODEL_FEATURES", **common
                )
            means = {k: sum(v[k] for v in values) / len(values) for k in keys}
            scales = {
                k: (sum((v[k] - means[k]) ** 2 for v in values) / len(values)).sqrt() for k in keys
            }
            if any(s == 0 for s in scales.values()):
                return OpeningPrediction(
                    status="NOT_READY", reason="RANK_DEFICIENT_DESIGN", **common
                )
            matrix = [[Decimal(1)] + [(v[k] - means[k]) / scales[k] for k in keys] for v in values]
            x = [Decimal(1)] + [(query[k] - means[k]) / scales[k] for k in keys]
            # No extrapolation represented as high confidence outside measured support.
            if any(
                not min(v[k] for v in values) <= query[k] <= max(v[k] for v in values) for k in keys
            ):
                return OpeningPrediction(
                    status="NOT_READY", reason="OUTSIDE_TRAINING_SUPPORT", **common
                )
            try:
                beta, inverse, variance = qr_fit(
                    matrix, [e.target.opening_return for e in rows], self.policy.rank_tolerance
                )
            except ValueError:
                return OpeningPrediction(
                    status="NOT_READY", reason="RANK_DEFICIENT_DESIGN", **common
                )
            prediction = sum(a * b for a, b in zip(x, beta, strict=True))
            if prediction <= -1:
                return OpeningPrediction(
                    status="NOT_READY", reason="INVALID_PREDICTED_PRICE", **common
                )
            leverage = sum(
                sum(x[i] * inverse[i][j] for i in range(len(x))) ** 2 for j in range(len(x))
            )
            width = self.policy.prediction_interval_multiplier * (variance * (1 + leverage)).sqrt()
            coefficients = {k: beta[i + 1] / scales[k] for i, k in enumerate(keys)}
            coefficients["intercept"] = beta[0] - sum(coefficients[k] * means[k] for k in keys)
            model_id = fingerprint(
                {
                    "policy": self.policy.model_dump(mode="json"),
                    "training": [e.model_dump(mode="json") for e in rows],
                    "coefficients": {k: str(v) for k, v in coefficients.items()},
                }
            )
            return OpeningPrediction(
                status="READY",
                reason="ROLLING_QR_OLS_LOCAL_FIT",
                **common,
                model_id=model_id,
                coefficients=coefficients,
                predicted_return=prediction,
                interval_low=prediction - width,
                interval_high=prediction + width,
                direction=direction(prediction),
                confidence="UNCALIBRATED",
            )
