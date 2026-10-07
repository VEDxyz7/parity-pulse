"""Versioned deterministic heuristics. Confidence is not calibrated probability."""


class TrustClassifier:
    def classify(self, *, reference, liquidity, news, baseline, analogues, features, mode):
        missing = list(reference.reason_codes)
        if reference.status != "AVAILABLE":
            missing.append("INDEPENDENT_COMPARISON_UNAVAILABLE")
        if liquidity.status != "AVAILABLE":
            missing.append("LIQUIDITY_" + liquidity.status)
            missing.extend(liquidity.reason_codes)
        if features is None:
            missing.append("FEATURES_UNAVAILABLE")
        if baseline.status != "SUFFICIENT":
            missing.append("BASELINE_" + baseline.status)
        if analogues.status != "SUFFICIENT":
            missing.append("ANALOGUES_INSUFFICIENT")
        if news.coverage != "COMPLETE_REQUESTED_WINDOW":
            missing.append("NEWS_COVERAGE_" + news.coverage)
        if missing:
            return "INSUFFICIENT_EVIDENCE", None, sorted(set(missing))
        if news.directional_state == "CONFLICTING":
            return "INSUFFICIENT_EVIDENCE", None, ["CONFLICTING_NEWS_EVIDENCE"]
        # Percentiles belong ONLY to this stock/issuer/contract/ratio/regime/reference-kind.
        absolute = baseline.absolute_deviation.quantiles
        volume = baseline.volume.quantiles
        persistence = baseline.persistence.quantiles
        liquidity_stats = baseline.liquidity.quantiles
        confidence = (
            "LOW"  # Uncalibrated heuristic, including synthetic DEMO; never upgraded by news.
        )
        if (
            features.absolute_deviation <= absolute["75"]
            and features.liquidity_usd >= liquidity_stats["25"]
        ):
            return "NORMAL", confidence, ["DEVIATION_WITHIN_STOCK_REGIME_BASELINE"]
        unusual = features.absolute_deviation >= absolute["95"]
        reversed_count = sum(m["outcome"] == "REVERSED" for m in analogues.matches)
        persisted_count = sum(m["outcome"] == "PERSISTED" for m in analogues.matches)
        if (
            unusual
            and features.volume_24h_usd <= volume["25"]
            and features.persistence_seconds <= persistence["25"]
            and features.liquidity_usd <= liquidity_stats["25"]
            and news.state == "NO_RELEVANT_NEWS"
            and reversed_count >= 2
        ):
            return (
                "LIKELY_NOISE",
                confidence,
                [
                    "HIGH_DEVIATION",
                    "LOW_RELATIVE_VOLUME",
                    "SHORT_PERSISTENCE",
                    "POOR_RELATIVE_LIQUIDITY",
                    "NO_NEWS_IN_COVERED_WINDOW",
                    "HISTORICAL_REVERSAL",
                ],
            )
        if (
            unusual
            and features.volume_24h_usd >= volume["75"]
            and features.persistence_seconds >= persistence["75"]
            and features.liquidity_usd >= liquidity_stats["50"]
            and news.state == "CORROBORATING"
            and persisted_count >= 2
        ):
            return (
                "LIKELY_INFORMATION",
                confidence,
                [
                    "HIGH_DEVIATION",
                    "HIGH_RELATIVE_VOLUME",
                    "PERSISTENT_MOVE",
                    "HEADLINE_DIRECTION_CORROBORATION",
                    "HISTORICAL_PERSISTENCE",
                    "HEURISTIC_NOT_CAUSAL_OR_CALIBRATED",
                ],
            )
        return "INSUFFICIENT_EVIDENCE", None, ["MIXED_OR_UNSUPPORTED_EVIDENCE"]
