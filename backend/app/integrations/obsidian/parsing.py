"""Real (if basic) markdown metadata extraction — no external markdown
library, just the two conventions Obsidian itself relies on: wiki-links
and hashtags."""
import re

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
# A tag is '#' immediately followed by a word/underscore/dash/slash char,
# not preceded by another non-space character (so "a#b" doesn't match) and
# not a markdown heading (heading '#' is always followed by a space).
_TAG_RE = re.compile(r"(?<!\S)#([A-Za-z0-9_/-]+)")
_EXCERPT_LEN = 220


def extract_links(content: str) -> list[str]:
    seen: list[str] = []
    for match in _WIKILINK_RE.findall(content):
        name = match.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def extract_tags(content: str) -> list[str]:
    seen: list[str] = []
    for match in _TAG_RE.findall(content):
        if match not in seen:
            seen.append(match)
    return seen


def derive_title(path: str, content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    # Fall back to the filename without extension.
    return path.rsplit("/", 1)[-1].removesuffix(".md")


def derive_excerpt(content: str) -> str:
    lines = [ln.strip() for ln in content.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= _EXCERPT_LEN:
        return text
    return text[:_EXCERPT_LEN].rstrip() + "…"
