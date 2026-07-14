"""football-data.co.uk historical results provider (ADR-0005).

Free CSVs with final scores and Pinnacle CLOSING 1X2 odds (PSCH/PSCD/PSCA)
— Brazil Serie A back to 2012, refreshed during the season. This is the
calibration corpus for the goal model and the closing-line source for
backtests. Kickoff times in the file are UK-local; we store them as UTC,
an accepted approximation for training weights (never for live decisions).
"""

import csv
import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HistoricalMatch:
    season: str
    kickoff_utc: datetime
    home_team_name: str
    away_team_name: str
    home_goals: int
    away_goals: int
    # Pinnacle closing 1X2 odds; None when the file has no quote
    closing_home: Decimal | None
    closing_draw: Decimal | None
    closing_away: Decimal | None


def _decimal_or_none(value: str) -> Decimal | None:
    value = value.strip()
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


class FootballDataCoUkProvider:
    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    @retry(reraise=True, stop=stop_after_attempt(4), wait=wait_exponential(min=1, max=30))
    def _download(self, csv_url: str) -> str:
        response = httpx.get(csv_url, timeout=self._timeout, follow_redirects=True)
        response.raise_for_status()
        return response.content.decode("utf-8-sig")

    def fetch_history(self, csv_url: str) -> list[HistoricalMatch]:
        text = self._download(csv_url)
        matches = [
            match
            for row in csv.DictReader(io.StringIO(text))
            if (match := self._parse_row(row)) is not None
        ]
        logger.info(
            "football_data.history_fetched",
            extra={"url": csv_url, "rows": len(matches)},
        )
        return matches

    def _parse_row(self, row: dict[str, str]) -> HistoricalMatch | None:
        try:
            date_text = row["Date"].strip()
            time_text = (row.get("Time") or "00:00").strip() or "00:00"
            kickoff = datetime.strptime(f"{date_text} {time_text}", "%d/%m/%Y %H:%M").replace(
                tzinfo=UTC
            )
            return HistoricalMatch(
                season=row["Season"].strip(),
                kickoff_utc=kickoff,
                home_team_name=row["Home"].strip(),
                away_team_name=row["Away"].strip(),
                home_goals=int(row["HG"]),
                away_goals=int(row["AG"]),
                closing_home=_decimal_or_none(row.get("PSCH", "")),
                closing_draw=_decimal_or_none(row.get("PSCD", "")),
                closing_away=_decimal_or_none(row.get("PSCA", "")),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("football_data.row_parse_failed", extra={"row": str(row)[:200]})
            return None
