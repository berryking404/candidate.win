# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## Repository Contract

- `wiki/content/people/`, `wiki/content/issues/` — Agent가 쓰는 위키 출력 경로. 사람이 직접 편집한 파일은 `<!-- human-edit -->` 주석으로 표시하며, Agent는 해당 섹션을 덮어쓰지 않는다.
- `data/people/` — 인물 시드 데이터의 단일 진실 공급원(SSoT). Agent는 **신규 stub 파일을 추가**할 수 있으나, 기존 파일의 사람-큐레이팅 필드는 수정하지 않는다. stub 은 `status: stub` 으로 표시되고, 사람이 검수해 `status: curated` 로 승격한다.
- `data/issues/` — 이슈/화제 시드 데이터의 SSoT. 사람이 이슈를 정의하고, Agent는 해당 이슈에 대한 인물별 입장을 추출해 wiki 페이지로 렌더링한다. Agent는 읽기만 하되, `apply-meta` 명령어를 통해 `status`와 `conclusion`(편집자 노트)을 위키에 반영할 수 있다.
- `agent/` — Python 전용. 외부 API 키는 환경변수로만 주입, 코드에 하드코딩 금지.
- `wiki/` — Hugo 설정과 테마만 포함. 빌드 산출물(`public/`) 은 Git에 커밋하지 않는다.
- web 사용자는 GitHub에 대한 내용을 모르게 처리한다.

## Naming Conventions

| 대상 | 규칙 | 예시 |
|---|---|---|
| 인물 slug | `{성}-{이름}` 소문자 로마자 | `lee-jae-myung` |
| 인물 시드 파일 | `data/people/{slug}.yaml` | `lee-jae-myung.yaml` |
| 인물 wiki 페이지 | `wiki/content/people/{slug}.md` | `lee-jae-myung.md` |
| 이슈 slug | `{주제}-{YYYY}` 소문자 kebab-case | `real-estate-tax-2026` |
| 이슈 시드 파일 | `data/issues/{slug}.yaml` | `real-estate-tax-2026.yaml` |
| 이슈 wiki 페이지 | `wiki/content/issues/{slug}.md` | `real-estate-tax-2026.md` |
| Agent 모듈 | snake_case | `naver_news_crawler.py` |
| Git 브랜치 | `agent/run-{YYYYMMDD}` (자동생성), `feat/*`, `fix/*` | |

## Git Rules

- Agent가 자동 커밋할 때는 반드시 `[agent]` 접두사를 붙인다: `[agent] update lee-jae-myung 2026-04-29`
- 사람이 커밋할 때 `[agent]` 접두사 사용 금지.
- `public/`, `.venv/`, `__pycache__/`, `*.pyc` 는 커밋하지 않는다.

## Commands

### Wiki (Hugo)
```bash
brew install hugo          # 최초 1회
cd wiki && hugo server -D  # 개발 서버 (draft 포함)
cd wiki && hugo            # 프로덕션 빌드 → wiki/public/
```

### Agent
```bash
cd agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python deep_agent.py --person lee-jae-myung   # 단일 인물 실행
python deep_agent.py --issue real-estate-tax-2026  # 단일 이슈 실행 (관련 인물 입장 갱신)
python deep_agent.py --all                     # status: ongoing 인 이슈만 일괄 실행
python deep_agent.py --dry-run                 # 커밋 없이 출력만 확인
```

## Stance Definition Guidelines (지지/반대 판정 기준 정의 규칙)

이슈 시드(`data/issues/*.yaml`)에서 인물별 입장 분류를 결정하는 `stances.(support,oppose)`를 정의할 때는 LLM의 언어적 편향(Prior Bias)에 맞춰 동기화해야 위키 페이지에서 지지/반대 레이블이 역전되지 않습니다.

- **긍정적/정책/입법 이슈** (예: 세금 제도 개편, 정책 도입, 지역 개발 등)
  - **`support` (지지)**: 해당 정책이나 제도 도입을 **지지/찬성/옹호**하는 입장.
  - **`oppose` (반대)**: 해당 정책이나 제도 도입을 **반대/비판/거부**하는 입장.
- **부정적/논란/사건/의혹 이슈** (예: 기업의 역사 폄훼 논란, 개인정보 유출 사고, 공직자 비위/해임 논란 등)
  - **`support` (지지)**: 논란의 대상(기업/인물)을 **옹호/변호**하거나, 이에 대한 비판/보이콧/수사가 과도하다(정치적 공세다)고 주장하는 입장.
  - **`oppose` (반대)**: 논란의 대상(기업/인물)을 **비판/규탄**하거나, 이에 대한 책임 추궁/수사/해임/불매운동을 지지하는 입장.
  - *이유*: LLM(gemma4 등)은 텍스트 내에서 대상에 대한 "비판(criticize)"이나 "규탄(condemn)"을 수행하는 발언을 본능적으로 **반대(oppose)** 입장으로 분류하며, 이를 감싸거나 옹호하는 발언을 **지지(support)** 입장으로 분류하기 때문입니다.

## Architecture Summary

두 서브시스템은 Git으로만 연결된다. 설계 세부사항은 [agent/DESIGN.md](agent/DESIGN.md), 로드맵은 [ROADMAP.md](ROADMAP.md), 사용자 가이드는 [README.md](README.md) 참조.
