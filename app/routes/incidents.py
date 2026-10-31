from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.analyzers import Analyzer, get_analyzer
from app.analysis.patterns import Pattern, build_patterns
from app.db import get_db
from app.deps import get_current_user
from app.models import Incident, LogEntry, User
from app.schemas import AnalyzeIn, IncidentOut, IncidentUpdate, PatternOut

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])

ERROR_LEVELS = ("ERROR", "CRITICAL")
MAX_ROWS = 5000  # safety cap per analysis window


def _patterns(db: Session, user_id: int, hours: int, min_count: int = 1) -> list[Pattern]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows = db.scalars(
        select(LogEntry)
        .where(LogEntry.user_id == user_id, LogEntry.level.in_(ERROR_LEVELS), LogEntry.timestamp >= cutoff)
        .order_by(LogEntry.id.desc())
        .limit(MAX_ROWS)
    ).all()
    return build_patterns(rows, min_count=min_count)


@router.get("/patterns", response_model=list[PatternOut])
def list_patterns(
    hours: int = Query(24, ge=1, le=720),
    min_count: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Group recent ERROR/CRITICAL logs into recurring patterns (no AI involved)."""
    return [PatternOut(**vars(p)) for p in _patterns(db, user.id, hours, min_count)[:limit]]


@router.post("/analyze", response_model=IncidentOut, status_code=201)
def analyze(
    payload: AnalyzeIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    analyzer: Analyzer = Depends(get_analyzer),
):
    """Analyze one pattern and create (or refresh) an incident for it."""
    pattern = next((p for p in _patterns(db, user.id, payload.hours) if p.fingerprint == payload.fingerprint), None)
    if pattern is None:
        raise HTTPException(404, "No matching error pattern in that time window")

    result = analyzer.analyze(pattern)
    incident = db.scalar(
        select(Incident).where(
            Incident.user_id == user.id, Incident.fingerprint == pattern.fingerprint, Incident.status == "open"
        )
    )
    if incident is None:
        incident = Incident(user_id=user.id, fingerprint=pattern.fingerprint)
        db.add(incident)
    else:
        response.status_code = 200  # refreshed existing open incident

    incident.title = result.title
    incident.severity = result.severity
    incident.summary = result.summary
    incident.root_cause = result.root_cause
    incident.recommended_fixes = result.recommended_fixes
    incident.affected_sources = pattern.sources
    incident.log_count = pattern.count
    incident.first_seen = pattern.first_seen
    incident.last_seen = pattern.last_seen
    incident.analysis_source = result.source
    incident.analysis_model = result.model
    incident.analyzed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(incident)
    return incident


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    status: str | None = Query(None, pattern="^(open|resolved)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Incident).where(Incident.user_id == user.id).order_by(Incident.id.desc())
    if status:
        stmt = stmt.where(Incident.status == status)
    return db.scalars(stmt.limit(limit).offset(offset)).all()


def _get_owned(db: Session, user: User, incident_id: int) -> Incident:
    incident = db.scalar(select(Incident).where(Incident.id == incident_id, Incident.user_id == user.id))
    if incident is None:
        raise HTTPException(404, "Incident not found")
    return incident


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_owned(db, user, incident_id)


@router.patch("/{incident_id}", response_model=IncidentOut)
def update_incident(
    incident_id: int,
    payload: IncidentUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    incident = _get_owned(db, user, incident_id)
    incident.status = payload.status
    db.commit()
    db.refresh(incident)
    return incident
