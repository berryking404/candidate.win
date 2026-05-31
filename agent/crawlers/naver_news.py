"""Naver News Search API 크롤러.

환경변수:
    NAVER_CLIENT_ID     — 네이버 개발자센터 애플리케이션 Client ID
    NAVER_CLIENT_SECRET — 네이버 개발자센터 애플리케이션 Client Secret

반환 스키마 (Article):
    {url, title, text, date, source}
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
CACHE_DIR = Path(__file__).parent.parent / ".cache" / "sources" / "naver"
REQUEST_DELAY = 0.3  # 네이버 API 호출 간격 (초)


class Article(TypedDict):
    url: str
    title: str
    text: str
    date: str   # ISO 8601
    source: str


def crawl(
    keywords: list[str],
    *,
    max_per_keyword: int = 30,
    date_from: str | None = None,  # "YYYY-MM-DD"
    fetch_full_text: bool = False,
) -> list[Article]:
    """Naver News Search API 로 기사 목록 수집.

    Args:
        keywords: 검색어 목록. 각 키워드별로 API 호출.
        max_per_keyword: 키워드당 최대 결과 수 (API 최대 100).
        date_from: 이 날짜 이후 기사만 포함 (YYYY-MM-DD).
        fetch_full_text: True 면 원문 페이지 스크래핑 시도.

    Returns:
        중복 제거된 Article 목록.
    """
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.warning("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정 — 빈 결과 반환")
        return []

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    seen_urls: set[str] = set()
    articles: list[Article] = []

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    cutoff_dt = _parse_date(date_from) if date_from else None

    with httpx.Client(timeout=15) as client:
        for keyword in keywords:
            results = _search(client, headers, keyword, max_per_keyword)
            for item in results:
                url = item.get("originallink") or item.get("link", "")
                if not url or url in seen_urls:
                    continue

                pub_date = _parse_naver_date(item.get("pubDate", ""))
                if cutoff_dt and pub_date and pub_date < cutoff_dt:
                    continue

                seen_urls.add(url)
                title = _strip_tags(item.get("title", ""))
                text = _strip_tags(item.get("description", ""))

                if fetch_full_text:
                    full = _fetch_full_text(client, url)
                    if full:
                        text = full

                articles.append(
                    Article(
                        url=url,
                        title=title,
                        text=text,
                        date=pub_date.isoformat() if pub_date else "",
                        source="naver_news",
                    )
                )

            time.sleep(REQUEST_DELAY)

    logger.info("Naver News: %d개 기사 수집 (keywords=%s)", len(articles), keywords)
    return articles


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _search(
    client: httpx.Client,
    headers: dict,
    keyword: str,
    display: int,
) -> list[dict]:
    params = {
        "query": keyword,
        "display": min(display, 100),
        "sort": "date",
    }
    try:
        r = client.get(SEARCH_URL, headers=headers, params=params)
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as exc:
        logger.warning("Naver 검색 실패 [keyword=%s]: %s", keyword, exc)
        return []


def _fetch_full_text(client: httpx.Client, url: str) -> str:
    """기사 원문 페이지에서 본문 텍스트 추출. 실패하면 빈 문자열."""
    cache_key = hashlib.sha256(url.encode()).hexdigest()[:16]
    cache_file = CACHE_DIR / f"{cache_key}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    try:
        r = client.get(url, follow_redirects=True, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 네이버 뉴스 본문 선택자 우선, 일반 article/p 태그 폴백
        selectors = [
            "#dic_area", "#articeBody", "#newsEndContents",
            "article", ".article_body", ".news_body",
        ]
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(separator="\n", strip=True)
                if len(text) > 100:
                    cache_file.write_text(text, encoding="utf-8")
                    return text

        # 폴백: 모든 <p> 태그
        paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 30]
        text = "\n".join(paragraphs)
        if text:
            cache_file.write_text(text, encoding="utf-8")
        return text

    except Exception as exc:
        logger.debug("원문 스크래핑 실패 [url=%s]: %s", url, exc)
        return ""


def _strip_tags(html: str) -> str:
    """HTML 태그 제거."""
    return re.sub(r"<[^>]+>", "", html).strip()


def _parse_date(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_naver_date(s: str) -> datetime | None:
    """Naver API pubDate 파싱: 'Mon, 29 Apr 2026 12:00:00 +0900'."""
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except Exception:
        return None
