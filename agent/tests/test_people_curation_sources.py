"""People curation: curated promotions must carry a non-wiki official/reputable URL."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PEOPLE_DIR = ROOT / "data" / "people"
WIKI_DIR = ROOT / "wiki" / "content" / "people"

_SAFE_HOST_HINTS = (
    "assembly.go.kr",
    "council.",
    "go.kr",
    "nobelprize.org",
    "wikidata.org",
    "peoplepower21.org",
    "justice21.org",
    "skku.edu",
    "smu.ac.kr",
    "pressian.com",
    "khanews.com",
    "donga.com",
    "joongang.co.kr",
    "fnnews.com",
    "digitaltoday.co.kr",
    "uljin21.com",
    "state.gov",
    "yna.co.kr",
    "newsis.com",
    "gukjenews.com",
)


def _curated_urls(data: dict) -> list[str]:
    sources = data.get("sources") or {}
    if not isinstance(sources, dict):
        return []
    urls: list[str] = []
    for key in ("official_urls", "profile_urls"):
        for u in sources.get(key) or []:
            urls.append(str(u))
    return urls


def test_recent_curation_batch_has_safe_source():
    """Regression: recent people curation promotions keep ≥1 safe URL."""
    batch = [
        "bak-gyun-taek",
        "gim-jong-dae",
        "han-gang",
        "jeong-uk-sik",
        "gu-jeong-u",
        "choe-ju-man",
        "im-seung-pil",
        "gim-yong",
        "i-myeong-hyeon",
        "jeong-sang-yong",
        "ryu-seong-suk",
        "gim-jeong-myeong",
        # 2026-08-05
        "cheon-ha-ram",
        "choe-jae-gu",
        "an-hyo-ik",
        "choe-eun-sik",
        "i-u-cheong",
        "o-hwang-gyun",
        "seo-jun-o",
        # 2026-08-06
        "an-hye-ri",
        "i-jun-su",
        "pyo-yeong-hui",
        "gim-jae-hyeon",
        "jo-bu-hwal",
        # 2026-08-07
        "song-seok-jun",
        "jo-ji-yeon",
        "i-du-hui",
        "i-hyeong-il",
        "gwak-no-jeong",
        "baek-seung-ju",
        "yun-nan-sil",
        "i-seong-hun",
        "jeong-chang-su",
        "i-seung-yeol",
        # 2026-08-08
        "bang-gi-seon",
        "yu-byeong-ho",
        "jo-il-gyo",
        "jo-gye-won",
        "i-yeong-jo",
        # 2026-08-09
        "choe-dae-ho",
        "gim-seong-won",
        "gwon-ik-hyeon",
        "yun-hye-seon",
        "ha-in-seong",
        "son-hyeon-bo",
        # 2026-08-10
        "yeom-gyu-song",
        "i-jong-sam",
        "byeon-hyeon-seop",
        "i-sang-sik",
        # 2026-08-11
        "choe-jeong-ho",
        "gim-jeong-gyeom",
        "jo-ju-hyeon",
        "yun-jong-o",
        "i-jang-seop",
        "choe-hyeong-sik",
        "gim-ui-gyeom",
    ]
    for slug in batch:
        data = yaml.safe_load((PEOPLE_DIR / f"{slug}.yaml").read_text(encoding="utf-8"))
        assert data["status"] == "curated", slug
        urls = _curated_urls(data)
        assert urls, f"{slug} missing official/profile url"
        assert any(any(h in u for h in _SAFE_HOST_HINTS) for u in urls), (slug, urls)
        wiki = (WIKI_DIR / f"{slug}.md").read_text(encoding="utf-8")
        assert "status: curated" in wiki.split("---", 2)[1]


def test_ssot_slug_alignment_no_orphan_people_pages():
    yaml_slugs = {p.stem for p in PEOPLE_DIR.glob("*.yaml")}
    wiki_slugs = {p.stem for p in WIKI_DIR.glob("*.md") if p.stem != "_index"}
    assert not (wiki_slugs - yaml_slugs), sorted(wiki_slugs - yaml_slugs)[:20]
    assert not (yaml_slugs - wiki_slugs), sorted(yaml_slugs - wiki_slugs)[:20]
