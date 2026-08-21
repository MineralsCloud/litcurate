"""Markdown cleaning helpers and section-stripping aliases."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from litcurate.config import MarkdownCleanConfig

REFERENCE_ALIASES: tuple[str, ...] = (
    "references",
    "reference",
    "bibliography",
    "works cited",
    "literature cited",
    "cited references",
)

ACKNOWLEDGMENT_ALIASES: tuple[str, ...] = (
    "acknowledgments",
    "acknowledgements",
    "acknowledgment",
    "acknowledgement",
)

SUPPLEMENTARY_ALIASES: tuple[str, ...] = (
    "supplementary information",
    "supplementary material",
    "supplementary data",
    "supplementary",
    "supplemental",
    "supporting information",
)

FUNDING_ALIASES: tuple[str, ...] = (
    "funding",
    "financial support",
    "funding information",
    "grant support",
)

# Short plain titles only; long lines are body text and must not be regex-scanned.
_MAX_PLAIN_SECTION_TITLE_LEN = 80

MARKDOWN_HEADER_PATTERN = re.compile(r"^#{1,6}\s+(.+)$", re.IGNORECASE)
UNDERLINE_SUFFIX_PATTERN = re.compile(r"\s*[=_.-]+\s*$")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")

_REFERENCE_ENTRY_PATTERN = re.compile(
    r"^\s*(?:"
    r"-\s+[A-Z\d]"
    r"|\d+\.\s+"
    r"|\[\d+\]"
    r")",
    re.IGNORECASE,
)
_AUTHOR_YEAR_REF_PATTERN = re.compile(
    r"^[A-Z][\w''\-\s,&.]+(?:\(\d{4}[a-z]?\)|et al\.)",
)
_UNDERLINE_ONLY_PATTERN = re.compile(r"^[=_.-]+\s*$")
_PAGE_HEADER_IN_REFS_PATTERN = re.compile(
    r"^\s*(?:"
    r"-?\s*X\s*[-–]\s*\d+"
    r"|#{1,6}\s*X\s*[-–]\s*\d+"
    r")",
    re.IGNORECASE,
)
_RESUME_AFTER_REFS_PATTERN = re.compile(
    r"(?:"
    r"!\["
    r"|^\s*#{1,6}\s+(?:Figure|Table)\b"
    r"|^\s*\*\*(?:Figure|Table)\b"
    r"|^\s*\*\*Figure\s+Captions\*\*"
    r"|^\s*Figure\s+(?:\d|[SB]\d*)"
    r"|^\s*Table\s+(?:\d|[SB]\d*)"
    r"|^\s*\|"
    r")",
    re.IGNORECASE,
)

_STRIP_MODE_REFERENCES = "references"
_STRIP_MODE_PROSE = "prose"


def _normalize_header_title(title: str) -> str:
    cleaned = title.strip()
    cleaned = MARKDOWN_LINK_PATTERN.sub(r"\1", cleaned)
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[#*_:`]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(" .:;-")
    cleaned = re.sub(r"^\d+\.\s+", "", cleaned)
    cleaned = re.sub(r"^\d+\s+", "", cleaned)
    return cleaned


def _matches_strip_alias(title: str, aliases: tuple[str, ...]) -> bool:
    normalized = _normalize_header_title(title)
    if not normalized:
        return False
    for alias in aliases:
        if normalized == alias:
            return True
        if normalized.startswith(f"{alias} "):
            return True
        if normalized.startswith(f"{alias}:"):
            return True
        if normalized.startswith(f"{alias}-"):
            return True
    return False


def _aliases_for_config(cfg: MarkdownCleanConfig) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (immediate_strip_aliases, guarded_strip_aliases)."""
    immediate: list[str] = []
    guarded: list[str] = []
    if cfg.strip_references:
        immediate.extend(REFERENCE_ALIASES)
    if cfg.strip_supplementary:
        guarded.extend(SUPPLEMENTARY_ALIASES)
    if cfg.strip_acknowledgments:
        guarded.extend(ACKNOWLEDGMENT_ALIASES)
    if cfg.strip_funding:
        guarded.extend(FUNDING_ALIASES)
    return tuple(immediate), tuple(guarded)


def _extract_bold_prefix_title(line: str) -> str | None:
    if line.startswith("**"):
        marker = "**"
    elif line.startswith("__"):
        marker = "__"
    else:
        return None

    end = line.find(marker, len(marker))
    if end == -1:
        return None
    return line[len(marker) : end]


def _bold_section_header_title(line: str) -> str | None:
    """Return a section title only for standalone bold header lines."""
    stripped = line.strip()
    title = _extract_bold_prefix_title(stripped)
    if title is None:
        return None

    marker = "**" if stripped.startswith("**") else "__"
    end = stripped.find(marker, len(marker))
    if end == -1:
        return None

    rest = stripped[end + len(marker) :].strip()
    if not rest or rest == ":":
        return title
    return None


