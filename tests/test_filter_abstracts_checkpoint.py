"""Tests for filter_abstracts checkpoint helpers."""

from pathlib import Path

from litcurate.stages.filter_abstracts import (
    _abstract_batch_for_llm,
    _batch_is_complete,
    _build_abstract_filter_prompt,
    _clear_checkpoint,
    _load_checkpoint_decisions,
    _save_checkpoint,
)
from litcurate.stages.utils import read_json


def test_checkpoint_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "filter_abstracts.checkpoint.json"
    paper_ids = ["p1", "p2", "p3"]
    decisions = [{"paper_id": "p1", "keep": True, "reason": "relevant"}]
    criteria = "Keep papers with extractable primary data."

    _save_checkpoint(
        path,
        paper_ids,
        decisions,
        last_completed_batch=1,
        filter_criteria=criteria,
    )
    payload = read_json(path)
    assert payload["filter_criteria"] == criteria
    assert payload["decisions"] == decisions

    loaded = _load_checkpoint_decisions(path, paper_ids, criteria)
    assert loaded == decisions


def test_checkpoint_invalid_when_paper_ids_change(tmp_path: Path) -> None:
    path = tmp_path / "filter_abstracts.checkpoint.json"
    criteria = "Keep relevant papers."
    _save_checkpoint(
        path,
        ["p1", "p2"],
        [{"paper_id": "p1", "keep": True, "reason": "relevant"}],
        last_completed_batch=1,
        filter_criteria=criteria,
    )
    assert _load_checkpoint_decisions(path, ["p1", "p3"], criteria) == []


def test_checkpoint_invalid_when_filter_criteria_change(tmp_path: Path) -> None:
    path = tmp_path / "filter_abstracts.checkpoint.json"
    paper_ids = ["p1", "p2"]
    _save_checkpoint(
        path,
        paper_ids,
        [{"paper_id": "p1", "keep": True, "reason": "relevant"}],
        last_completed_batch=1,
        filter_criteria="Keep relevant papers.",
    )
    assert _load_checkpoint_decisions(path, paper_ids, "Different criteria.") == []


def test_batch_is_complete() -> None:
    batch = [{"paper_id": "p1"}, {"paper_id": "p2"}]
    decision_map = {"p1": {"keep": True}, "p2": {"keep": False}}
    assert _batch_is_complete(batch, decision_map) is True
    assert _batch_is_complete(batch, {"p1": {"keep": True}}) is False


def test_clear_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "filter_abstracts.checkpoint.json"
    _save_checkpoint(path, ["p1"], [], last_completed_batch=0, filter_criteria="criteria")
    _clear_checkpoint(path)
    assert not path.exists()


def test_abstract_batch_strips_metadata() -> None:
    batch = [
        {
            "paper_id": "p1",
            "abstract": "Reports measured parameters for the target system.",
            "is_oa": True,
            "citation_count": 120,
            "score": 0.99,
            "title": "Should not appear",
            "journal": "Nature",
        }
    ]
    slim = _abstract_batch_for_llm(batch)
    assert slim == [
        {"paper_id": "p1", "abstract": "Reports measured parameters for the target system."}
    ]

    prompt = _build_abstract_filter_prompt("Keep relevant papers.", batch)
    assert "Reports measured parameters for the target system." in prompt
    assert "is_oa" not in prompt
    assert "citation_count" not in prompt
    assert "0.99" not in prompt
    assert "Nature" not in prompt
    assert "using only each paper's abstract" in prompt


def test_filter_batch_retries_missing_after_truncated(monkeypatch) -> None:
    from litcurate.clients.llm import LlmResponse
    from litcurate.stages.filter_abstracts import _filter_batch_with_retry

    batch = [
        {"paper_id": "p1", "abstract": "Primary results for the target system."},
        {"paper_id": "p2", "abstract": "Mantle seismic model."},
    ]
    labels: list[str] = []

    def fake_chat(*args, **kwargs):
        label = kwargs.get("label", "")
        labels.append(label)
        if label == "batch_1":
            return LlmResponse(
                text='{"decisions":[{"paper_id":"p1","keep":true,"reason":"relevant"}]}',
                finish_reason="length",
                output_tokens=100,
                truncated=True,
            )
        return LlmResponse(
            text='{"decisions":[{"paper_id":"p2","keep":false,"reason":"seismic only"}]}',
            finish_reason="stop",
            truncated=False,
        )

    monkeypatch.setattr("litcurate.stages.filter_abstracts.llm_chat", fake_chat)
    decisions = _filter_batch_with_retry(
        ctx=object(),  # type: ignore[arg-type]
        criteria="Keep relevant",
        batch=batch,
        model="qwen3:14b",
        max_tokens=100,
        stage_llm=None,
        label_prefix="batch_1",
    )
    by_id = {d["paper_id"]: d for d in decisions}
    assert by_id["p1"]["keep"] is True
    assert by_id["p2"]["keep"] is False
    assert "batch_1" in labels
    assert any(label.startswith("batch_1") and label != "batch_1" for label in labels)


def test_single_paper_failure_marks_pending(monkeypatch) -> None:
    from litcurate.clients.llm import LlmResponse
    from litcurate.stages.filter_abstracts import _filter_batch_with_retry

    batch = [{"paper_id": "p_bad", "abstract": "???"}]

    def fake_chat(*args, **kwargs):
        return LlmResponse(
            text="not valid json at all",
            finish_reason="stop",
            truncated=False,
        )

    monkeypatch.setattr("litcurate.stages.filter_abstracts.llm_chat", fake_chat)
    decisions = _filter_batch_with_retry(
        ctx=object(),  # type: ignore[arg-type]
        criteria="Keep relevant",
        batch=batch,
        model="qwen3:14b",
        max_tokens=100,
        stage_llm=None,
        label_prefix="batch_1aa",
    )
    assert len(decisions) == 1
    assert decisions[0]["paper_id"] == "p_bad"
    assert decisions[0]["keep"] is None
    assert decisions[0]["status"] == "pending"
    assert "llm failed" in decisions[0]["reason"]
