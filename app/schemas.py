from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Level(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ---- auth ----
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["prod-server-1"])


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    revoked: bool
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    key: str  # shown once, never retrievable again


# ---- logs ----
class LogIn(BaseModel):
    source: str = Field(min_length=1, max_length=100, examples=["nginx-1"])
    level: Level
    message: str = Field(min_length=1, max_length=10_000)
    timestamp: datetime | None = None


class LogBatchIn(BaseModel):
    logs: list[LogIn] = Field(min_length=1, max_length=500)


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    level: str
    message: str
    timestamp: datetime


class IngestResult(BaseModel):
    ingested: int


class StatsOut(BaseModel):
    total: int
    by_level: dict[str, int]
    by_source: dict[str, int]


# ---- incidents ----
class PatternOut(BaseModel):
    fingerprint: str
    template: str
    count: int
    levels: dict[str, int]
    sources: list[str]
    first_seen: datetime | None
    last_seen: datetime | None
    examples: list[str]


class AnalyzeIn(BaseModel):
    fingerprint: str = Field(min_length=8, max_length=32)
    hours: int = Field(24, ge=1, le=720)


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fingerprint: str
    title: str
    severity: str
    status: str
    summary: str
    root_cause: str
    recommended_fixes: list[str]
    affected_sources: list[str]
    log_count: int
    first_seen: datetime
    last_seen: datetime
    analysis_source: str
    analysis_model: str | None
    created_at: datetime
    analyzed_at: datetime


class IncidentUpdate(BaseModel):
    status: Literal["open", "resolved"]


# ---- dashboard ----
class TimeseriesPoint(BaseModel):
    start: datetime
    total: int
    errors: int


class TimeseriesOut(BaseModel):
    hours: int
    bucket_seconds: int
    points: list[TimeseriesPoint]
