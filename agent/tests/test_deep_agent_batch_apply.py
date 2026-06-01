"""daily Batch apply orchestration regression tests."""

from __future__ import annotations

import json
import sys
import types
from argparse import Namespace
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))
import yaml

if "yaml" not in sys.modules:
    def _safe_load(text: str):
        data = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip() or None
        return data
    yaml_module = types.ModuleType("yaml")
    setattr(yaml_module, "safe_load", _safe_load)
    sys.modules["yaml"] = yaml_module

if "dotenv" not in sys.modules:
    dotenv_module = types.ModuleType("dotenv")
    setattr(dotenv_module, "load_dotenv", lambda *args, **kwargs: None)
    sys.modules["dotenv"] = dotenv_module

import deep_agent


def test_active_batch_issue_slugs_reads_sidecar(tmp_path, monkeypatch):
    active = tmp_path / ".cache" / "batch" / "active.json"
    active.parent.mkdir(parents=True)
    active.write_text(
        json.dumps({"batch_id": "batch_1", "issue_slugs": ["issue-b", "issue-a", "issue-b"]}),
        encoding="utf-8",
    )
    fake_deep_agent_py = tmp_path / "deep_agent.py"
    fake_deep_agent_py.write_text("", encoding="utf-8")
    monkeypatch.setattr(deep_agent, "__file__", str(fake_deep_agent_py))

    assert deep_agent._active_batch_issue_slugs() == ["issue-a", "issue-b"]


def test_ongoing_issue_slugs_matches_all_filter(tmp_path, monkeypatch):
    issues = tmp_path / "issues"
    issues.mkdir()
    (issues / "ongoing-a.yaml").write_text("status: ongoing\n", encoding="utf-8")
    (issues / "default-ongoing.yaml").write_text("", encoding="utf-8")
    (issues / "closed-a.yaml").write_text("status: closed\n", encoding="utf-8")
    monkeypatch.setattr(deep_agent, "DATA_ISSUES", issues)

    assert deep_agent._ongoing_issue_slugs() == ["default-ongoing", "ongoing-a"]


def test_run_batch_apply_ingests_then_applies_active_issues(tmp_path, monkeypatch):
    calls: list[str] = []
    active = tmp_path / "active.json"
    active.write_text("{}", encoding="utf-8")
    fake_submitter = types.SimpleNamespace(poll_and_ingest=lambda: True)
    monkeypatch.setitem(sys.modules, "publishers.batch_submitter", fake_submitter)
    monkeypatch.setattr(deep_agent, "_active_batch_file", lambda: active)
    monkeypatch.setattr(deep_agent, "_active_batch_issue_slugs", lambda: ["issue-a", "issue-b"])
    monkeypatch.setattr(deep_agent, "_ongoing_issue_slugs", lambda: ["fallback-issue"])
    monkeypatch.setattr(deep_agent, "run_apply", lambda slug, opts: calls.append(slug))

    assert deep_agent.run_batch_apply(Namespace(no_escalate=False, dry_run=False)) is True
    assert calls == ["issue-a", "issue-b"]


def test_run_batch_apply_falls_back_to_ongoing_for_legacy_active(tmp_path, monkeypatch):
    calls: list[str] = []
    active = tmp_path / "active.json"
    active.write_text("{}", encoding="utf-8")
    fake_submitter = types.SimpleNamespace(poll_and_ingest=lambda: True)
    monkeypatch.setitem(sys.modules, "publishers.batch_submitter", fake_submitter)
    monkeypatch.setattr(deep_agent, "_active_batch_file", lambda: active)
    monkeypatch.setattr(deep_agent, "_active_batch_issue_slugs", lambda: [])
    monkeypatch.setattr(deep_agent, "_ongoing_issue_slugs", lambda: ["ongoing-a"])
    monkeypatch.setattr(deep_agent, "run_apply", lambda slug, opts: calls.append(slug))

    assert deep_agent.run_batch_apply(Namespace(no_escalate=False, dry_run=False)) is True
    assert calls == ["ongoing-a"]


def test_run_batch_apply_returns_false_when_batch_not_done(tmp_path, monkeypatch):
    active = tmp_path / "active.json"
    active.write_text("{}", encoding="utf-8")
    fake_submitter = types.SimpleNamespace(poll_and_ingest=lambda: False)
    monkeypatch.setitem(sys.modules, "publishers.batch_submitter", fake_submitter)
    monkeypatch.setattr(deep_agent, "_active_batch_file", lambda: active)
    monkeypatch.setattr(deep_agent, "_active_batch_issue_slugs", lambda: ["issue-a"])
    monkeypatch.setattr(deep_agent, "run_apply", lambda slug, opts: (_ for _ in ()).throw(AssertionError("should not apply")))

    assert deep_agent.run_batch_apply(Namespace(no_escalate=False, dry_run=False)) is False


def test_run_batch_apply_status_returns_no_active_without_applying(tmp_path, monkeypatch):
    missing_active = tmp_path / "missing-active.json"
    fake_submitter = types.SimpleNamespace(poll_and_ingest=lambda: (_ for _ in ()).throw(AssertionError("should not poll")))
    monkeypatch.setitem(sys.modules, "publishers.batch_submitter", fake_submitter)
    monkeypatch.setattr(deep_agent, "_active_batch_file", lambda: missing_active)
    monkeypatch.setattr(deep_agent, "run_apply", lambda slug, opts: (_ for _ in ()).throw(AssertionError("should not apply")))

    assert deep_agent.run_batch_apply_status(Namespace(no_escalate=False, dry_run=False)) == "no_active"
    assert deep_agent.run_batch_apply(Namespace(no_escalate=False, dry_run=False)) is False
