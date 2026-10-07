"""Isolated read-only capability audit; never overwrite previous verification runs."""

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.clients.binance_web3 import PREFIX, BinanceWeb3Client
from app.clients.common import ProviderError
from app.clients.massive import MassiveClient
from app.config import ROOT_DIR, Settings
from app.database import Database
from app.services.data_layer import DataLayer
from app.services.trust import TrustService
from app.utils.logging import configure_logging


class PoolDiagnosticClient(BinanceWeb3Client):
    """One officially documented Market GET, separate from application permissions."""

    def authorize(self, method, path):
        if method == "GET" and path == PREFIX + "token/top-liquidity":
            if not self.api_key or not self.secret_key:
                raise ProviderError(self.provider, "NOT_CONFIGURED")
            return
        raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")


class TradeDiagnosticClient(MassiveClient):
    """Single alternative equity read; no production allowlist change."""

    def authorize(self, method, path):
        if method == "GET" and path == "/v2/last/trade/NVDA":
            if not self.api_key:
                raise ProviderError(self.provider, "NOT_CONFIGURED")
            return
        raise ProviderError(self.provider, "READ_ONLY_OPERATION_REQUIRED")


def denial_hook(secret_values, diagnoses):
    def hook(response):
        if response.status_code != 403:
            return
        response.read()
        body = response.text
        if any(value in body for value in secret_values):
            diagnoses.append({"http": 403, "cause": "PAYLOAD_DISCARDED"})
            return
        try:
            raw = json.loads(body)
            message = str(raw.get("message", raw.get("error", ""))).lower()
            status = raw.get("status")
            diagnoses.append(
                {
                    "http": 403,
                    "business": status if status in {"NOT_AUTHORIZED", "ERROR"} else "OTHER",
                    "cause": "ENTITLEMENT_DENIED"
                    if "entitled" in message or "plan" in message or "subscription" in message
                    else "FORBIDDEN_CAUSE_UNCONFIRMED",
                }
            )
        except (ValueError, TypeError, AttributeError):
            diagnoses.append({"http": 403, "cause": "FORBIDDEN_CAUSE_UNCONFIRMED"})

    return hook


def history_inventory():
    result = []
    for path in sorted((ROOT_DIR / "data").glob("*.db")):
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            item = {"database": str(path.relative_to(ROOT_DIR)), "live_counts": {}}
            for table in [
                "trust_samples",
                "trust_episodes",
                "token_observations",
                "equity_observations",
            ]:
                if table not in tables:
                    item["live_counts"][table] = {"status": "TABLE_ABSENT", "count": 0}
                    continue
                rows = db.execute(
                    f"SELECT ticker, payload FROM {table} WHERE data_mode='LIVE'"
                ).fetchall()
                groups = Counter()
                for ticker, payload in rows:
                    data = json.loads(payload)
                    sample = data.get("sample", data)
                    groups[
                        (
                            ticker,
                            sample.get("regime", "NOT_A_TRUST_SAMPLE"),
                            data.get("evidence_kind", data.get("kind", "OBSERVATION")),
                        )
                    ] += 1
                item["live_counts"][table] = {
                    "count": len(rows),
                    "by_ticker_regime_episode_or_observation_type": [
                        {"ticker": t, "regime": r, "type": k, "count": count}
                        for (t, r, k), count in sorted(groups.items())
                    ],
                }
            result.append(item)
    return result


