import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.integrations.claude.errors import ProviderNotConfiguredError
from app.integrations.claude.factory import get_claude_provider
from app.integrations.obsidian.factory import get_obsidian_provider
from app.knowledge.gap_analysis import record_unavailable_analysis, run_gap_analysis
from app.knowledge.vault_analysis import analyze_vault, build_knowledge_graph
from app.models.history import HistoryEntry, HistoryEntryType
from app.models.knowledge_analysis import KnowledgeAnalysis
from app.models.project import Project
from app.models.user import User
from app.schemas.knowledge import (
    CreateGapAnalysisRequest,
    KnowledgeAnalysisOut,
    KnowledgeGraphOut,
    KnowledgeHealthOut,
)
from app.security.sessions import get_current_user, require_csrf

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _to_analysis_out(analysis: KnowledgeAnalysis) -> KnowledgeAnalysisOut:
    out = KnowledgeAnalysisOut.model_validate(analysis)
    out.project_name = analysis.project.name if analysis.project else None
    return out


@router.get("/health", response_model=KnowledgeHealthOut)
def knowledge_health(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    provider = get_obsidian_provider(user.id)
    analysis = analyze_vault(provider)

    gaps_count = (
        db.query(KnowledgeAnalysis)
        .filter(
            KnowledgeAnalysis.user_id == user.id,
            KnowledgeAnalysis.status == "completed",
        )
        .count()
    )
    updates_count = (
        db.query(HistoryEntry)
        .filter(HistoryEntry.user_id == user.id, HistoryEntry.type == HistoryEntryType.knowledge_update)
        .count()
    )

    return KnowledgeHealthOut(
        note_count=analysis.note_count,
        tag_count=analysis.tag_count,
        link_count=analysis.link_count,
        duplicates=[d.__dict__ for d in analysis.duplicates],
        outdated=[o.__dict__ for o in analysis.outdated],
        broken_links=[b.__dict__ for b in analysis.broken_links],
        orphan_notes=analysis.orphan_notes,
        health_score=analysis.health_score,
        gaps_count=gaps_count,
        updates_count=updates_count,
    )


@router.get("/graph", response_model=KnowledgeGraphOut)
def knowledge_graph(user: User = Depends(get_current_user)):
    provider = get_obsidian_provider(user.id)
    graph = build_knowledge_graph(provider)
    return KnowledgeGraphOut(
        nodes=[n.__dict__ for n in graph.nodes],
        edges=[e.__dict__ for e in graph.edges],
    )


@router.get("/gaps", response_model=list[KnowledgeAnalysisOut])
def list_gap_analyses(
    project_id: uuid.UUID | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(KnowledgeAnalysis).filter(KnowledgeAnalysis.user_id == user.id)
    if project_id is not None:
        query = query.filter(KnowledgeAnalysis.project_id == project_id)
    analyses = query.order_by(KnowledgeAnalysis.created_at.desc()).all()
    return [_to_analysis_out(a) for a in analyses]


@router.get("/gaps/{analysis_id}", response_model=KnowledgeAnalysisOut)
def get_gap_analysis(
    analysis_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    analysis = (
        db.query(KnowledgeAnalysis)
        .filter(KnowledgeAnalysis.id == analysis_id, KnowledgeAnalysis.user_id == user.id)
        .first()
    )
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found.")
    return _to_analysis_out(analysis)


@router.post("/gaps", response_model=KnowledgeAnalysisOut, status_code=status.HTTP_201_CREATED)
async def create_gap_analysis(
    payload: CreateGapAnalysisRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
):
    project = None
    if payload.project_id is not None:
        project = (
            db.query(Project)
            .filter(Project.id == payload.project_id, Project.user_id == user.id)
            .first()
        )
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    try:
        claude_provider = get_claude_provider()
    except ProviderNotConfiguredError as exc:
        record_unavailable_analysis(db, user, project, payload.query, str(exc))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

    obsidian_provider = get_obsidian_provider(user.id)
    analysis = await run_gap_analysis(db, user, project, obsidian_provider, claude_provider, payload.query)
    return _to_analysis_out(analysis)
