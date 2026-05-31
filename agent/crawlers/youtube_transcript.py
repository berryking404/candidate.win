"""YouTube 자막 크롤러.

채널 RSS → youtube-transcript-api 순으로 자막 수집.
YouTube Data API (search.list) 는 quota 비용이 크므로 RSS 로 우선 처리한다.

환경변수:
    YOUTUBE_API_KEY — 채널 RSS 미지원 채널 폴백용 (선택)

반환 스키마 (VideoTranscript):
    {video_id, title, transcript, channel_id, published}
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TypedDict

import feedparser
import httpx
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent / ".cache" / "sources" / "youtube"
CHANNEL_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
YT_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class VideoTranscript(TypedDict):
    video_id: str
    title: str
    transcript: str
    channel_id: str
    published: str  # ISO 8601


def crawl_channel(
    channel_id: str,
    *,
    keywords: list[str] | None = None,
    max_videos: int = 10,
    no_youtube: bool = False,
) -> list[VideoTranscript]:
    """채널 RSS 로 최신 영상 목록 조회 후 자막 수집.

    Args:
        channel_id: YouTube 채널 ID (UC...).
        keywords: 제목·자막에 하나라도 포함된 영상만 반환. None 이면 전체.
        max_videos: 최대 처리 영상 수.
        no_youtube: True 면 YouTube 관련 호출 전체 차단 (--no-youtube 플래그).

    Returns:
        VideoTranscript 목록.
    """
    if no_youtube:
        logger.info("--no-youtube 플래그: YouTube 호출 건너뜀")
        return []

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    video_ids = _get_video_ids_from_rss(channel_id, max_videos)

    if not video_ids:
        logger.warning("채널 RSS 영상 없음 [channel_id=%s], API 폴백 시도", channel_id)
        video_ids = _get_video_ids_from_api(channel_id, max_videos)

    results: list[VideoTranscript] = []
    for vid_id, title, published in video_ids:
        if keywords and not _title_matches(title, keywords):
            continue
        transcript = _get_transcript(vid_id, keywords)
        if transcript is None:
            continue
        results.append(
            VideoTranscript(
                video_id=vid_id,
                title=title,
                transcript=transcript,
                channel_id=channel_id,
                published=published,
            )
        )

    logger.info(
        "YouTube: 채널=%s, 후보=%d, 자막 수집=%d",
        channel_id, len(video_ids), len(results),
    )
    return results


def crawl_channels(
    channel_ids: list[str],
    *,
    keywords: list[str] | None = None,
    max_per_channel: int = 10,
    no_youtube: bool = False,
) -> list[VideoTranscript]:
    """여러 채널을 순차 처리."""
    results: list[VideoTranscript] = []
    for cid in channel_ids:
        results.extend(
            crawl_channel(cid, keywords=keywords, max_videos=max_per_channel, no_youtube=no_youtube)
        )
    return results


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _get_video_ids_from_rss(channel_id: str, limit: int) -> list[tuple[str, str, str]]:
    """채널 RSS 피드에서 (video_id, title, published) 추출. quota 무관."""
    url = CHANNEL_RSS.format(channel_id=channel_id)
    try:
        feed = feedparser.parse(url)
        items: list[tuple[str, str, str]] = []
        for entry in feed.entries[:limit]:
            vid_id = entry.get("yt_videoid", "")
            title = entry.get("title", "")
            published = entry.get("published", "")
            if vid_id:
                items.append((vid_id, title, published))
        return items
    except Exception as exc:
        logger.warning("채널 RSS 파싱 실패 [channel_id=%s]: %s", channel_id, exc)
        return []


def _get_video_ids_from_api(channel_id: str, limit: int) -> list[tuple[str, str, str]]:
    """YouTube Data API search.list 로 영상 조회 (quota 100 units/호출)."""
    from quotas.youtube import YouTubeQuota, QuotaExhausted

    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        logger.warning("YOUTUBE_API_KEY 미설정 — API 폴백 불가")
        return []

    quota = YouTubeQuota()
    try:
        quota.charge_op("search.list")
    except QuotaExhausted as e:
        logger.error("YouTube quota 소진: %s", e)
        return []

    params = {
        "key": api_key,
        "channelId": channel_id,
        "part": "snippet",
        "order": "date",
        "type": "video",
        "maxResults": min(limit, 50),
    }
    try:
        with httpx.Client(timeout=15) as client:
            r = client.get(YT_SEARCH_URL, params=params)
            r.raise_for_status()
            items = r.json().get("items", [])
            return [
                (
                    it["id"]["videoId"],
                    it["snippet"]["title"],
                    it["snippet"]["publishedAt"],
                )
                for it in items
                if it.get("id", {}).get("videoId")
            ]
    except Exception as exc:
        logger.warning("YouTube API 검색 실패: %s", exc)
        return []


def _get_transcript(video_id: str, keywords: list[str] | None) -> str | None:
    """youtube-transcript-api 로 자막 텍스트 반환. 실패 시 None."""
    cache_file = CACHE_DIR / f"{video_id}.txt"
    if cache_file.exists():
        text = cache_file.read_text(encoding="utf-8")
        if keywords and not any(kw in text for kw in keywords):
            return None
        return text

    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(
            video_id, languages=["ko", "ko-KR", "en"]
        )
        text = " ".join(seg["text"] for seg in transcript_list)
    except (NoTranscriptFound, TranscriptsDisabled):
        logger.debug("자막 없음 [video_id=%s]", video_id)
        return None
    except Exception as exc:
        logger.warning("자막 수집 실패 [video_id=%s]: %s", video_id, exc)
        return None

    if keywords and not any(kw in text for kw in keywords):
        return None

    cache_file.write_text(text, encoding="utf-8")
    return text


def _title_matches(title: str, keywords: list[str]) -> bool:
    return any(kw in title for kw in keywords)
