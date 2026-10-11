"""Display-only historical equity observations, never a live reference or Trust input."""

from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from app.models.data import DataModel, EquityObservation

START = datetime(2026, 10, 5, tzinfo=UTC)
END = datetime(2026, 10, 10, tzinfo=UTC)


class DisplayPeriod(DataModel):
    period: Literal["1D", "1W"]
    first_bar_at: datetime
    last_bar_at: datetime
    first_close: Decimal
    last_close: Decimal
    change_fraction: Decimal
    bar_count: int


class DisplayHistory(DataModel):
    ticker: Literal["NVDA", "AAPL"]
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    source: Literal["ALPACA"] = "ALPACA"
    feed: Literal["sip"] = "sip"
    currency: Literal["USD"] = "USD"
    interval: Literal["5minute"] = "5minute"
    timezone: Literal["America/New_York"] = "America/New_York"
    session: Literal["REGULAR"] = "REGULAR"
    requested_start: datetime = START
    requested_end_exclusive: datetime = END
    captured_at: datetime | None = None
    observations: list[EquityObservation] = Field(default_factory=list, max_length=390)
    limitations: list[str] = Field(
        default_factory=lambda: [
            "Historical bars, not live quotes or an official closing reference.",
            "Raw unadjusted USD prices; historical revision as-of is unverified.",
            "Display only; excluded from Trust evidence, execution and scenario calculations.",
        ]
    )
    production_reference_eligible: Literal[False] = False
    periods: list[DisplayPeriod] = Field(default_factory=list)

    @model_validator(mode="after")
    def history_only(self):
        if self.requested_start != START or self.requested_end_exclusive != END:
            raise ValueError("Fixed display window required")
        if bool(self.observations) != (self.status == "AVAILABLE"):
            raise ValueError("Availability must match observations")
        previous = None
        for row in self.observations:
            at = row.source_timestamp
            if at is None or row.close is None:
                raise ValueError("Observed bar timestamp and close required")
            local = at.astimezone(ZoneInfo(self.timezone))
            if (
                row.source != "ALPACA"
                or row.data_mode != "LIVE"
                or row.data_quality != "HISTORICAL"
                or row.kind != "BAR"
                or row.ticker != self.ticker
                or row.interval != self.interval
                or row.feed != self.feed
                or row.adjusted is not False
                or not START <= at < END
                or at.second != 0
                or at.minute % 5
                or local.weekday() > 4
                or not time(9, 30) <= local.time() < time(16)
                or previous is not None
                and at <= previous
                or self.captured_at is None
                or row.ingestion_timestamp > self.captured_at
            ):
                raise ValueError("Historical identity/session/provenance mismatch")
            previous = at
        # Display arithmetic only. Always recompute from validated observations,
        # never accept a supplied movement metric or use it as a Trust reference.
        periods = []
        if self.observations:
            last_day = self.observations[-1].source_timestamp.date()
            windows = {
                "1D": [r for r in self.observations if r.source_timestamp.date() == last_day],
                "1W": self.observations,
            }
            for period, rows in windows.items():
                first, last = rows[0], rows[-1]
                periods.append(
                    DisplayPeriod(
                        period=period,
                        first_bar_at=first.source_timestamp,
                        last_bar_at=last.source_timestamp,
                        first_close=first.close,
                        last_close=last.close,
                        change_fraction=(last.close - first.close) / first.close,
                        bar_count=len(rows),
                    )
                )
        object.__setattr__(self, "periods", periods)
        return self
