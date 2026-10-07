"""Synthetic coverage boundaries; captured provider evidence is tested separately."""

from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from app.clients.common import ProviderError
from app.clients.massive import MassiveClient
from app.providers.massive import MassiveProvider
from app.services.trust_evidence import NewsAlignmentService
from backend.tests.unit.test_trust import NOW, news_event


def align(articles, *, prefix_start=None, complete=False, **changes):
    return NewsAlignmentService().evaluate(
        articles,
        ticker="NVDA",
        company="Nvidia",
        deviation=Decimal("0.1"),
        at=NOW,
        mode="DEMO",
        complete=complete,
        prefix_start=prefix_start,
        **changes,
    )


@pytest.mark.parametrize(
    "headline,state",
    [
        ("Nvidia announces a meeting", "RELEVANT_NEWS"),
        ("Nvidia raises guidance", "CORROBORATING"),
        ("Nvidia cuts guidance", "CONFLICTING"),
    ],
)
def test_descending_prefix_covers_window_preserving_partial_history(headline, state):
    old = news_event(provider_identifier="old", published_timestamp=NOW - timedelta(days=1))
    result = align([news_event(headline), old], prefix_start=old.published_timestamp)
    assert result.state == state and result.coverage == "COMPLETE_REQUESTED_WINDOW"
    assert "BOUNDED_NEWS_HISTORY" in result.reason_codes
    assert "DESCENDING_PREFIX_COVERS_REQUESTED_WINDOW" in result.reason_codes
    assert not result.absence_proves_no_information and not result.provider_llm_sentiment_used


@pytest.mark.parametrize(
    "mutation",
    [
        "equal_boundary",
        "too_recent",
        "unordered",
        "future_seen",
        "wrong_mode",
        "wrong_source",
        "wrong_ticker",
        "false_bound",
    ],
)
def test_insufficient_or_untrusted_prefix_remains_partial(mutation):
    recent = news_event()
    old = news_event(provider_identifier="old", published_timestamp=NOW - timedelta(days=1))
    if mutation == "equal_boundary":
        old = old.model_copy(update={"published_timestamp": NOW - timedelta(hours=1)})
    if mutation == "too_recent":
        old = old.model_copy(update={"published_timestamp": NOW - timedelta(minutes=30)})
    if mutation == "future_seen":
        old = old.model_copy(update={"ingestion_timestamp": NOW + timedelta(seconds=1)})
    if mutation == "wrong_mode":
        old = old.model_copy(update={"data_mode": "LIVE", "data_quality": "HISTORICAL"})
    if mutation == "wrong_source":
        old = old.model_copy(update={"source": "UNKNOWN"})
    if mutation == "wrong_ticker":
        old = old.model_copy(update={"ticker": "AAPL"})
    events = [old, recent] if mutation == "unordered" else [recent, old]
    prefix = NOW - timedelta(days=2) if mutation == "false_bound" else old.published_timestamp
    result = align(events, prefix_start=prefix)
    assert result.coverage == "PARTIAL" and result.state == "PARTIAL"


def test_no_relevant_news_is_scoped_not_proof_of_no_information():
    old = news_event(published_timestamp=NOW - timedelta(days=1))
    result = align([old], prefix_start=old.published_timestamp)
    assert result.state == "NO_RELEVANT_NEWS" and result.article_ids == []
    assert not result.absence_proves_no_information
    assert align([], prefix_start=old.published_timestamp).coverage == "PARTIAL"
    assert (
        align([old], prefix_start=old.published_timestamp, unavailable=True).state == "UNAVAILABLE"
    )


def test_prefix_must_cover_entire_observed_move_plus_hour():
    old = news_event(published_timestamp=NOW - timedelta(minutes=65))
    assert (
        align([old], prefix_start=old.published_timestamp).coverage == "COMPLETE_REQUESTED_WINDOW"
    )
    assert (
        align(
            [old], prefix_start=old.published_timestamp, move_start=NOW - timedelta(minutes=15)
        ).coverage
        == "PARTIAL"
    )


def test_provider_only_certifies_unbounded_latest_ordered_prefix_and_resets_after_failure():
    rows = [
        {
            "id": str(i),
            "title": "Nvidia announces a meeting",
            "publisher": {"name": "Synthetic"},
            "tickers": ["NVDA"],
            "article_url": "https://example.test/news",
            "published_utc": (NOW - timedelta(hours=i + 1)).isoformat(),
        }
        for i in range(2)
    ]
    status = 200

    def handler(_):
        return httpx.Response(
            status,
            json={
                "status": "OK",
                "results": rows,
                "next_url": "https://api.massive.com/v2/reference/news?cursor=x",
            },
        )

    provider = MassiveProvider(
        MassiveClient(
            SecretStr("synthetic-massive"),
            http=httpx.Client(transport=httpx.MockTransport(handler)),
            min_interval=0,
            clock=lambda: NOW,
        )
    )
    provider.get_news("NVDA", max_pages=1)
    assert not provider.last_page_complete and provider.news_prefix_start == NOW - timedelta(
        hours=2
    )
    provider.get_news("NVDA", before=NOW, max_pages=1)
    assert provider.news_prefix_start is None
    provider.client.cache.clear()
    rows.reverse()
    provider.get_news("NVDA", max_pages=1)
    assert provider.news_prefix_start is None
    provider.client.cache.clear()
    status = 403
    with pytest.raises(ProviderError):
        provider.get_news("NVDA", max_pages=1)
    assert provider.news_prefix_start is None
