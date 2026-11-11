import json
import os
import sys
import urllib.request
from pathlib import Path

# `python3 wiki/fetch_issues.py` 및 `cd wiki && python3 fetch_issues.py` 모두 허용
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sanitize_public_text import sanitize_public_status_text

token = os.environ.get("GITHUB_TOKEN")
headers = {
    "Accept": "application/vnd.github+json",
}
if token:
    headers["Authorization"] = f"token {token}"

def get_json(url):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode())

repo = "berryking404/candidate.win"
issues_url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100"

try:
    print(f"Fetching issues from {issues_url}...")
    issues = get_json(issues_url)
    combined = []
    
    for issue in issues:
        # Pull request인 경우는 제외 (이슈만 처리)
        if "pull_request" in issue:
            continue
            
        # labels가 비어 있으면 건너뜀
        issue_labels = [l["name"] for l in issue.get("labels", [])]
        if not ("correction" in issue_labels or "takedown" in issue_labels):
            continue
            
        print(f"Processing issue #{issue['number']}: {issue['title']}")
        
        # 댓글(답변) 가져오기
        comments = []
        if issue.get("comments", 0) > 0:
            comments_url = issue["comments_url"]
            try:
                comments_data = get_json(comments_url)
                comments = [
                    {
                        "user": c["user"]["login"],
                        "body": sanitize_public_status_text(c["body"]),
                        "created_at": c["created_at"]
                    }
                    for c in comments_data
                ]
            except Exception as e:
                print(f"  Error fetching comments for issue #{issue['number']}: {e}")
                
        combined.append({
            "number": issue["number"],
            "title": issue["title"],
            "html_url": issue["html_url"],
            "state": issue["state"],
            "body": sanitize_public_status_text(issue["body"]),
            "created_at": issue["created_at"],
            "closed_at": issue["closed_at"],
            "labels": issue["labels"],
            "comments": comments
        })
        
    os.makedirs("wiki/data", exist_ok=True)
    with open("wiki/data/reports.json", "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    print(f"Successfully saved {len(combined)} issues with comments to wiki/data/reports.json")
except Exception as e:
    print(f"Error fetching issues: {e}")
    exit(1)
