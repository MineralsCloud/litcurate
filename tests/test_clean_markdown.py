"""Tests for markdown cleaning and section aliases."""

from __future__ import annotations

from litcurate.config import MarkdownCleanConfig
from litcurate.markdown_clean import clean_markdown, markdown_strip_stats


def _cfg(**overrides: object) -> MarkdownCleanConfig:
    defaults = {
        "strip_references": True,
        "strip_acknowledgments": True,
        "strip_supplementary": True,
        "strip_funding": True,
    }
    defaults.update(overrides)
    return MarkdownCleanConfig(**defaults)


def _short_doc_cfg() -> MarkdownCleanConfig:
    """Config for compact synthetic fixtures (below default body-line guard)."""
    return _cfg(min_body_lines_before_strip=2)


def test_strips_acknowledgment_singular_header() -> None:
    text = """## Results

Some primary data.

### ACKNOWLEDGMENT

Thanks to everyone.
"""
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "ACKNOWLEDGMENT" not in cleaned
    assert "Thanks to everyone" not in cleaned
    assert "Some primary data." in cleaned


def test_strips_references_header_and_tail() -> None:
    text = """## Discussion

Important finding.

## References

1. Smith et al., Nature (2019).
"""
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "Important finding." in cleaned
    assert "References" not in cleaned
    assert "Smith et al." not in cleaned


def test_keeps_figures_and_tables_after_references_section() -> None:
    """Marker often places figure/table captions after the bibliography."""
    text = """## Discussion

Important finding.

## References

- Smith et al. (2020), Nature.
- Jones, A. (2019), Science.

![](_page_20_Figure_2.jpeg)

Figure 1. Elastic moduli plot.

| Col1 | Col2 |
| --- | --- |
| a | b |

**Table 2.** Moduli values.
"""
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "Important finding." in cleaned
    assert "Smith et al." not in cleaned
    assert "Jones, A." not in cleaned
    assert "![](_page_20_Figure_2.jpeg)" in cleaned
    assert "Figure 1." in cleaned
    assert "| Col1 |" in cleaned
    assert "**Table 2.**" in cleaned


def test_keeps_figures_after_bounded_acknowledgments_and_references() -> None:
    """Acknowledgments must not strip figures/tables that follow the bibliography."""
    text = """## Results

Primary finding.

#### **Acknowledgments**

We thank everyone for support.

327 References Cited

- Smith et al. (2020), Nature.
- Jones, A. (2019), Science.

Figure 3. Pressure-volume relationship.

![](_page_32_Figure_1.jpeg)

Table 1. Compression data.
"""
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "Primary finding." in cleaned
    assert "We thank everyone" not in cleaned
    assert "Smith et al." not in cleaned
    assert "Figure 3." in cleaned
    assert "![](_page_32_Figure_1.jpeg)" in cleaned
    assert "Table 1." in cleaned


def test_strips_references_case_insensitive() -> None:
    text = """## Results

Data here.

## REFERENCES

Smith (2020).
"""
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "Data here." in cleaned
    assert "Smith (2020)." not in cleaned


def test_strips_supplementary_information() -> None:
    body = "\n".join(f"Body paragraph {i} with measured parameters and results." for i in range(45))
    text = f"""## Abstract

{body}

#### SUPPLEMENTARY INFORMATION

Table S1.
"""
    cleaned = clean_markdown(text, _cfg())
    assert "Body paragraph 44" in cleaned
    assert "SUPPLEMENTARY" not in cleaned
    assert "Table S1" not in cleaned


def test_keeps_numbered_citation_list_without_references_header() -> None:
    text = "\n".join(
        [f"Line {i} of body content." for i in range(25)]
        + ["", "<sup>1</sup> D. Andrault, Earth Planet. Sci. Lett. (2001).", "<sup>2</sup> Another ref."]
    )
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "Line 24 of body content." in cleaned
    assert "D. Andrault" in cleaned


def test_keeps_inline_citation_links_in_body() -> None:
    text = """## Introduction

Bridgmanite measurements[1–3] are important.

## Methods

Details here.
"""
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "Bridgmanite measurements[1–3]" in cleaned


def test_plain_references_line_without_hash() -> None:
    text = """## Results

Data here.

References
==========

Smith (2020).
"""
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "Data here." in cleaned
    assert "Smith (2020)." not in cleaned


def test_keeps_inline_bold_acknowledgements_in_body_paragraph() -> None:
    text = """## Results

Important finding.

**Acknowledgements:** Thanks to everyone for support.

More results follow.

### References

Smith (2020).
"""
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "Important finding." in cleaned
    assert "Thanks to everyone for support." in cleaned
    assert "More results follow." in cleaned
    assert "Smith (2020)." not in cleaned


def test_ignores_early_author_contributions_in_publisher_front_matter() -> None:
    """Publisher front matter often puts Author Contributions before the abstract."""
    text = """### **RESEARCH ARTICLE**

10.1029/2023JB026879

#### **Key Points:**

- The fitted parameters for the target material were determined.

Received 12 APR 2023 Accepted 19 DEC 2023

#### **Author Contributions:**

**Conceptualization:** A. Author

## **Thermal Properties and Structural Evolution**

**Abstract** The target material is studied under controlled conditions.

#### **1. Introduction**

Material compressibility was studied using single-crystal XRD.

## Results

parameter is 256 units.

""" + "\n".join(f"Additional results line {i}." for i in range(40)) + """

### ACKNOWLEDGMENT

Thanks to collaborators.

## References

Smith et al. (2020).
"""
    cleaned = clean_markdown(text, _cfg())
    assert "fitted parameters for the target material" in cleaned
    assert "Material compressibility" in cleaned
    assert "parameter is 256 units" in cleaned
    assert "Conceptualization" in cleaned
    assert "Thanks to collaborators" not in cleaned
    assert "Smith et al." not in cleaned


def test_strips_funding_section_header() -> None:
    text = """## Results

Primary data here.

## Funding

Supported by NSF grant 12345.

## References

Smith (2020).
"""
    cleaned = clean_markdown(text, _short_doc_cfg())
    assert "Primary data here." in cleaned
    assert "NSF grant" not in cleaned
    assert "Smith (2020)." not in cleaned


def test_markdown_strip_stats_flags_heavy_strip() -> None:
    stats = markdown_strip_stats("abcdefghij", "abc", heavy_strip_fraction=0.5)
    assert stats["strip_fraction"] == 0.7
    assert stats["heavy_strip"] is True

    stats_ok = markdown_strip_stats("abcdefghij", "abcdefg", heavy_strip_fraction=0.5)
    assert stats_ok["heavy_strip"] is False
