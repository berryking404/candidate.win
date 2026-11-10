"""GH Actions CD for edge/report Worker (Option A closeout)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WRANGLER = REPO / "edge" / "report" / "wrangler.toml"
WORKFLOW = REPO / ".github" / "workflows" / "deploy-report-worker.yml"
EDGE_README = REPO / "edge" / "report" / "README.md"
ROOT_README = REPO / "README.md"


def test_wrangler_route_is_declared() -> None:
    text = WRANGLER.read_text(encoding="utf-8")
    assert 'pattern = "wiki.candidate.win/api/report*"' in text
    assert 'zone_name = "candidate.win"' in text
    assert 'name = "candidate-report-api"' in text


def test_deploy_workflow_uses_cloudflare_secrets() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "cloudflare/wrangler-action@" in text
    assert "secrets.CLOUDFLARE_API_TOKEN" in text
    assert "secrets.CLOUDFLARE_ACCOUNT_ID" in text
    assert "CANDYDATE_ISSUES_TOKEN" in text
    assert "edge/report" in text
    assert "workflow_dispatch" in text
    # Separate from Pages job
    assert "Deploy report Worker" in text or "deploy-report-worker" in text.lower() or "candidate-report-api" in text


def test_readme_documents_actions_cd() -> None:
    edge = EDGE_README.read_text(encoding="utf-8")
    root = ROOT_README.read_text(encoding="utf-8")
    assert "GitHub Actions" in edge
    assert "deploy-report-worker" in edge
    assert "CLOUDFLARE_API_TOKEN" in root
    assert "CLOUDFLARE_ACCOUNT_ID" in root
    assert "wrangler secret put" not in edge
