"""Versioned published exchange schedule, bounded coverage; not a Trust regime engine."""

import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.clients.common import ProviderError
from app.config import ROOT_DIR
from app.models.data import MarketStatus, utc


class USEquityCalendar:
    def __init__(self, path=ROOT_DIR / "data/calendar/nyse-2026-2028.json", *, mode="LIVE"):
        self.data = json.loads(path.read_text())
        self.zone = ZoneInfo(self.data["timezone"])
        self.mode = mode
        self.start = date.fromisoformat(self.data["coverage_start"])
        self.end = date.fromisoformat(self.data["coverage_end"])
        self.holidays = {date.fromisoformat(d) for d in self.data["holidays"]}
        self.early = {date.fromisoformat(d) for d in self.data["early_closes"]}

    def check(self, day):
        if not self.start <= day <= self.end:
            raise ProviderError("NYSE_CALENDAR", "OUTSIDE_VERIFIED_SCHEDULE")

    def moment(self, day, label):
        return datetime.combine(day, time.fromisoformat(label), self.zone).astimezone(UTC)

    def session(self, day):
        self.check(day)
        if day.weekday() >= 5 or day in self.holidays:
            return None
        return self.moment(day, self.data["regular_open"]), self.moment(
            day, "13:00" if day in self.early else self.data["regular_close"]
        )

    def previous_session(self, at):
        at = utc(at)
        day = at.astimezone(self.zone).date()
        for offset in range(15):
            result = self.session(day - timedelta(days=offset))
            if result and result[1] <= at:
                return result
        raise ProviderError("NYSE_CALENDAR", "PREVIOUS_SESSION_UNAVAILABLE")

    def status(self, at):
        at = utc(at)
        local = at.astimezone(self.zone)
        day = local.date()
        session = self.session(day)
        upcoming = None
        for offset in range(15):
            candidate = self.session(day + timedelta(days=offset))
            if candidate and candidate[0] > at:
                upcoming = candidate
                break
        if upcoming is None:
            raise ProviderError("NYSE_CALENDAR", "NEXT_SESSION_UNAVAILABLE")
        prior = self.previous_session(at)
        closure_days = (
            upcoming[0].astimezone(self.zone).date() - prior[1].astimezone(self.zone).date()
        ).days - 1
        reopening = False
        if session:
            prior_day = self.previous_session(session[0])[1].astimezone(self.zone).date()
            reopening = (day - prior_day).days > 1
            if at < self.moment(day, self.data["premarket_open"]):
                state = "WEEKDAY_OVERNIGHT"
            elif at < session[0]:
                state = "PREMARKET"
            elif at < session[1]:
                state = "REGULAR"
            elif at < self.moment(
                day,
                self.data["early_postmarket_close"]
                if day in self.early
                else self.data["postmarket_close"],
            ):
                state = "POSTMARKET"
            else:
                state = "WEEKDAY_OVERNIGHT"
        else:
            state = "HOLIDAY" if day in self.holidays else "WEEKEND"
        return MarketStatus(
            source="NYSE_PUBLISHED_SCHEDULE",
            provider_identifier=self.data["version"],
            source_timestamp=datetime.fromisoformat(self.data["verified_at"]),
            raw_source_timestamp=self.data["verified_at"],
            timestamp_unit="SCHEDULE",
            ingestion_timestamp=at if self.mode == "DEMO" else datetime.now(UTC),
            data_mode=self.mode,
            data_quality="DEMO" if self.mode == "DEMO" else "HISTORICAL",
            state=state,
            next_open=upcoming[0],
            next_close=session[1] if session and at < session[1] else upcoming[1],
            early_close=day in self.early,
            multi_day_closure=closure_days >= 3,
            reopening=reopening,
            provider_metadata={
                "schedule_version": self.data["version"],
                "evaluated_at": at.isoformat(),
                "schedule_verified_at": self.data["verified_at"],
                "schedule_source": self.data["source"],
                "venue": self.data["venue"],
                "coverage_start": self.data["coverage_start"],
                "coverage_end": self.data["coverage_end"],
                "scheduled_not_exchange_halt_status": True,
            },
        )
