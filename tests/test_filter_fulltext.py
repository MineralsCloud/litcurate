"""Tests for filter_fulltext truncation retry and pending handling."""

from __future__ import annotations


def test_fulltext_batch_retries_missing_after_truncated(monkeypatch) -> None:
    from litcurate.clients.llm import LlmResponse
    from litcurate.stages.filter_fulltext import _filter_batch_with_retry

    batch = [
        {"paper_id": "p1", "excerpt": "New fitted parameters reported in Table 1."},
        {"paper_id": "p2", "excerpt": "Uses published values for calibration."},
    ]
    labels: list[str] = []

    def fake_chat(*args, **kwargs):
        label = kwargs.get("label", "")
        labels.append(label)
        if label == "batch_1":
            return LlmResponse(
                text='{"decisions":[{"paper_id":"p1","keep":true,"reason":"new data"}]}',
                finish_reason="length",
                output_tokens=100,
                truncated=True,
            )
        return LlmResponse(
            text='{"decisions":[{"paper_id":"p2","keep":false,"reason":"cited only"}]}',
            finish_reason="stop",
            truncated=False,
        )

    monkeypatch.setattr("litcurate.stages.filter_fulltext.llm_chat", fake_chat)
    decisions = _filter_batch_with_retry(
        ctx=object(),  # type: ignore[arg-type]
        criteria="Keep new primary data",
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


def test_fulltext_single_paper_failure_marks_pending(monkeypatch) -> None:
    from litcurate.clients.llm import LlmResponse
    from litcurate.stages.filter_fulltext import _filter_batch_with_retry

    batch = [{"paper_id": "p_bad", "excerpt": "???"}]

    def fake_chat(*args, **kwargs):
        return LlmResponse(
            text="not valid json at all",
            finish_reason="stop",
            truncated=False,
        )

    monkeypatch.setattr("litcurate.stages.filter_fulltext.llm_chat", fake_chat)
    decisions = _filter_batch_with_retry(
        ctx=object(),  # type: ignore[arg-type]
        criteria="Keep new primary data",
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
