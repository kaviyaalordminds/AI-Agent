import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.knowledge_analysis import KnowledgeAnalysisStatus


class DuplicatePairOut(BaseModel):
    path_a: str
    title_a: str
    path_b: str
    title_b: str
    similarity: float
    reason: str


class OutdatedNoteOut(BaseModel):
    path: str
    title: str
    days_since_update: int


class BrokenLinkOut(BaseModel):
    source_path: str
    source_title: str
    target_name: str


class KnowledgeHealthOut(BaseModel):
    note_count: int
    tag_count: int
    link_count: int
    duplicates: list[DuplicatePairOut]
    outdated: list[OutdatedNoteOut]
    broken_links: list[BrokenLinkOut]
    orphan_notes: list[str]
    health_score: int
    gaps_count: int
    updates_count: int


class GraphNodeOut(BaseModel):
    path: str
    title: str
    folder: str
    tags: list[str]


class GraphEdgeOut(BaseModel):
    source: str
    target: str


class KnowledgeGraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class CreateGapAnalysisRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    project_id: uuid.UUID | None = None

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Describe what you want to analyze in a bit more detail.")
        return v


class KnowledgeAnalysisOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    project_name: str | None = None
    query: str
    status: KnowledgeAnalysisStatus
    error: str | None
    existing_summary: str | None
    missing_items: list[str]
    recommended_additions: list[str]
    duplicate_notes: list[str]
    outdated_notes: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}