def _plain_section_title(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    bold_title = _bold_section_header_title(stripped)
    if bold_title is not None:
        return bold_title

    if "**" in stripped or "__" in stripped:
        return None

    if len(stripped) > _MAX_PLAIN_SECTION_TITLE_LEN:
        return None

    return UNDERLINE_SUFFIX_PATTERN.sub("", stripped)


def _strip_section_title(line: str) -> str | None:
    """Return a section title if the line is a standalone strip-able header."""
    stripped = line.strip()
    if not stripped:
        return None

    header_match = MARKDOWN_HEADER_PATTERN.match(stripped)
    if header_match:
        return header_match.group(1)

    return _plain_section_title(stripped)


def _line_starts_strip_section(line: str, aliases: tuple[str, ...]) -> bool:
    title = _strip_section_title(line)
    if title is None:
        return False
    return _matches_strip_alias(title, aliases)


def line_section_title(line: str) -> str | None:
    """Return a section title if the line starts a new document section."""
    return _strip_section_title(line)


def line_markdown_section_title(line: str) -> str | None:
    """Return a section title for markdown/bold headers only (not plain short lines)."""
    stripped = line.strip()
    if not stripped:
        return None

    header_match = MARKDOWN_HEADER_PATTERN.match(stripped)
    if header_match:
        return header_match.group(1)

    return _bold_section_header_title(stripped)


def normalize_section_title(title: str) -> str:
    return _normalize_header_title(title)


def matches_section_alias(title: str, aliases: tuple[str, ...] | list[str]) -> bool:
    return _matches_strip_alias(title, tuple(aliases))


def _looks_like_reference_line(line: str) -> bool:
    """True for blank lines and bibliography entries inside a References block."""
    stripped = line.strip()
    if not stripped:
        return True
    if _UNDERLINE_ONLY_PATTERN.match(stripped):
        return True
    if _PAGE_HEADER_IN_REFS_PATTERN.match(stripped):
        return True
    if _REFERENCE_ENTRY_PATTERN.match(stripped):
        return True
    return bool(_AUTHOR_YEAR_REF_PATTERN.match(stripped))


def _should_resume_after_references(line: str) -> bool:
    """True when post-bibliography figure/table content resumes."""
    return bool(_RESUME_AFTER_REFS_PATTERN.search(line.strip()))


def _classify_strip_section(
    line: str,
    *,
    immediate_aliases: tuple[str, ...],
    guarded_aliases: tuple[str, ...],
    body_lines: int,
    min_body: int,
) -> str | None:
    """Return strip mode for a back-matter section header, if any."""
    if immediate_aliases and _line_starts_strip_section(line, immediate_aliases):
        return _STRIP_MODE_REFERENCES
    if (
        guarded_aliases
        and body_lines >= min_body
        and _line_starts_strip_section(line, guarded_aliases)
    ):
        return _STRIP_MODE_PROSE
    return None


def clean_markdown(text: str, cfg: MarkdownCleanConfig) -> str:
    """Remove back-matter sections that match configured section-header aliases."""
    immediate_aliases, guarded_aliases = _aliases_for_config(cfg)
    if not immediate_aliases and not guarded_aliases:
        return text.strip() + ("\n" if text.strip() else "")

    lines = text.splitlines()
    output: list[str] = []
    strip_mode: str | None = None
    body_lines = 0
    min_body = cfg.min_body_lines_before_strip

    for line in lines:
        section_kind = _classify_strip_section(
            line,
            immediate_aliases=immediate_aliases,
            guarded_aliases=guarded_aliases,
            body_lines=body_lines,
            min_body=min_body,
        )

        if strip_mode is not None:
            if section_kind is not None:
                strip_mode = section_kind
                continue

            if strip_mode == _STRIP_MODE_REFERENCES:
                if _should_resume_after_references(line):
                    strip_mode = None
                    output.append(line)
                    if line.strip():
                        body_lines += 1
                elif _looks_like_reference_line(line):
                    continue
                continue

            continue

        if section_kind is not None:
            strip_mode = section_kind
            continue

        output.append(line)
        if line.strip():
            body_lines += 1

    cleaned = "\n".join(output).strip()
    return cleaned + ("\n" if cleaned else "")


def markdown_strip_stats(
    raw: str,
    cleaned: str,
    *,
    heavy_strip_fraction: float = 0.5,
) -> dict[str, int | float | bool]:
    """Measure how much content cleaning removed from the source markdown."""
    source_chars = len(raw.strip())
    cleaned_chars = len(cleaned.strip())
    if source_chars == 0:
        strip_fraction = 0.0
    else:
        removed = max(0, source_chars - cleaned_chars)
        strip_fraction = removed / source_chars
    return {
        "source_chars": source_chars,
        "cleaned_chars": cleaned_chars,
        "strip_fraction": round(strip_fraction, 4),
        "heavy_strip": strip_fraction > heavy_strip_fraction,
    }
