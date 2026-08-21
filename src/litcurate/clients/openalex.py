"""OpenAlex semantic search client."""

from __future__ import annotations

import time
from typing import Any

import httpx

from litcurate.env import get_env

BASE_URL = "https://api.openalex.org/works"
SEMANTIC_SEARCH_MAX_RESULTS = 50


class OpenAlexRequestError(RuntimeError):
    """Raised when an OpenAlex HTTP request fails after retries."""


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Rebuild plain-text abstract from OpenAlex inverted index."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for idx in idxs:
            positions[idx] = word
    if not positions:
        return None
    return " ".join(positions[idx] for idx in sorted(positions))


def build_filter(
    *,
    year_min: int | None = None,
    year_max: int | None = None,
    extra_filter: str | None = None,
    is_oa: bool | None = None,
    full_papers_only: bool = True,
) -> str | None:
    """Build OpenAlex filter string from config options.

    When ``full_papers_only`` is true, document-quality rules are applied at merge
    time because semantic search rejects or times out on many work filters.
    """
    del full_papers_only
    parts: list[str] = []
    if extra_filter:
        parts.append(extra_filter.strip())
    if year_min is not None:
        parts.append(f"publication_year:>{year_min - 1}")
    if year_max is not None:
        parts.append(f"publication_year:<{year_max + 1}")
    if is_oa is True:
        parts.append("is_oa:true")
    return ",".join(parts) if parts else None


def _request_with_retries(
    client: httpx.Client,
    params: dict[str, Any],
    *,
    max_retries: int = 8,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.get(BASE_URL, params=params)
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPError) as exc:
            last_error = exc
            time.sleep(min(60.0, 2**attempt))
            continue
        if response.status_code == 200:
            return response.json()
        if response.status_code in {429, 502, 503, 504} or response.status_code >= 500:
            last_error = OpenAlexRequestError(
                f"OpenAlex API error {response.status_code}: {response.text[:500]}"
            )
            time.sleep(min(60.0, 2**attempt))
            continue
        raise OpenAlexRequestError(
            f"OpenAlex API error {response.status_code}: {response.text[:500]}"
        )
    detail = f": {last_error}" if last_error else ""
    raise OpenAlexRequestError(
        f"OpenAlex request failed after {max_retries} retries{detail}"
    )


def fetch_works_for_query(
    query: str,
    *,
    api_key: str | None = None,
    mailto: str | None = None,
    max_results: int = 50,
    per_page: int = 50,
    extra_filter: str | None = None,
    request_delay_seconds: float = 0.1,
) -> list[dict[str, Any]]:
    """
    Fetch semantically relevant works for one query.

    OpenAlex semantic search is capped at 50 results per query.
    Each returned work dict includes `_relevance_rank` (1 = best match).
    """
    max_results = min(max_results, SEMANTIC_SEARCH_MAX_RESULTS)
    per_page = min(per_page, SEMANTIC_SEARCH_MAX_RESULTS)

    api_key = api_key or get_env("OPENALEX_API_KEY")
    mailto = mailto or get_env("OPENALEX_EMAIL") or get_env("OPENALEX_MAILTO")

    works: list[dict[str, Any]] = []
    page = 1
    rank = 0

    with httpx.Client(timeout=120.0) as client:
        while len(works) < max_results:
            params: dict[str, Any] = {
                "search.semantic": query,
                "per_page": min(per_page, max_results - len(works)),
                "page": page,
            }
            if api_key:
                params["api_key"] = api_key
            if mailto:
                params["mailto"] = mailto
            if extra_filter:
                params["filter"] = extra_filter

            data = _request_with_retries(client, params)
            results = data.get("results") or []
            if not results:
                break

            for work in results:
                rank += 1
                enriched = dict(work)
                enriched["_relevance_rank"] = rank
                works.append(enriched)

            if len(results) < per_page:
                break
            page += 1
            time.sleep(request_delay_seconds)

    return works[:max_results]