def main(tag):
    output = ROOT_DIR / f"docs/evidence/CANONICAL_PHASE_2_TRUST_{tag}.json"
    if output.exists():
        raise ValueError("Choose a new evidence tag; existing evidence is immutable")
    settings = Settings(data_mode="LIVE_READ_ONLY")
    configure_logging(settings.log_level, settings.redaction_values())
    path = ROOT_DIR / "data/phase2-trust-remediation-verification.db"
    database = Database(f"sqlite:///{path}")
    database.initialize()
    layer = DataLayer(settings, database)
    layer.clients[0].recv_window = 60000
    pool = PoolDiagnosticClient(
        settings.binance_web3_api_key, settings.binance_web3_secret_key, recv_window=60000
    )
    trade = TradeDiagnosticClient(settings.massive_api_key)
    diagnoses = []
    hook = denial_hook(settings.redaction_values(), diagnoses)
    layer.clients[1].http.event_hooks["response"].append(hook)
    trade.http.event_hooks["response"].append(hook)
    try:
        service = TrustService(layer, database)
        result = service.assess(
            "NVDA", run_id=str(uuid4()), request_id=str(uuid4()), correlation_id=str(uuid4())
        )
        assert service.repository.get(result.assessment_id, "LIVE") == result
        assert service.repository.get(result.assessment_id, "DEMO") is None
        assert not result.transaction_broadcast and not result.execution_ready
        assert not result.llm_authoritative and not result.live_trading_enabled
        pools = []
        for representation in result.representations:
            try:
                rows, received, _ = pool.read(
                    "GET",
                    PREFIX + "token/top-liquidity",
                    {
                        "binanceChainId": representation.chain_id,
                        "tokenContractAddress": representation.contract,
                    },
                )
                pools.append(
                    {
                        "issuer": representation.issuer,
                        "pool_count": len(rows),
                        "received_at": received.isoformat(),
                        "liquidity_usd_present_count": sum(
                            isinstance(row, dict) and row.get("liquidityUsd") is not None
                            for row in rows
                        ),
                        "market_measurement_time": "NOT_DOCUMENTED",
                        "authoritative_token_liquidity": False,
                    }
                )
            except (ProviderError, TypeError):
                pools.append({"issuer": representation.issuer, "status": "UNAVAILABLE"})
        for fetch in [
            lambda: layer.equity.get_latest_quote("NVDA"),
            lambda: trade.read("GET", "/v2/last/trade/NVDA"),
        ]:
            try:
                fetch()
            except ProviderError:
                pass
        articles = layer.equity.get_news("NVDA", max_pages=1)
        news = {
            "count": len(articles),
            "full_history_complete": layer.equity.last_page_complete,
            "earliest_publication": min(
                (a.published_timestamp.isoformat() for a in articles), default=None
            ),
            "latest_publication": max(
                (a.published_timestamp.isoformat() for a in articles), default=None
            ),
            "descending_order_verified": all(
                a.published_timestamp >= b.published_timestamp
                for a, b in zip(articles, articles[1:], strict=False)
            ),
            "source_recency": "UPDATED_HOURLY_NOT_EXHAUSTIVE_MARKET_COVERAGE",
        }
        reads = []
        for client in [*layer.clients, pool, trade]:
            for record in client.evidence:
                reads.append(
                    {
                        "endpoint_tested": record["endpoint"],
                        "http_business_response_status": {
                            "http": record["http_status"],
                            "business": record["business_status"],
                        },
                        "permission_result": "VERIFIED_FOR_THIS_READ"
                        if record["capability_result"] == "PASS"
                        else "UNAVAILABLE",
                        "capability_result": record["capability_result"],
                        "timestamp_utc": record["timestamp"],
                    }
                )
        evidence = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "verification": "ACTUAL_READ_ONLY_PROVIDERS",
            "assessment": result.model_dump(mode="json"),
            "denial_diagnoses": diagnoses,
            "account_plan": "UNKNOWN",
            "alternative_last_trade": "NO_CURRENT_REFERENCE_VERIFIED",
            "pool_diagnostics": pools,
            "news_prefix": news,
            "reads": reads,
            "history_inventory": history_inventory(),
            "persisted": "PASS",
            "mode_isolation": "PASS",
            "calls_to_execution_endpoints": 0,
            "positive_real_classifications": "NOT_AVAILABLE_INSUFFICIENT_EVIDENCE",
        }
        encoded = json.dumps(evidence, indent=2) + "\n"
        assert not any(secret in encoded for secret in settings.redaction_values())
        output.write_text(encoded)
        print(
            json.dumps(
                {
                    "evidence": str(output.relative_to(ROOT_DIR)),
                    "representations": len(result.representations),
                    "classifications": [r.classification for r in result.representations],
                    "denial_diagnoses": diagnoses,
                    "pool_diagnostics": pools,
                    "news_prefix": news,
                }
            )
        )
    finally:
        layer.close()
        pool.close()
        trade.close()
        database.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--tag", choices=["REMEDIATION_LIVE", "REMEDIATION_REVERIFIED"], default="REMEDIATION_LIVE"
    )
    main(parser.parse_args().tag)
