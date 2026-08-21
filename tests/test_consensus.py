"""Tests for Consensus API response normalization."""

import json

from litcurate.clients.consensus import (
    extract_papers_from_response,
    normalize_consensus_paper,
    paper_dedupe_key,
)

SAMPLE_RESPONSE = {
    "results": [
        {
            "abstract": "We report equations of state...",
            "authors": ["N. Guignot", "D. Andrault"],
            "doi": "10.1016/j.pepi.2003.09.014",
            "journal_name": "Physics of the Earth and Planetary Interiors",
            "pages": "107-128",
            "publish_year": 2004,
            "title": "Equations of state of Na–K–Al host phases",
            "url": "https://consensus.app/papers/example",
            "volume": "143",
            "citation_count": 77,
            "takeaway": "CF and NAL phases are less dense than pyrolite.",
            "publisher_name": "Elsevier",
            "study_type": "bench experiment",
        }
    ],
    "page": 0,
    "is_end": False,
}


def test_extract_papers_from_results_key() -> None:
    papers = extract_papers_from_response(SAMPLE_RESPONSE)
    assert len(papers) == 1
    assert papers[0]["doi"].startswith("10.1016")


def test_normalize_maps_publish_year_and_journal() -> None:
    paper = normalize_consensus_paper(SAMPLE_RESPONSE["results"][0])
    assert paper["year"] == 2004
    assert paper["journal"] == "Physics of the Earth and Planetary Interiors"
    assert paper["study_type"] == "bench experiment"
    assert paper["publisher_name"] == "Elsevier"
    assert json.loads(paper["authors_json"]) == ["N. Guignot", "D. Andrault"]
    raw = json.loads(paper["consensus_raw_json"])
    assert raw["takeaway"] == "CF and NAL phases are less dense than pyrolite."


def test_normalize_handles_missing_doi_and_none_abstract() -> None:
    paper = normalize_consensus_paper(
        {
            "title": "Primary experimental study of target materials",
            "doi": "",
            "abstract": "None",
            "publish_year": 2004,
        }
    )
    assert paper["doi"] is None
    assert paper["abstract"] is None
    assert paper_dedupe_key({"title": paper["title"], "doi": ""}) == paper["title"].lower()
