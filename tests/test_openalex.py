"""Tests for OpenAlex search normalization."""

import json

from litcurate.clients.literature import (
    extract_papers_from_response,
    normalize_openalex_paper,
    normalize_search_paper,
    paper_dedupe_key,
)

SAMPLE_OPENALEX_RESPONSE = {
    "provider": "openalex",
    "query_id": "q1",
    "query": "example research topic literature search",
    "results": [
        {
            "id": "https://openalex.org/W123",
            "display_name": "Equations of state of Na–K–Al host phases",
            "doi": "https://doi.org/10.1016/j.pepi.2003.09.014",
            "publication_year": 2004,
            "cited_by_count": 77,
            "abstract_inverted_index": {"We": [0], "report": [1], "EoS": [2]},
            "authorships": [
                {"author": {"display_name": "N. Guignot"}},
                {"author": {"display_name": "D. Andrault"}},
            ],
            "primary_location": {
                "source": {
                    "display_name": "Physics of the Earth and Planetary Interiors",
                    "host_organization_name": "Elsevier",
                }
            },
            "open_access": {"is_oa": False},
            "_relevance_rank": 1,
        }
    ],
}


def test_extract_openalex_results() -> None:
    papers = extract_papers_from_response(SAMPLE_OPENALEX_RESPONSE)
    assert len(papers) == 1
    assert papers[0]["display_name"].startswith("Equations of state")


def test_normalize_openalex_paper() -> None:
    paper = normalize_openalex_paper(SAMPLE_OPENALEX_RESPONSE["results"][0])
    assert paper["doi"] == "10.1016/j.pepi.2003.09.014"
    assert paper["year"] == 2004
    assert paper["journal"] == "Physics of the Earth and Planetary Interiors"
    assert paper["search_provider"] == "openalex"
    assert paper["relevance_score"] == 1.0
    assert paper["abstract_source"] == "openalex"
    assert "report EoS" in paper["abstract"]
    assert json.loads(paper["authors_json"]) == ["N. Guignot", "D. Andrault"]


def test_normalize_search_paper_auto_detects_openalex() -> None:
    paper = normalize_search_paper(SAMPLE_OPENALEX_RESPONSE["results"][0])
    assert paper["openalex_id"] == "https://openalex.org/W123"
    assert paper_dedupe_key(SAMPLE_OPENALEX_RESPONSE["results"][0]) == "10.1016/j.pepi.2003.09.014"


def test_build_filter_uses_year_only_for_full_papers_mode() -> None:
    from litcurate.clients.openalex import build_filter

    result = build_filter(year_min=1990, full_papers_only=True)
    assert result == "publication_year:>1989"
    assert "has_doi" not in result
    assert "has_abstract" not in result


def test_build_filter_skips_full_paper_defaults_when_disabled() -> None:
    from litcurate.clients.openalex import build_filter

    result = build_filter(year_min=1990, full_papers_only=False)
    assert result == "publication_year:>1989"


def test_build_filter_year_slice_range() -> None:
    from litcurate.clients.openalex import build_filter

    result = build_filter(year_min=1990, year_max=1999)
    assert result == "publication_year:>1989,publication_year:<2000"


def test_openalex_config_search_year_slices_explicit() -> None:
    from litcurate.config import OpenAlexConfig, YearSliceConfig

    cfg = OpenAlexConfig(
        year_slices=[
            YearSliceConfig(year_min=1990, year_max=1999),
            YearSliceConfig(year_min=2000, year_max=2009),
        ]
    )
    slices = cfg.search_year_slices()
    assert len(slices) == 2
    assert slices[0].year_min == 1990
    assert slices[1].year_max == 2009


def test_openalex_config_search_year_slices_from_legacy_year_min() -> None:
    from litcurate.config import OpenAlexConfig

    cfg = OpenAlexConfig(year_min=1990)
    slices = cfg.search_year_slices()
    assert len(slices) == 1
    assert slices[0].year_min == 1990
    assert slices[0].year_max is None


def test_openalex_config_slice_result_suffix() -> None:
    from litcurate.config import OpenAlexConfig, YearSliceConfig

    cfg = OpenAlexConfig(
        year_slices=[
            YearSliceConfig(year_min=1990, year_max=1999),
            YearSliceConfig(year_min=2020),
        ]
    )
    assert cfg.slice_result_suffix(cfg.year_slices[0]) == "_y1990_1999"
    assert cfg.slice_result_suffix(cfg.year_slices[1]) == "_y2020_up"

    single = OpenAlexConfig(year_min=1990)
    assert single.slice_result_suffix(YearSliceConfig(year_min=1990)) == ""
