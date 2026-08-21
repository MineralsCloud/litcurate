"""Tests for PDF download helpers."""

import httpx

from litcurate.clients.pdf_download import (
    PdfCandidate,
    collect_candidates,
    host_allows_direct_http,
    is_pdf_bytes,
    looks_like_pdf_url,
    try_http_download,
)


def test_is_pdf_bytes_magic() -> None:
    assert is_pdf_bytes(b"%PDF-1.4\n", "text/html") is True
    assert is_pdf_bytes(b"not a pdf", "text/html") is False


def test_host_allows_direct_http() -> None:
    assert host_allows_direct_http("https://arxiv.org/pdf/1234.pdf") is True
    assert host_allows_direct_http("https://www.nature.com/articles/foo.pdf") is False


def test_looks_like_pdf_url() -> None:
    assert looks_like_pdf_url("https://example.com/doi/pdf/10.1/test") is True
    assert looks_like_pdf_url("https://example.com/article") is False


def test_collect_candidates_returns_pdf_urls() -> None:
    candidates = collect_candidates("10.1038/nature00000", unpaywall_email=None)
    assert isinstance(candidates, list)


def test_collect_candidates_oa_only_skips_crossref(monkeypatch) -> None:
    monkeypatch.setattr(
        "litcurate.clients.pdf_download.crossref_candidates",
        lambda doi: [PdfCandidate("https://publisher.com/pdf", "crossref")],
    )
    monkeypatch.setattr(
        "litcurate.clients.pdf_download.openalex_candidates",
        lambda doi, oa_only=False: ([], ["https://doi.org/10.1038/nature00000"]),
    )
    candidates = collect_candidates("10.1038/nature00000", unpaywall_email=None, oa_only=True)
    assert candidates == []


def test_try_http_download_pdf() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4 test",
        )
    )
    with httpx.Client(transport=transport) as client:
        body = try_http_download(client, "https://arxiv.org/pdf/1234.pdf")
    assert body == b"%PDF-1.4 test"
