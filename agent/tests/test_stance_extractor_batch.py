"""_enqueue_batch 가 OpenAI Batch API 스키마를 위반하지 않는지 검증.

회귀 테스트: `_meta` 같은 unknown top-level key 가 들어가면
Batch submit 직후 status=failed 가 되어 처리량 0이 됨.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from processors import stance_extractor

ALLOWED_TOP_LEVEL_KEYS = {"custom_id", "method", "url", "body"}


@pytest.fixture
def isolated_batch_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(stance_extractor, "BATCH_DIR", tmp_path)
    return tmp_path


def _read_pending(batch_dir: Path) -> list[dict]:
    pending = batch_dir / "pending.jsonl"
    assert pending.exists(), "pending.jsonl 이 생성되지 않음"
    return [json.loads(line) for line in pending.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_enqueue_batch_has_only_openai_allowed_keys(isolated_batch_dir):
    stance_extractor._enqueue_batch(
        text="샘플 텍스트",
        person_slug="lee-jae-myung",
        person_name="이재명",
        issue_slug="real-estate-tax-2026",
        cache_key="test-key-001",
    )

    [entry] = _read_pending(isolated_batch_dir)
    extra = set(entry.keys()) - ALLOWED_TOP_LEVEL_KEYS
    assert not extra, f"OpenAI Batch API 가 모르는 top-level key 포함: {extra}"


def test_enqueue_batch_no_meta_field(isolated_batch_dir):
    """`_meta` 회귀 가드: 2026-05-06 batch_69fac21258d... 실패 원인."""
    stance_extractor._enqueue_batch(
        text="샘플",
        person_slug="lee-jae-myung",
        person_name="이재명",
        issue_slug="real-estate-tax-2026",
        cache_key="test-key-002",
    )
    [entry] = _read_pending(isolated_batch_dir)
    assert "_meta" not in entry


def test_enqueue_batch_required_fields_present(isolated_batch_dir):
    stance_extractor._enqueue_batch(
        text="본문",
        person_slug="lee-jae-myung",
        person_name="이재명",
        issue_slug="real-estate-tax-2026",
        cache_key="test-key-003",
    )
    [entry] = _read_pending(isolated_batch_dir)
    assert entry["custom_id"] == "test-key-003"
    assert entry["method"] == "POST"
    assert entry["url"] == "/v1/chat/completions"
    body = entry["body"]
    assert "model" in body
    assert isinstance(body.get("messages"), list) and len(body["messages"]) == 2
    assert body["temperature"] == 0


def test_enqueue_batch_appends(isolated_batch_dir):
    for i in range(3):
        stance_extractor._enqueue_batch(
            text=f"본문 {i}",
            person_slug="p",
            person_name="이름",
            issue_slug="이슈",
            cache_key=f"k-{i}",
        )
    entries = _read_pending(isolated_batch_dir)
    assert [e["custom_id"] for e in entries] == ["k-0", "k-1", "k-2"]


def test_enqueue_batch_records_issue_sidecar_without_batch_schema_pollution(isolated_batch_dir):
    stance_extractor._enqueue_batch(
        text="본문 1",
        person_slug="p1",
        person_name="이름1",
        issue_slug="issue-b",
        cache_key="k-b",
    )
    stance_extractor._enqueue_batch(
        text="본문 2",
        person_slug="p2",
        person_name="이름2",
        issue_slug="issue-a",
        cache_key="k-a",
    )
    stance_extractor._enqueue_batch(
        text="본문 3",
        person_slug="p3",
        person_name="이름3",
        issue_slug="issue-b",
        cache_key="k-b2",
    )

    entries = _read_pending(isolated_batch_dir)
    assert all(set(entry) <= ALLOWED_TOP_LEVEL_KEYS for entry in entries)
    sidecar = isolated_batch_dir / stance_extractor.PENDING_ISSUES_FILE
    assert json.loads(sidecar.read_text(encoding="utf-8")) == ["issue-a", "issue-b"]


def test_enqueue_batch_truncates_long_text(isolated_batch_dir):
    long_text = "가" * 20000
    stance_extractor._enqueue_batch(
        text=long_text,
        person_slug="p",
        person_name="이름",
        issue_slug="이슈",
        cache_key="k-long",
    )
    [entry] = _read_pending(isolated_batch_dir)
    user_msg = entry["body"]["messages"][1]["content"]
    assert "가" * 12000 in user_msg
    assert "가" * 12001 not in user_msg
