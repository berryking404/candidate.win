#!/usr/bin/env python3
"""Report Candydate cron outcomes to Leantime (factory paths / env auth)."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ID = int(os.environ.get("CANDYDATE_LEANTIME_PROJECT_ID", "0") or "0")
USER_ID = int(os.environ.get("CANDYDATE_LEANTIME_USER_ID", "0") or "0")
ASSIGNED_TO = os.environ.get("CANDYDATE_LEANTIME_ASSIGNED_TO", "1")
STATUS_DONE = 0
STATUS_BLOCKED = 1


def load_env() -> dict[str, str]:
    url = (os.environ.get("LEANTIME_URL") or "").strip()
    token = (
        os.environ.get("LEANTIME_ACCESS_TOKEN")
        or os.environ.get("LEANTIME_API_KEY")
        or ""
    ).strip()
    if not url or not token:
        raise RuntimeError("LEANTIME_URL and LEANTIME_ACCESS_TOKEN/API_KEY required")
    if PROJECT_ID <= 0 or USER_ID <= 0:
        raise RuntimeError(
            "CANDYDATE_LEANTIME_PROJECT_ID and CANDYDATE_LEANTIME_USER_ID must be set"
        )
    return {"LEANTIME_URL": url, "_LEANTIME_TOKEN": token, "auth": "bearer" if os.environ.get("LEANTIME_ACCESS_TOKEN") else "apikey"}


def auth_headers(env: dict[str, str]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if env.get("auth") == "bearer":
        headers["Authorization"] = "Bearer " + env["_LEANTIME_TOKEN"]
    else:
        headers["X-API-KEY"] = env["_LEANTIME_TOKEN"]
    return headers


def rpc(env: dict[str, str], method: str, params: dict[str, Any] | None = None) -> Any:
    url = env["LEANTIME_URL"].rstrip("/") + "/api/jsonrpc"
    payload = json.dumps(
        {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=auth_headers(env))
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "error" in data:
        err = data["error"]
        raise RuntimeError(f"{method}: {err.get('message')} ({err.get('code')})")
    return data.get("result")


def tail(path: str | None, max_chars: int = 6000) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists() or not p.is_file():
        return f"(log file not found: {path})"
    data = p.read_bytes()[-max_chars:]
    text = data.decode("utf-8", errors="replace")
    text = re.sub(
        r'(api[_-]?key|token|secret|password)(["\'\s:=]+)[^\s"\']+',
        r"\1\2[REDACTED]",
        text,
        flags=re.I,
    )
    return text.strip()


def kst_now_label() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime(
        "%Y-%m-%d %H:%M KST"
    )


def html_description(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(
        r"```\n(.*?)\n```",
        lambda m: "<pre>" + m.group(1) + "</pre>",
        escaped,
        flags=re.S,
    )
    return escaped.replace("\n", "<br>\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-name", required=True)
    ap.add_argument(
        "--status", required=True, choices=["done", "canceled", "blocked", "failed"]
    )
    ap.add_argument("--exit-code", required=True)
    ap.add_argument("--summary", default="")
    ap.add_argument("--log-file")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    success = args.status == "done"
    status_id = STATUS_DONE if success else STATUS_BLOCKED
    label = "성공" if success else "실패"
    title = f"[cron][{label}] {args.job_name} — {kst_now_label()}"
    log_tail = tail(args.log_file)
    desc_parts = [
        f"작업: {args.job_name}",
        f"상태: {args.status}",
        f"exit_code: {args.exit_code}",
    ]
    if args.summary:
        desc_parts += ["", "요약:", args.summary]
    if log_tail:
        desc_parts += ["", f"로그 tail ({args.log_file}):", "```", log_tail, "```"]
    description = html_description("\n".join(desc_parts))

    if args.dry_run:
        print(
            json.dumps(
                {
                    "headline": title,
                    "status": status_id,
                    "projectId": PROJECT_ID,
                    "userId": USER_ID,
                    "description_len": len(description),
                },
                ensure_ascii=False,
            )
        )
        return 0

    env = load_env()
    result = rpc(
        env,
        "leantime.rpc.Tickets.Tickets.addTicket",
        {
            "values": {
                "headline": title,
                "projectId": PROJECT_ID,
                "userId": USER_ID,
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "description": description,
                "status": status_id,
                "assignedTo": ASSIGNED_TO,
                "tags": "cron,candydate,candidate",
            }
        },
    )
    tid = result.get("id") if isinstance(result, dict) else result
    print(f"Created Leantime ticket {tid}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"leantime_cron_report failed: HTTP {exc.code}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"leantime_cron_report failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
