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
    snapshots_inserted: int
    captured_at: datetime


class ClosingMarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    matches_processed: int
    snapshots_marked: int
