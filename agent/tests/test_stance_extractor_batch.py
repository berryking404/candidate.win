"""escalation 큐 enqueue 스키마 검증 (OpenAI Batch 스키마 아님)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from processors import stance_extractor


@pytest.fixture
def isolated_batch_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(stance_extractor, "ESCALATION_DIR", tmp_path)
    monkeypatch.setattr(stance_extractor, "BATCH_DIR", tmp_path)
    return tmp_path


def _read_pending(batch_dir: Path) -> list[dict]:
    pending = batch_dir / "pending.jsonl"
    assert pending.exists(), "pending.jsonl 이 생성되지 않음"
    return [
        json.loads(line)
        for line in pending.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


REQUIRED_KEYS = {
    "cache_key",
    "person_slug",
    "person_name",
    "issue_slug",
    "criteria",
    "text",
    "tier1_result",
}


def test_enqueue_escalation_has_factory_queue_keys(isolated_batch_dir):
    stance_extractor._enqueue_escalation(
        text="샘플 텍스트",
        person_slug="lee-jae-myung",
        person_name="이재명",
        issue_slug="real-estate-tax-2026",
        cache_key="test-key-001",
        tier1_result={"position": "mixed", "confidence": 0.4},
    )

    [entry] = _read_pending(isolated_batch_dir)
    assert REQUIRED_KEYS <= set(entry.keys())
    assert entry["person_slug"] == "lee-jae-myung"
    assert entry["tier1_result"]["position"] == "mixed"
    assert "method" not in entry
    assert "url" not in entry
    assert "body" not in entry


def test_enqueue_batch_alias_writes_escalation_entry(isolated_batch_dir):
    stance_extractor._enqueue_batch(
        text="샘플",
        person_slug="lee-jae-myung",
        person_name="이재명",
        issue_slug="real-estate-tax-2026",
        cache_key="test-key-002",
    )
    [entry] = _read_pending(isolated_batch_dir)
    assert entry["cache_key"] == "test-key-002"
    assert "_meta" not in entry


def test_enqueue_escalation_appends(isolated_batch_dir):
    for i in range(3):
        stance_extractor._enqueue_escalation(
            text=f"본문 {i}",
            person_slug="p",
            person_name="이름",
            issue_slug="이슈",
            cache_key=f"k-{i}",
        )
    entries = _read_pending(isolated_batch_dir)
    assert [e["cache_key"] for e in entries] == ["k-0", "k-1", "k-2"]


def test_enqueue_records_issue_sidecar(isolated_batch_dir):
    stance_extractor._enqueue_escalation(
        text="본문 1",
        person_slug="p1",
        person_name="이름1",
        issue_slug="issue-b",
        cache_key="k-b",
    )
    stance_extractor._enqueue_escalation(
        text="본문 2",
        person_slug="p2",
        person_name="이름2",
        issue_slug="issue-a",
        cache_key="k-a",
    )
    sidecar = json.loads(
        (isolated_batch_dir / stance_extractor.PENDING_ISSUES_FILE).read_text(
            encoding="utf-8"
        )
    )
    assert sidecar == ["issue-a", "issue-b"]
