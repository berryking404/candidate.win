#!/usr/bin/env python3
"""Publish recent issue-radar candidates as public /today/ data.

The public surface must not expose internal approval tooling. This script converts
approved-for-display radar output into a neutral "오늘의 화제" queue and leaves
formal issue registration to the editor's separate workflow.
"""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "agent" / ".cache" / "issue_candidates"
TODAY_DATA = ROOT / "wiki" / "data" / "today.yaml"

STATUS_LABELS = {
    "독립 이슈": "정식 검토",
    "기존 이슈 병합/업데이트": "기존 이슈와 함께 검토",
    "보류 후 추가 확인": "추가 확인",
}


def latest_cache() -> Path:
    candidates = sorted(CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"no issue candidate cache found under {CACHE_DIR}")
    return candidates[0]


def public_status(recommendation: str) -> str:
    for prefix, label in STATUS_LABELS.items():
        if recommendation.startswith(prefix):
            return label
    return "편집 검토"


def compact_item(raw: dict[str, Any], rank: int) -> dict[str, Any]:
    signals = raw.get("signals") or {}
    actors = signals.get("stance_actor_terms") or []
    articles = raw.get("articles") or []
    item: dict[str, Any] = {
        "rank": rank,
        "title": html.unescape(str(raw.get("title") or raw.get("keyword") or "제목 없음")),
        "status": public_status(str(raw.get("recommendation") or "")),
        "score": int(raw.get("score") or 0),
        "summary": (
            f"최근 보도 {signals.get('news_count', 0)}건, 매체 {signals.get('outlet_count', 0)}곳에서 확인된 공적 쟁점입니다."
        ),
        "signals": {
            "news_count": int(signals.get("news_count") or 0),
            "outlet_count": int(signals.get("outlet_count") or 0),
            "public_actor": ", ".join(actors) if actors else "확인 중",
        },
        "sources": [],
    }
    if raw.get("merge_target"):
        item["related_issue"] = raw["merge_target"]
    for article in articles[:3]:
        url = article.get("url")
        title = html.unescape(str(article.get("title") or url))
        if not url:
            continue
        item["sources"].append({"title": str(title), "url": str(url)})
    return item


def build_payload(cache_path: Path, limit: int) -> dict[str, Any]:
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    items = [compact_item(c, i) for i, c in enumerate((data.get("candidates") or [])[:limit], 1)]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_date": data.get("date") or cache_path.stem,
        "window_hours": 72,
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish public today-topic queue from issue-radar cache")
    parser.add_argument("--input", type=Path, default=None, help="issue candidate JSON cache path")
    parser.add_argument("--output", type=Path, default=TODAY_DATA, help="output YAML path")
    parser.add_argument("--limit", type=int, default=10, help="max public cards")
    args = parser.parse_args()

    cache_path = (args.input or latest_cache()).resolve()
    output_path = args.output.resolve()
    payload = build_payload(cache_path, args.limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"wrote {output_path.relative_to(ROOT)} from {cache_path.relative_to(ROOT)} ({len(payload['items'])} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
