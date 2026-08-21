"""PDF discovery and direct network download helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from litcurate.doi import normalize_doi
from litcurate.env import get_env

logger = logging.getLogger(__name__)

HTTP_USER_AGENT = "LitCurate/0.1 (literature curation; contact via UNPAYWALL_EMAIL)"

# Hosts that often allow plain HTTP PDF fetch without a browser session.
DIRECT_HTTP_HOSTS = (
    "arxiv.org",
    "zenodo.org",
    "figshare.com",
    "osti.gov",
    "hdl.handle.net",
    "openreview.net",
    "biorxiv.org",
    "medrxiv.org",
    "chemrxiv.org",
    "osf.io",
    "hal.science",
    "hal.archives-ouvertes.fr",
    "europepmc.org",
    "ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
)

PDF_URL_MARKERS = (
    "/doi/pdf/",
    "/pdf/",
    ".pdf",
    "article-pdf",
    "downloadpdf",
    "download/pdf",
)


@dataclass(frozen=True)
class PdfCandidate:
    url: str
    source: str
    referer: str | None = None


@dataclass
class DownloadOutcome:
    status: str
    source: str | None = None
    error: str | None = None
    pdf_bytes: bytes | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "success" and self.pdf_bytes is not None


def doi_landing_url(doi: str) -> str:
    return f"https://doi.org/{normalize_doi(doi) or doi}"


def url_host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def host_allows_direct_http(url: str) -> bool:
    host = url_host(url)
    return any(host == allowed or host.endswith("." + allowed) for allowed in DIRECT_HTTP_HOSTS)


def looks_like_pdf_url(url: str) -> bool:
    lower = (url or "").lower()
    return any(marker in lower for marker in PDF_URL_MARKERS)


def is_pdf_bytes(body: bytes, content_type: str = "", content_disposition: str = "") -> bool:
    if not body:
        return False
    if body.startswith(b"%PDF"):
        return True
    ct = content_type.lower()
    cd = content_disposition.lower()
    return "application/pdf" in ct or (".pdf" in cd and "filename=" in cd)


def _dedupe_candidates(candidates: list[PdfCandidate]) -> list[PdfCandidate]:
    seen: set[str] = set()
    ordered: list[PdfCandidate] = []
    for candidate in candidates:
        if candidate.url in seen:
            continue
        seen.add(candidate.url)
        ordered.append(candidate)
    return ordered


def unpaywall_candidates(doi: str, email: str) -> list[PdfCandidate]:
    normalized = normalize_doi(doi)
    if not normalized:
        return []
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                f"https://api.unpaywall.org/v2/{normalized}",
                params={"email": email},
            )
        if response.status_code != 200:
            return []
        data = response.json()
    except Exception as exc:
        logger.debug("Unpaywall lookup failed for %s: %s", doi, exc)
        return []

    candidates: list[PdfCandidate] = []
    for key in ("best_oa_location", "first_oa_location"):
        loc = data.get(key) or {}
        pdf_url = loc.get("url_for_pdf") or loc.get("url")
        if pdf_url:
            candidates.append(PdfCandidate(pdf_url, "unpaywall", loc.get("url")))
    return candidates


def openalex_candidates(doi: str, *, oa_only: bool = False) -> tuple[list[PdfCandidate], list[str]]:
    normalized = normalize_doi(doi)
    if not normalized:
        return [], [doi_landing_url(doi)]

    mailto = get_env("OPENALEX_EMAIL") or get_env("OPENALEX_MAILTO") or "litcurate@example.com"
    params = {"filter": f"doi:https://doi.org/{normalized}", "mailto": mailto}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get("https://api.openalex.org/works", params=params)
        if response.status_code != 200:
            return [], [doi_landing_url(doi)]
        results = response.json().get("results") or []
        if not results:
            return [], [doi_landing_url(doi)]
        work = results[0]
    except Exception as exc:
        logger.debug("OpenAlex lookup failed for %s: %s", doi, exc)
        return [], [doi_landing_url(doi)]

    pdf_candidates: list[PdfCandidate] = []
    landing_urls: list[str] = []

    locations: list[dict[str, Any]] = []
    if oa_only:
        if not (work.get("open_access") or {}).get("is_oa"):
            return [], [doi_landing_url(doi)]
        for key in ("best_oa_location",):
            loc = work.get(key)
            if loc:
                locations.append(loc)
        for loc in work.get("locations") or []:
            if loc.get("is_oa"):
                locations.append(loc)
    else:
        for key in ("primary_location", "best_oa_location"):
            loc = work.get(key)
            if loc:
                locations.append(loc)
        locations.extend(work.get("locations") or [])

    for loc in locations:
        pdf_url = loc.get("pdf_url")
        landing = loc.get("landing_page_url")
        if pdf_url:
            pdf_candidates.append(PdfCandidate(pdf_url, "openalex", landing))
        if landing:
            landing_urls.append(landing)

    oa_url = (work.get("open_access") or {}).get("oa_url")
    if oa_url:
        landing_urls.append(oa_url)
        if oa_only and looks_like_pdf_url(oa_url):
            pdf_candidates.append(PdfCandidate(oa_url, "openalex:oa_url", oa_url))

    if not landing_urls:
        landing_urls.append(doi_landing_url(doi))

    return pdf_candidates, landing_urls


def crossref_candidates(doi: str) -> list[PdfCandidate]:
    normalized = normalize_doi(doi)
    if not normalized:
        return []
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"https://api.crossref.org/works/{normalized}")
        if response.status_code != 200:
            return []
        links = response.json().get("message", {}).get("link", [])
    except Exception as exc:
        logger.debug("Crossref lookup failed for %s: %s", doi, exc)
        return []

    candidates: list[PdfCandidate] = []
    for link in links:
        url = link.get("URL")
        if not url or not looks_like_pdf_url(url):
            continue
        candidates.append(PdfCandidate(url, "crossref", doi_landing_url(doi)))
    return candidates


def collect_candidates(
    doi: str,
    *,
    unpaywall_email: str | None,
    oa_only: bool = False,
) -> list[PdfCandidate]:
    """Build an ordered list of PDF URLs reported by metadata services."""
    candidates: list[PdfCandidate] = []

    if unpaywall_email:
        candidates.extend(unpaywall_candidates(doi, unpaywall_email))

    openalex_pdfs, _ = openalex_candidates(doi, oa_only=oa_only)
    candidates.extend(openalex_pdfs)

    if not oa_only:
        candidates.extend(crossref_candidates(doi))

    return _dedupe_candidates(candidates)


def try_http_download(
    client: httpx.Client,
    url: str,
    *,
    referer: str | None = None,
    require_direct_host: bool = False,
) -> bytes | None:
    if require_direct_host and not host_allows_direct_http(url):
        return None

    headers = {
        "User-Agent": HTTP_USER_AGENT,
        "Accept": "application/pdf,application/octet-stream,*/*",
    }
    if referer:
        headers["Referer"] = referer

    try:
        response = client.get(url, headers=headers, follow_redirects=True)
    except Exception as exc:
        logger.debug("HTTP download failed for %s: %s", url, exc)
        return None

    if response.status_code != 200:
        return None

    content_type = response.headers.get("content-type", "")
    content_disposition = response.headers.get("content-disposition", "")
    if is_pdf_bytes(response.content, content_type, content_disposition):
        return response.content
    return None


def download_pdf_bytes(
    doi: str,
    *,
    unpaywall_email: str | None,
    oa_only: bool = False,
) -> DownloadOutcome:
    """Download a PDF from metadata-provided URLs using HTTP only."""
    if not doi:
        return DownloadOutcome(status="failed", error="missing DOI")

    candidates = collect_candidates(
        doi,
        unpaywall_email=unpaywall_email,
        oa_only=oa_only,
    )

    if oa_only and not candidates:
        return DownloadOutcome(status="failed", error="no OA PDF URL found")

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        # Open repositories first — no browser needed.
        for candidate in candidates:
            if not host_allows_direct_http(candidate.url):
                continue
            body = try_http_download(
                client,
                candidate.url,
                referer=candidate.referer or doi_landing_url(doi),
                require_direct_host=True,
            )
            if body:
                return DownloadOutcome(status="success", source=f"direct_http:{candidate.source}", pdf_bytes=body)

        # OA repository URLs first; publisher OA links only when not oa_only.
        for candidate in candidates:
            if host_allows_direct_http(candidate.url):
                continue
            body = try_http_download(
                client,
                candidate.url,
                referer=candidate.referer or doi_landing_url(doi),
            )
            if body:
                return DownloadOutcome(status="success", source=f"http:{candidate.source}", pdf_bytes=body)

    error = "no OA PDF available via HTTP" if oa_only else "no PDF available via HTTP"
    return DownloadOutcome(status="failed", error=error)


def save_pdf(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
