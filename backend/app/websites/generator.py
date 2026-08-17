"""Claude-backed multi-page website drafting + real file rendering (Phase
8, Developer Studio).

Follows the exact honesty contract established by Document generation:
the user's prompt is persisted before any Claude call is attempted, and
if Claude isn't configured (or the call fails, or its response can't be
parsed into real pages) the website is recorded as failed with the real
error — never a fabricated page, never a silently dropped request.

"3D Website" is not a separate module or provider: it is style="3d" on
this exact same pipeline, which asks Claude for a real, working Three.js
scene (see _SYSTEM_PROMPT) instead of a second, duplicate code path.
"""
import json
import re
import uuid

from sqlalchemy.orm import Session

from app.database.base import utcnow
from app.integrations.claude.base import ClaudeProvider
from app.integrations.claude.errors import ProviderRequestError
from app.integrations.claude.utils import complete
from app.integrations.storage.base import StorageProvider
from app.integrations.storage.errors import StorageError
from app.models.history import HistoryEntry, HistoryEntryStatus, HistoryEntryType
from app.models.project import Project
from app.models.user import User
from app.models.website import Website, WebsiteStatus

_SYSTEM_PROMPT = """You are the Website Generation engine of Shadow AI. \
The user describes a website and gives you an exact, ordered list of \
pages with the filename each page must use for internal navigation \
links.

Respond with ONLY a single JSON object (no markdown code fences, no \
commentary before or after it) in this exact shape:

{"pages": ["<complete HTML for page 1>", "<complete HTML for page 2>", ...]}

Return exactly one HTML string per requested page, in the exact order \
requested. Rules for each page's HTML:
- A complete, valid HTML5 document: <!DOCTYPE html>, <html>, <head> with \
a <title> and a <style> block containing all CSS for that page (no \
external stylesheet links), <body> with the real page content.
- Every page must include a <nav> that links to every other page using \
exactly the filenames given to you for each page (e.g. <a \
href="about.html">About</a>) — never invent different filenames.
- Write real, finished content matching the site's stated purpose and \
style — headings, paragraphs, and structure appropriate to each page. \
Never write placeholder text like "Lorem ipsum" or "Content goes here".
- No external JavaScript or CSS CDN links, EXCEPT when the style is \
"3d": then you may include exactly one \
<script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script> \
tag per page that uses it, plus real, working inline Three.js code (a \
genuinely rendering, animated 3D scene — e.g. a rotating mesh or \
particle field) as part of that page's content, not a placeholder canvas.
- Properly JSON-escape all quotes, backslashes, and newlines inside each \
HTML string so the overall response is valid JSON.

Return ONLY the JSON object described above — nothing else."""

_MAX_NAME_CHARS = 255


def _slugify(name: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or fallback


def _compute_filenames(page_names: list[str]) -> list[str]:
    filenames: list[str] = []
    used: set[str] = set()
    for i, name in enumerate(page_names):
        if i == 0:
            filename = "index.html"
        else:
            slug = _slugify(name, f"page-{i + 1}")
            filename = f"{slug}.html"
            suffix = 2
            while filename in used:
                filename = f"{slug}-{suffix}.html"
                suffix += 1
        used.add(filename)
        filenames.append(filename)
    return filenames


def _extract_json_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def _parse_pages(raw: str) -> list[str] | None:
    text = _extract_json_text(raw)
    data = None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except (json.JSONDecodeError, ValueError):
                data = None
    if not isinstance(data, dict):
        return None
    pages = data.get("pages")
    if not isinstance(pages, list):
        return None
    htmls = [p for p in pages if isinstance(p, str) and p.strip()]
    return htmls or None


def _record_failed_website(
    db: Session, user: User, project: Project | None, name: str, prompt: str, style: str, error_detail: str
) -> Website:
    website = Website(
        user_id=user.id,
        project_id=project.id if project else None,
        name=name[:_MAX_NAME_CHARS],
        prompt=prompt,
        style=style,
        status=WebsiteStatus.failed,
        error=error_detail,
        pages=[],
    )
    db.add(website)
    _log_history(db, user, project, name, HistoryEntryStatus.failed)
    db.commit()
    db.refresh(website)
    return website


def record_unavailable_website(
    db: Session, user: User, project: Project | None, name: str, prompt: str, style: str, error_detail: str
) -> Website:
    """Provider couldn't even be constructed — persist the request anyway
    so it isn't lost, exactly like record_unavailable_document does."""
    return _record_failed_website(db, user, project, name, prompt, style, error_detail)


async def generate_website(
    db: Session,
    user: User,
    project: Project | None,
    claude_provider: ClaudeProvider,
    storage_provider: StorageProvider,
    name: str,
    prompt: str,
    style: str,
    page_names: list[str],
) -> Website:
    filenames = _compute_filenames(page_names)
    page_lines = "\n".join(f'- "{n}" -> {f}' for n, f in zip(page_names, filenames))
    combined_prompt = (
        f"Website name: {name}\nStyle: {style}\nDescription: {prompt}\n\n"
        f"Pages to generate, in this exact order, with the exact filename "
        f"each page must use for internal navigation links:\n{page_lines}"
    )

    try:
        raw = await complete(claude_provider, combined_prompt, _SYSTEM_PROMPT)
    except ProviderRequestError as exc:
        return _record_failed_website(db, user, project, name, prompt, style, str(exc))

    htmls = _parse_pages(raw)
    if not htmls:
        return _record_failed_website(
            db,
            user,
            project,
            name,
            prompt,
            style,
            "The AI provider returned an unexpected response format. Please try again.",
        )

    website_id = uuid.uuid4()
    stored_pages: list[dict] = []
    # Best-effort: if Claude returned fewer pages than requested, still
    # store the real ones it did produce rather than discarding a
    # genuine, non-fabricated partial result.
    for page_name, filename, html in zip(page_names, filenames, htmls):
        try:
            stored = storage_provider.write(
                "websites", str(user.id), f"{website_id}__{filename}", html.encode("utf-8")
            )
        except StorageError as exc:
            return _record_failed_website(db, user, project, name, prompt, style, str(exc))
        stored_pages.append(
            {"name": page_name, "path": filename, "storage_ref": stored.ref, "size_bytes": stored.size_bytes}
        )

    website = Website(
        id=website_id,
        user_id=user.id,
        project_id=project.id if project else None,
        name=name[:_MAX_NAME_CHARS],
        prompt=prompt,
        style=style,
        status=WebsiteStatus.completed,
        pages=stored_pages,
    )
    db.add(website)
    _log_history(db, user, project, name, HistoryEntryStatus.completed)
    db.commit()
    db.refresh(website)
    return website


def _log_history(
    db: Session, user: User, project: Project | None, name: str, status: HistoryEntryStatus
) -> None:
    db.add(
        HistoryEntry(
            user_id=user.id,
            project_id=project.id if project else None,
            type=HistoryEntryType.website,
            status=status,
            title=f"Website: {name}",
            completed_at=utcnow() if status == HistoryEntryStatus.completed else None,
        )
    )
