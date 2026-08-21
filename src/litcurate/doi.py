"""DOI normalization helpers."""

from __future__ import annotations

import hashlib
import re


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    value = doi.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    return value or None


def paper_id_from_doi(doi: str | None, title: str | None = None) -> str:
    normalized = normalize_doi(doi)
    if normalized:
        return normalized.replace("/", "_")
    digest = hashlib.sha256((title or "unknown").encode()).hexdigest()[:16]
    return f"title_{digest}"
