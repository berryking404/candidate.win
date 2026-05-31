# Candydate

정치인·언론인·인플루언서의 행적을 추적하는 오픈 위키.

LLM Agent가 뉴스와 YouTube 자막을 분석해 각 인물의 wiki 페이지를 자동으로 생성하고 갱신합니다.

## 사전 준비

| 도구 | 버전 | 용도 |
|---|---|---|
| Hugo | 0.140+ | Wiki 정적 사이트 빌드 |
| Python | 3.11+ | Agent 실행 |
| Git | - | 콘텐츠 DB |

```bash
brew install hugo
python --version  # 3.11+
```

배포는 GitHub Pages 를 사용한다. **Free 플랜에서 Pages 무료 서빙은 public repo 에서만 가능**하므로 본 저장소는 public 으로 운영한다. 따라서:
- `.env`, API 키, 크롤링 원문(`agent/.cache/`) 등 민감 정보는 절대 커밋하지 않는다 (`.gitignore` 참고).
- 인물·이슈 데이터는 공개되므로 모든 stance·event 항목에 출처 URL 을 인용한다.

## GitHub Actions 시크릿 설정

배포 전 아래 시크릿을 GitHub 저장소에 등록해야 한다.

**Settings → Secrets and variables → Actions → New repository secret**

| 시크릿 이름 | 용도 | 발급 위치 |
|---|---|---|
| `CANDYDATE_ISSUES_TOKEN` | 위키 정정·삭제 요청 폼 → GitHub Issues 자동 생성 | GitHub → Settings → Developer settings → Fine-grained personal access tokens |

`GITHUB_ISSUES_TOKEN` 발급 시 권한 설정:

- **Repository access**: `berryking404/candidate.win` 만 선택
- **Permissions → Issues**: `Read and write`
- 나머지 권한은 모두 `No access`

등록 후 `main` 브랜치에 push하면 배포 시 토큰이 자동으로 빌드에 주입된다.

## Wiki 로컬 실행

```bash
cd wiki
hugo server -D
# → http://localhost:1313
```

## Agent 실행

```bash
cd agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 에 OPENAI_API_KEY, NAVER_CLIENT_ID/SECRET 등 입력
# Kubernetes 운영 환경의 Tier 1 모델은 SGLang Gemma4:
#   TIER1_BACKEND=sglang
#   SGLANG_BASE_URL=http://sglang-gemma4-31b.llm-serving.svc.cluster.local:30000/v1
#   SGLANG_MODEL=QuantTrio/gemma-4-31B-it-AWQ

# 특정 인물 실행
python deep_agent.py --person lee-jae-myung

# 특정 이슈 실행 (관련 인물들의 입장을 갱신)
python deep_agent.py --issue real-estate-tax-2026

# 전체 이슈 실행 (각 yaml 의 status: ongoing 만; --issue 단건은 status 무관)
python deep_agent.py --all

# 커밋 없이 결과 미리 보기
python deep_agent.py --person lee-jae-myung --dry-run
```

## 새 인물 추가

1. `data/people/` 에 시드 파일 생성:

```bash
cp data/people/example.yaml data/people/{slug}.yaml
# slug = {성}-{이름} 소문자 로마자, 예: lee-jae-myung
```

2. 시드 파일 내용 작성 (아래 형식 참고):

```yaml
slug: lee-jae-myung
name_ko: 이재명
name_en: Lee Jae-myung
category: politician   # politician | journalist | influencer
aliases:
  - 이재명
  - 더불어민주당 대표
sources:
  news_keywords:
    - "이재명"
    - "민주당 대표 이재명"
  youtube_channels: []
```

3. Agent 실행:

```bash
python deep_agent.py --person {slug}
```

## 새 이슈/화제 추가

이슈는 인물 평가의 공통 축이자 **인물 발견의 진입점**이다. 사람이 이슈를 정의하면 Agent가 해당 이슈에 등장한 모든 인물을 발견·등록하고, 각자의 입장(찬성·반대·논평)을 추출해 wiki 페이지로 정리한다.

1. `data/issues/` 에 시드 파일 생성:

```bash
cp data/issues/example.yaml data/issues/{slug}.yaml
# slug = {주제}-{YYYY} 소문자 kebab-case, 예: real-estate-tax-2026
```

2. 시드 파일 내용 작성 (아래 형식 참고):

```yaml
slug: real-estate-tax-2026
title_ko: 종합부동산세 개편 논쟁 (2026)
title_en: Comprehensive Real Estate Tax Reform Debate (2026)
category: policy        # policy | scandal | election | social | foreign
status: ongoing         # ongoing | closed
started_at: 2026-01-15
summary: |
  2026년 정부의 종부세 개편안을 둘러싼 여야 입장 차이.
keywords:               # 크롤링 검색어 (필수)
  - "종부세"
  - "종합부동산세"
stances:                # (선택) 입장 판정 기준 — 없으면 이슈 제목·요약만으로 추출
  support: "종부세 폐지 또는 완화에 찬성하며 세부담 경감을 주장하는 입장"
  oppose: "종부세 유지 또는 강화를 주장하며 자산 불평등 완화를 강조하는 입장"
seed_people:            # (선택) 우선 추적할 인물 slug. 비워두면 전부 자동 발견.
  - lee-jae-myung
sources:                # (선택) 사람이 큐레이팅한 핵심 출처
  - url: https://example.com/article
    title: "정부, 종부세 개편안 발표"
    date: 2026-01-15
```

