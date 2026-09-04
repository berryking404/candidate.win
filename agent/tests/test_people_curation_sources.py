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
    "khan.co.kr",
    "donga.com",
    "joongang.co.kr",
    "fnnews.com",
    "digitaltoday.co.kr",
    "uljin21.com",
    "state.gov",
    "yna.co.kr",
    "newsis.com",
    "gukjenews.com",
    "job-post.co.kr",
    "nocutnews.co.kr",
    "mk.co.kr",
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
        # 2026-08-12
        "gwon-chang-jun",
        "sin-yeong-jae",
        "hwang-yu-seong",
        "mun-yeon-cheol",
        "jo-gwang-han",
        # 2026-08-13
        "gim-gyeong-mi",
        "hwang-yeong-man",
        "won-i",
        "gim-so-hui",
        "o-se-hui",
        "jeon-hyeon-yeong",
        "sin-jin-chang",
        # 2026-08-15
        "gim-seong-je",
        "han-deuk-su",
        "ryu-gyeong-gi",
        "seo-gang-seok",
        "o-yu-gyeong",
        "i-si-won",
        "i-eun-u",
        "i-jun-ho",
        "choe-seung-hwan",
        # 2026-08-16
        "jo-hui-dae",
        "no-mu-hyeon",
        # 2026-08-17
        "bak-yong-jin",
        "bae-in-gyu",
        "i-hyeok",
        "i-tae-han",
        # 2026-08-18
        "gang-min-guk",
        "i-man-hui",
        "gim-wi-sang",
        "jo-sang-ho",
        "i-seung-don",
        "gim-ji-hyeong",
        "gwon-o-hyeon",
        "bak-jun",
        "cheon-ho-seong",
        "bak-u-ryang",
        "han-yo-sep",
        "i-hyeon-jeong",
        "jeong-dal-seong",
        "hwang-yeong-mo",
        # 2026-08-19
        "i-chang-yong",
        "yun-han-hong",
        "gim-jong-hui",
        "gim-han-jong",
        "gwon-o-sang",
        "hong-tae-yong",
        "choe-yeong-jung",
        "jo-gap-je",
        "jo-seong-hyeon",
        "ryu-yeon-seung",
        "jeong-dong-hwa",
        "choe-si-won",
        # 2026-08-20
        "gang-seong-hwi",
        "gim-yong-pan",
        "jeong-seong-ju",
        "so-byeong-hun",
        "yu-dong-su",
        "yang-ug",
        "jeon-hui-gyeong",
        "heo-jeon",
        "son-hyeon-gyu",
        "yang-o-bong",
        "myeong-tae-gyun",
        # 2026-08-21
        "jang-do-yeong",
        "jo-ho-gyeong",
        "seo-eun-yeong",
        "yu-hyo-sang",
        # 2026-08-22
        "gil-jong-seong",
        "gim-han-yeong",
        "gim-sang-hun",
        "i-cheong-hyeong",
        "jo-chan-hyeong",
        "gang-suk-hui",
        "hwang-chi-hwan",
        "jang-jeong-hui",
        "i-gi-hyeong",
        "jo-jae-gu",
        "i-dong-hun",
        # 2026-08-23
        "gwon-o-eul",
        "bak-sun-yeong",
        "choe-su-jin",
        "i-heung-gu",
        "yun-seong-sik",
        "hong-yeong-cheol",
        # 2026-08-25
        "an-jin-suk",
        "yun-yeong-hui",
        # 2026-08-26
        "gwon-chil-seung",
        "min-byeong-deok",
        "gim-jeong-ho",
        "han-min-su",
        "gim-yun",
        "gim-jong-seong",
        "gang-du-sik",
        "jeong-da-eun",
        "gim-gi-beom",
        # 2026-08-27
        "gim-in-man",
        "yun-seok-gu",
        "jang-yeong-jin",
        "bak-gyeong-mi",
        "im-seong-hun",
        "bak-han-gi",
        "mel-lani-geu-ra-di-keu",
        # 2026-08-28
        "gim-jong-ho",
        "jo-bi-yeon",
        "song-won-bae",
        "bak-mi-ok",
        # 2026-08-29
        "gim-hong-guk",
        "i-ju-yeong",
        # 2026-08-31
        "yu-dong-gyun",
        "yong-hye-in",
        "i-so-yeong",
        "gang-sin-cheol",
        "hong-ji-seon",
        "i-hae-min",
        "bang-gi-hong",
        "gim-bong-deok",
        "i-ji-eon",
        # 2026-09-01
        "bak-seong-jun",
        "baek-jin-suk",
        "i-ju-ho",
        "na-jung-gyu",
        # 2026-09-02
        "o-geon-ho",
        "han-hak-ja",
        "yang-seon-hwa",
        "i-gwang-hun",
        "choe-in-su",
        # 2026-09-03
        "choe-gyo-jin",
        "bak-hyeong-su",
        "yang-gyeong-gyu",
        "u-hui-jong",
        "gim-do-gyun",
        "heo-jang",
        "jeong-yong-rae",
        "jeong-da-un",
        "son-geum-ju",
        "gim-gyeong-dae",
        "gim-il-hwan",
        "gwon-hyeong-taek",
        "choe-gyeong-cheon",
        "choe-won-seok",
        "gim-hyo-suk",
        "jo-cheol-gi",
        "song-gyeong-ju",
        "jeong-jae-heon",
        "jeong-seon-hwa",
        "jang-seok-yeong",
        "bak-ju-hui",
        "son-gwang-yeong",
        # 2026-09-04
        "i-eun-yeong",
        "jeon-beom-il",
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


def test_issue_stance_people_links_resolve_to_ssot():
    """Publication hygiene: stance bullets must point at yaml+wiki people slugs."""
    import re

    yaml_slugs = {p.stem for p in PEOPLE_DIR.glob("*.yaml")}
    wiki_slugs = {p.stem for p in WIKI_DIR.glob("*.md") if p.stem != "_index"}
    issues_dir = ROOT / "wiki" / "content" / "issues"
    line_re = re.compile(r"\[([^\]]+)\]\(/people/([a-z0-9-]+)\)")
    block_re = re.compile(r"<!--\s*agent:stances\s*-->(.*?)<!--\s*/agent:stances\s*-->", re.S)
    broken: list[str] = []
    for md in sorted(issues_dir.glob("*.md")):
        if md.stem == "_index":
            continue
        text = md.read_text(encoding="utf-8")
        match = block_re.search(text)
        body = match.group(1) if match else text
        for name, slug in line_re.findall(body):
            if slug not in yaml_slugs or slug not in wiki_slugs:
                broken.append(f"{md.stem}:{name}:{slug}")
    assert broken == [], broken[:20]
