"""Deterministic Knowledge Intelligence analysis.

Everything in this module is computed directly from real vault data — no
LLM call, no external service, no seeded/fake numbers. It answers the
"is my knowledge base healthy" questions that don't require world
knowledge or reasoning: duplicate detection (title/content similarity),
staleness, broken links, and orphaned notes. Gap analysis ("what am I
missing for a manufacturing HRMS") does require reasoning about a domain
and lives in gap_analysis.py instead, backed by Claude.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.integrations.obsidian.base import NoteSummary, ObsidianProvider

# Notes here are vault documentation, not user knowledge — excluded from
# analysis for the same reason they're excluded from search (see
# LocalVaultProvider._searchable_note_files).
_EXCLUDED_FOLDER = "00-System"

OUTDATED_THRESHOLD_DAYS = 90
TITLE_DUPLICATE_THRESHOLD = 0.7
CONTENT_DUPLICATE_THRESHOLD = 0.6


@dataclass
class DuplicatePair:
    path_a: str
    title_a: str
    path_b: str
    title_b: str
    similarity: float
    reason: str


@dataclass
class OutdatedNote:
    path: str
    title: str
    days_since_update: int


@dataclass
class BrokenLink:
    source_path: str
    source_title: str
    target_name: str


@dataclass
class GraphNode:
    path: str
    title: str
    folder: str
    tags: list[str]


@dataclass
class GraphEdge:
    source: str
    target: str


@dataclass
class KnowledgeGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@dataclass
class VaultAnalysis:
    note_count: int
    tag_count: int
    link_count: int
    duplicates: list[DuplicatePair] = field(default_factory=list)
    outdated: list[OutdatedNote] = field(default_factory=list)
    broken_links: list[BrokenLink] = field(default_factory=list)
    orphan_notes: list[str] = field(default_factory=list)
    health_score: int = 100


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def _analyzable_notes(provider: ObsidianProvider) -> list[NoteSummary]:
    return [n for n in provider.list_notes() if n.folder.split("/")[0] != _EXCLUDED_FOLDER]


def find_duplicates(notes: list[NoteSummary]) -> list[DuplicatePair]:
    """O(n^2) pairwise comparison — fine for the vault sizes a single user
    accumulates; would need indexing (e.g. LSH/minhash) at real scale."""
    duplicates: list[DuplicatePair] = []
    title_tokens = {n.path: _tokenize(n.title) for n in notes}
    content_tokens = {n.path: _tokenize(n.excerpt) for n in notes}

    for i, note_a in enumerate(notes):
        for note_b in notes[i + 1 :]:
            if note_a.title.strip().lower() == note_b.title.strip().lower() and note_a.title.strip():
                duplicates.append(
                    DuplicatePair(note_a.path, note_a.title, note_b.path, note_b.title, 1.0, "identical title")
                )
                continue

            title_sim = _jaccard(title_tokens[note_a.path], title_tokens[note_b.path])
            if title_sim >= TITLE_DUPLICATE_THRESHOLD:
                duplicates.append(
                    DuplicatePair(note_a.path, note_a.title, note_b.path, note_b.title, round(title_sim, 2), "similar title")
                )
                continue

            content_sim = _jaccard(content_tokens[note_a.path], content_tokens[note_b.path])
            if content_sim >= CONTENT_DUPLICATE_THRESHOLD:
                duplicates.append(
                    DuplicatePair(note_a.path, note_a.title, note_b.path, note_b.title, round(content_sim, 2), "similar content")
                )

    return duplicates


def find_outdated(notes: list[NoteSummary], threshold_days: int = OUTDATED_THRESHOLD_DAYS) -> list[OutdatedNote]:
    now = datetime.now(timezone.utc)
    outdated = []
    for note in notes:
        updated_at = note.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        days = (now - updated_at).days
        if days >= threshold_days:
            outdated.append(OutdatedNote(note.path, note.title, days))
    return sorted(outdated, key=lambda o: o.days_since_update, reverse=True)


def find_broken_links(notes: list[NoteSummary]) -> list[BrokenLink]:
    known_titles = {n.title.strip().lower() for n in notes}
    known_stems = {n.path.rsplit("/", 1)[-1].removesuffix(".md").strip().lower() for n in notes}
    broken = []
    for note in notes:
        for link_target in note.links:
            normalized = link_target.strip().lower()
            if normalized not in known_titles and normalized not in known_stems:
                broken.append(BrokenLink(note.path, note.title, link_target))
    return broken


def find_orphan_notes(notes: list[NoteSummary]) -> list[str]:
    linked_targets: set[str] = set()
    has_outgoing: set[str] = set()
    title_to_path = {n.title.strip().lower(): n.path for n in notes}

    for note in notes:
        if note.links:
            has_outgoing.add(note.path)
        for link_target in note.links:
            target_path = title_to_path.get(link_target.strip().lower())
            if target_path:
                linked_targets.add(target_path)

    return sorted(n.path for n in notes if n.path not in linked_targets and n.path not in has_outgoing)


def compute_health_score(
    note_count: int,
    duplicates: list[DuplicatePair],
    outdated: list[OutdatedNote],
    broken_links: list[BrokenLink],
    orphan_notes: list[str],
) -> int:
    """A simple, fully transparent formula — not a claim of statistical
    rigor, just a real, reproducible signal from real vault data:

        100, minus penalties for each problem category, each capped so no
        single category can tank the score to zero on its own; the
        remainder is scaled by how much of the vault each problem affects.
    """
    if note_count == 0:
        return 100

    duplicate_penalty = min(25, len(duplicates) * 4)
    outdated_ratio = len(outdated) / note_count
    outdated_penalty = min(25, round(outdated_ratio * 50))
    broken_link_penalty = min(25, len(broken_links) * 5)
    orphan_ratio = len(orphan_notes) / note_count
    orphan_penalty = min(15, round(orphan_ratio * 30))

    score = 100 - duplicate_penalty - outdated_penalty - broken_link_penalty - orphan_penalty
    return max(0, score)


def analyze_vault(provider: ObsidianProvider) -> VaultAnalysis:
    notes = _analyzable_notes(provider)
    tag_count = len({tag for n in notes for tag in n.tags})
    link_count = sum(len(n.links) for n in notes)

    duplicates = find_duplicates(notes)
    outdated = find_outdated(notes)
    broken_links = find_broken_links(notes)
    orphan_notes = find_orphan_notes(notes)

    health_score = compute_health_score(len(notes), duplicates, outdated, broken_links, orphan_notes)

    return VaultAnalysis(
        note_count=len(notes),
        tag_count=tag_count,
        link_count=link_count,
        duplicates=duplicates,
        outdated=outdated,
        broken_links=broken_links,
        orphan_notes=orphan_notes,
        health_score=health_score,
    )


def build_knowledge_graph(provider: ObsidianProvider) -> KnowledgeGraph:
    notes = _analyzable_notes(provider)
    title_to_path = {n.title.strip().lower(): n.path for n in notes}

    nodes = [GraphNode(path=n.path, title=n.title, folder=n.folder, tags=n.tags) for n in notes]
    edges: list[GraphEdge] = []
    seen_edges: set[tuple[str, str]] = set()
    for note in notes:
        for link_target in note.links:
            target_path = title_to_path.get(link_target.strip().lower())
            if target_path and target_path != note.path:
                edge_key = tuple(sorted((note.path, target_path)))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    edges.append(GraphEdge(source=note.path, target=target_path))

    return KnowledgeGraph(nodes=nodes, edges=edges)
