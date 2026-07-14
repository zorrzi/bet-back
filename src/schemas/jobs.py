"""Response schemas for internal job routes. All mirror service result
dataclasses via from_attributes — one field list, not two."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FixtureIngestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fixtures_seen: int
    matches_created: int
    matches_updated: int


class OddsIngestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    events_seen: int
    events_matched: int
    events_unmatched: int
    matches_autocreated: int
    snapshots_inserted: int
    captured_at: datetime


class ResultsIngestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    events_seen: int
    results_applied: int
    events_unmatched: int


class ClosingMarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    matches_processed: int
    snapshots_marked: int


class HistoryImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rows_seen: int
    matches_created: int
    results_updated: int
    snapshots_inserted: int
