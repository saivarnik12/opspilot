from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import LogEntry, User
from app.schemas import (
    IngestResult,
    Level,
    LogBatchIn,
    LogIn,
    LogOut,
    StatsOut,
    TimeseriesOut,
    TimeseriesPoint,
)

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


def _to_model(item: LogIn, user_id: int) -> LogEntry:
    entry = LogEntry(
        user_id=user_id, source=item.source, level=item.level.value, message=item.message
    )
    if item.timestamp is not None:
        entry.timestamp = item.timestamp
    return entry


@router.post("", response_model=LogOut, status_code=201)
def ingest_one(
    payload: LogIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    entry = _to_model(payload, user.id)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/batch", response_model=IngestResult, status_code=201)
def ingest_batch(
    payload: LogBatchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    db.add_all([_to_model(item, user.id) for item in payload.logs])
    db.commit()
    return IngestResult(ingested=len(payload.logs))


@router.get("", response_model=list[LogOut])
def list_logs(
    response: Response,
    level: Level | None = None,
    source: str | None = None,
    q: str | None = Query(None, max_length=200, description="Case-insensitive text search in the message"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List logs, newest event first (by log timestamp, so late-arriving logs sort correctly). The total number of matches is in the X-Total-Count header."""
    conditions = [LogEntry.user_id == user.id]
    if level:
        conditions.append(LogEntry.level == level.value)
    if source:
        conditions.append(LogEntry.source == source)
    if q:
        conditions.append(LogEntry.message.icontains(q, autoescape=True))
    response.headers["X-Total-Count"] = str(
        db.scalar(select(func.count(LogEntry.id)).where(*conditions)) or 0
    )
    stmt = select(LogEntry).where(*conditions).order_by(LogEntry.timestamp.desc(), LogEntry.id.desc())
    return db.scalars(stmt.limit(limit).offset(offset)).all()


TIMESERIES_BUCKETS = 48
TIMESERIES_MAX_ROWS = 100_000


@router.get("/timeseries", response_model=TimeseriesOut)
def timeseries(
    hours: int = Query(24, ge=1, le=168),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Log volume and error count (ERROR + CRITICAL) per time bucket, zero-filled."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    step = timedelta(hours=hours) / TIMESERIES_BUCKETS
    rows = db.execute(
        select(LogEntry.timestamp, LogEntry.level)
        .where(LogEntry.user_id == user.id, LogEntry.timestamp >= start)
        .limit(TIMESERIES_MAX_ROWS)
    ).all()
    totals = [0] * TIMESERIES_BUCKETS
    errors = [0] * TIMESERIES_BUCKETS
    for ts, level in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        i = min(int((ts - start) / step), TIMESERIES_BUCKETS - 1)
        if i < 0:
            continue
        totals[i] += 1
        if level in ("ERROR", "CRITICAL"):
            errors[i] += 1
    points = [
        TimeseriesPoint(start=start + step * i, total=totals[i], errors=errors[i])
        for i in range(TIMESERIES_BUCKETS)
    ]
    return TimeseriesOut(hours=hours, bucket_seconds=int(step.total_seconds()), points=points)


@router.get("/stats", response_model=StatsOut)
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mine = LogEntry.user_id == user.id
    total = db.scalar(select(func.count(LogEntry.id)).where(mine)) or 0
    by_level = dict(
        db.execute(select(LogEntry.level, func.count()).where(mine).group_by(LogEntry.level)).all()
    )
    by_source = dict(
        db.execute(select(LogEntry.source, func.count()).where(mine).group_by(LogEntry.source)).all()
    )
    return StatsOut(total=total, by_level=by_level, by_source=by_source)