`status`는 `ongoing`(진행·추적) 또는 `closed`(종료·보관)만 쓴다. 위키 프론트매터와 `data/cli/main.py issue list --status`에만 반영되며, Agent 뉴스·유튜브 수집에는 사용되지 않는다. `deep_agent.py --all`은 `ongoing`인 이슈만 대상으로 하고, `--issue`로 지정한 단건은 status와 무관하게 실행된다.

3. Agent 실행:

```bash
python deep_agent.py --issue {slug}
```

수행 결과:
- `wiki/content/issues/{slug}.md` 생성 (이슈 요약 + 인물별 입장 표).
- 이슈에서 새로 발견된 인물에 대해 `data/people/{slug}.yaml` stub 자동 생성 (`status: stub`).
- 기존 인물의 wiki 페이지에는 "관련 이슈" 섹션이 갱신.

stub 인물은 사람이 직접 검수해 별칭·카테고리 등을 보강하고 `status: curated` 로 승격한다.

## 데이터 관리 CLI

`data/cli/main.py`는 인물·이슈 데이터와 wiki 동기화를 명령어로 관리하는 도구다. Agent를 직접 호출하지 않아도 된다.

```bash
# 의존성: pyyaml (agent 환경에 이미 포함)
python data/cli/main.py <command>
```

### 전체 현황

```bash
python data/cli/main.py status
# curated/stub 인원 수, wiki 미반영 인물 목록, 이슈 현황 출력
```

### 인물 관리

```bash
# 목록 조회
python data/cli/main.py person list
python data/cli/main.py person list --status stub
python data/cli/main.py person list --status curated

# 상세 조회
python data/cli/main.py person show i-jae-myeong

# 새 stub 추가
python data/cli/main.py person add gim-chul-su --name-ko 김철수 --party 국민의힘 --role 국회의원

# status 변경 (stub → curated 등)
python data/cli/main.py person set-status i-jae-myeong curated

# yaml 메타(status·role·party)를 wiki 프론트매터에 즉시 반영 (에이전트 불필요)
python data/cli/main.py person apply-meta

# 에이전트로 wiki 갱신 (뉴스·YouTube 크롤링 포함)
python data/cli/main.py person sync i-jae-myeong [--dry-run]

# curated 이지만 wiki 없는 인물 일괄 동기화
python data/cli/main.py person sync-pending [--dry-run]
```

### 이슈 관리

```bash
# 목록 조회
python data/cli/main.py issue list
python data/cli/main.py issue list --status ongoing

# 상세 조회
python data/cli/main.py issue show local-election-nomination-2026

# 에이전트로 이슈 wiki 갱신
python data/cli/main.py issue sync local-election-nomination-2026 [--dry-run]

# yaml 메타(status, conclusion)를 wiki에 반영 (편집자 노트 자동 생성/갱신)
python data/cli/main.py issue apply-meta

# 전체 이슈 일괄 동기화 (내부적으로 deep_agent.py --all → status: ongoing 인 이슈만)

python data/cli/main.py issue sync-all [--dry-run]
```

## 프로젝트 구조

```
candydate/
├── wiki/                   # Hugo 정적 사이트
│   └── content/
│       ├── people/         # Agent가 생성하는 인물 wiki 페이지
│       └── issues/         # Agent가 생성하는 이슈 wiki 페이지
├── agent/                  # LLM Agent 파이프라인
│   └── DESIGN.md           # Agent 설계 문서
├── data/
│   ├── people/             # 인물 시드 데이터 (SSoT)
│   ├── issues/             # 이슈/화제 시드 데이터 (SSoT)
│   └── cli/                # 데이터 관리 CLI (main.py)
├── ROADMAP.md              # 개발 로드맵
└── AGENTS.md               # 코딩 에이전트 운영 규칙
```

## 정정·삭제 요청

본 위키는 실명 인물의 발언·행적을 다루므로 사실관계 오류나 삭제 요청은 **GitHub Issues 단일 채널**로 접수한다 (별도 폼·이메일 없음).

- 사실관계 정정: [`correction` 템플릿](../../issues/new?template=correction.yml) — 대상 페이지 URL, 정정 내용, 근거 출처를 함께 제출
- 삭제 요청: [`takedown` 템플릿](../../issues/new?template=takedown.yml) — 대상 페이지 URL, 본인 확인 가능한 정보, 삭제 사유

처리 SLA: 1차 응답 7일 / 처리 완료 30일 (영업일 기준). 처리된 변경은 commit 에 `Closes #N` 으로 연결되어 이력이 공개된다.

## 라이선스

- **코드** (`agent/`, `wiki/layouts/`, `wiki/hugo.toml` 등): [MIT](LICENSE)
- **콘텐츠** (`wiki/content/`, `data/people/`, `data/issues/`): [CC BY-NC 4.0](LICENSE-content) — 학술·언론 인용 허용, 상업적 이용 금지
