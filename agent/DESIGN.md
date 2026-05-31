# Agent System Design

## 개요

Agent는 LangChain의 [DeepAgents](https://docs.langchain.com/oss/python/deepagents/) 라이브러리(`pip install deepagents`) 기반의 LLM 에이전트이다. 뉴스 기사와 YouTube 자막을 원천으로 두 종류의 wiki post를 생성·갱신한다.

1. **인물 페이지** — 각 인물의 행적·발언 기록.
2. **이슈 페이지** — 사람이 정의한 이슈/화제에 대한 인물별 입장(찬성·반대·중립·혼합) 정리.

두 페이지는 양방향으로 링크된다. 인물 페이지에는 "관련 이슈" 섹션, 이슈 페이지에는 "인물별 입장" 섹션이 자동 생성된다.

## DeepAgents 런타임

LangGraph 위에서 동작하는 에이전트 하네스로, 다음 빌트인 도구를 기본 제공한다.

| 빌트인 도구 | 용도 |
|---|---|
| `ls`, `read_file`, `write_file`, `edit_file` | 파일시스템 (wiki 마크다운 읽기·패치에 직접 사용) |
| `write_todos` | 작업 분해/계획 (인물·이슈 갱신 단계 추적) |
| `task` | 서브에이전트 호출 (인물별·이슈별 컨텍스트 격리) |

따라서 wiki 페이지 입출력은 자체 도구를 만들지 않고 빌트인 `read_file` / `edit_file` 을 그대로 사용한다. 우리가 추가로 정의하는 도구는 외부 데이터 수집·구조화에 한정된다 (아래 "커스텀 도구" 절 참고).

진입점은 `create_deep_agent()` 이다.

```python
from deepagents import create_deep_agent
from candydate_agent.tools import (
    crawl_news, crawl_youtube,
    find_participants, register_person,
    extract_events, extract_stance,
    read_agent_section, write_agent_section,
    commit_changes,
)

SYSTEM_PROMPT = """당신은 정치인·언론인·인플루언서의 행적과 이슈별 입장을
추적하는 위키 편집 에이전트이다. ..."""

# 오케스트레이터는 OpenAI GPT-5.4 mini (sync, auto prompt cache).
# 도구 내부의 무거운 텍스트 처리는 Tier 1 백엔드(SGLang/Ollama)에서 종료되고,
# stance escalation 은 Tier 2-batch (GPT-5.4 via Batch API) 로 비동기 처리.
# 자세한 비용·실행 전략은 "비용·모델 전략" 절 참고.
agent = create_deep_agent(
    model="openai:gpt-5.4-mini",
    tools=[
        crawl_news, crawl_youtube,
        find_participants, register_person,
        extract_events, extract_stance,
        read_agent_section, write_agent_section,
        commit_changes,
    ],
    system_prompt=SYSTEM_PROMPT,
)

# Pass A — research (sync). escalation 후보를 batch buffer 로 enqueue.
agent.invoke({"messages": [{"role": "user", "content": "research lee-jae-myung"}]})

# Phase B/C 는 별도 실행 (publishers/batch_submitter.py 가 OpenAI Batch 제출·polling).

# Pass D — apply (sync). batch 결과가 LLM 캐시에 적재된 상태에서 호출.
agent.invoke({"messages": [{"role": "user", "content": "apply stances for lee-jae-myung"}]})
```

> 오케스트레이터는 도구 결과의 **구조화된 요약**(JSON, 짧은 텍스트)만 받는다. 50KB 짜리 자막 원문이 SOTA 컨텍스트에 들어가는 일은 없다.

## 데이터 흐름

```
data/people/{slug}.yaml          (시드: 인물 정의 — 사람 큐레이팅 + agent stub)
data/issues/{slug}.yaml          (시드: 이슈/화제 정의 — 사람만 작성)
        │
        ▼
[Crawler]  ──────────────────────────────────────────────┐
  naver_news.py   → 뉴스 기사 HTML/RSS                   │
  youtube_transcript.py → 유튜브 자막 텍스트              │
        │ 키워드: 인물 aliases (인물 모드) 또는           │
        │         이슈 keywords (이슈 모드)               │
        ▼                                                  │
[Processor]                                               │
  dedup.py        → URL/내용 기반 중복 제거               │
  chunker.py      → 키워드 ±N문장 윈도우만 잘라냄 [Tier 0]│
  ner_kr.py       → 한국어 NER 로 인명 후보 추출 [Tier 0] │
  participant_finder.py → 인물 후보 정규화·매칭 [Tier 1]  │
  extractor.py    → 행적 문장 추출 [Tier 1]               │
  stance_extractor.py → 입장 추출 [Tier 1→2 escalation]   │
        │                                                  │
        ▼                                                  │
[DeepAgents 런타임 (create_deep_agent)]                    │
  이슈 모드:                                              │
    1. crawl_news/youtube 로 텍스트 수집                  │
    2. find_participants 로 등장한 인물 후보 추출         │
    3. 미등록자는 register_person 으로 stub 생성          │
       (data/people/{slug}.yaml, status: stub)            │
    4. extract_stance 로 인물별 입장 추출                 │
    5. write_agent_section 으로 이슈/인물 페이지 섹션 갱신│
  인물 모드:                                              │
    1. crawl_* + extract_events 로 행적 추출              │
    2. write_agent_section 으로 인물 페이지 섹션 갱신     │
  공통:                                                   │
    - write_todos 로 단계 추적                            │
    - task 로 인물별 컨텍스트 격리 (선택)                 │
    - <!-- human-edit --> 블록 보존                       │
        │                                                  │
        ▼                                                  │
[Publisher]                                               │
  git_committer.py    → [agent] 커밋 자동 생성            │
        │                                                  │
        ▼                                                  │
data/people/{slug}.yaml          (신규 stub 추가)
wiki/content/people/{slug}.md    (인물 wiki 페이지)
wiki/content/issues/{slug}.md    (이슈 wiki 페이지)
```

## 커스텀 도구 정의

DeepAgents 빌트인(`read_file` / `write_file` / `edit_file` / `write_todos` / `task`)으로는 충당되지 않는 외부 데이터 수집과 LLM 구조화 단계만 별도 함수로 정의한다. 각 도구는 docstring + 타입 힌트를 갖춘 일반 Python 함수로 작성하고 `tools=[...]` 로 `create_deep_agent` 에 전달한다.

| 도구 | 입력 | 출력 | 내부 모델 | 설명 |
|---|---|---|---|---|
| `crawl_news` | keywords, date_range | `[{url, title, text, date}]` | — | 뉴스 크롤링 |
| `crawl_youtube` | keywords, channel_ids | `[{video_id, title, transcript}]` | — | 유튜브 자막 수집 |
| `find_participants` | raw_texts, issue_slug | `[{name_ko, role_hint, mention_count, sample_quote}]` | Tier 0 NER + Tier 1 | 자막·기사에서 발언자 후보 추출. 청킹 후 Tier 1 모델이 최종 정규화. mention_count ≥ 2 인 인물만 반환 (matched_slug 우회 제거) |
| `register_person` | name_ko, aliases, category, discovered_via_issue | `{slug, created: bool, pending: bool, rejected: bool}` | — (순수 파일 I/O) | stub YAML 생성, 실명 검증(`_is_valid_person_name`), curated slug 불일치 해결(`_find_existing_slug`), 동명이인 검출 순으로 처리 |
| `create_wiki_page` | kind, slug, title, summary | `{created: bool, path: str}` | — | wiki 페이지 초안 생성. slug 에 비ASCII 문자 포함 시 즉시 거부하여 한글 파일명 생성 차단 |
| `extract_events` | raw_texts, person_slug | `[{date, event, source_url}]` | Tier 1 | 행적 이벤트 추출 |
| `extract_stance` | raw_texts, person_slug, issue_slug | `{position, summary, quotes[], confidence}` | Tier 1 → Tier 2 SOTA escalation | 입장 추출. 1차 Tier 1 결과의 confidence 가 임계값 미만이면 SOTA 재호출 |
| `read_agent_section` | kind, slug, section_id | `{content, exists: bool}` | — | wiki 페이지에서 `<!-- agent:section_id -->` 블록 본문만 추출해 반환. 페이지 전체를 컨텍스트에 올리지 않기 위함 |
| `append_agent_stances` | kind, slug, new_content | `{written: bool, diff_lines: int}` | — | 기존 `agent:stances` 를 읽은 뒤 `new_content` bullet 을 병합·저장. 이슈 페이지는 `/people/{slug}`+**입장**, 인물 페이지는 `/issues/{issue_slug}`+**입장** 조합이 이미 있으면 동일 조합 incoming 줄 생략 (`publishers/stance_merge.py`) |
| `write_agent_section` | kind, slug, section_id, content | `{written: bool, diff_lines: int}` | — | `section_id=stances` 는 `append_agent_stances` 와 동일(병합). 그 외(`events` 등)는 블록을 `content` 로 정규식 치환. 마커 없으면 거부 |
| `commit_changes` | summary | commit_sha | — | Git 커밋 |

> **빌트인 `read_file` / `edit_file` 은 wiki 페이지에 사용하지 않는다.** 페이지 전체를 LLM 컨텍스트에 노출하면 입력 토큰이 폭증하므로, 위키 마크다운 입출력은 위 두 자체 도구로 강제한다. 빌트인 파일 도구는 `data/`(YAML 시드), `agent/.cache/`(캐시 점검) 등 디버깅 용도에만 허용한다.

## 비용·모델 전략 (Tiered Model Architecture)

목표: 1시간 자막(약 30k~50k 토큰)이 SOTA 모델에 절대 통째로 들어가지 않도록 한다. 무거운 텍스트는 모두 무료 계층에서 처리하고, SOTA 호출은 (a) 오케스트레이터의 짧은 메시지와 (b) Tier 1 이 자신 없을 때의 escalation 만으로 한정한다.

### 계층 정의

| Tier | 무엇 | 어디에 사용 | 비용 |
|---|---|---|---|
| **Tier 0** | 정규식 + 한국어 NER (`kiwipiepy`) + 룰베이스 | 청킹, 인명 후보 추출, 키워드 매칭, 날짜 정규화 | 무료 (로컬 CPU) |
| **Tier 1** | Ollama 로컬 LLM 또는 SGLang OpenAI-compatible endpoint (`TIER1_BACKEND`) | `find_participants` 정규화, `extract_events`, `extract_stance` 1차 분류 | 로컬/클러스터 GPU |
| **Tier 2-sync** | OpenAI **GPT-5.4 mini** (sync, auto prompt cache) | DeepAgents 오케스트레이터 — 짧은 메시지·도구 디스패치 | $0.75/$4.50 MTok, 캐시 히트 시 입력 -90% |
| **Tier 2-batch** | OpenAI **GPT-5.4** via **Batch API** (async, 24h SLA) | Tier 1 confidence 미달 시 stance 재분석 (대량) | $2.50/$15.00 MTok × **Batch -50%** + 캐시 -90% 결합 가능 |

OpenAI 를 Tier 2 로 채택한 이유:
1. **자동 prompt caching**: 같은 system_prompt 가 매 호출 반복되는 본 워크로드에서 입력 토큰의 ~90% 가 캐시 히트가 되어 실효 단가가 폭락.
2. **Batch API -50%**: 매일 cron 으로 도는 비실시간 워크로드라 24h SLA 가 완전히 무해.
3. 둘 결합 시 GPT-5.4 의 실효 입력 비용이 $0.125/MTok 수준까지 떨어짐 (Sonnet 4.6 대비 ~96% 절감).

> 소비자 ChatGPT Plus/Pro 구독은 API 와 별개 — 본 빌링은 OpenAI Platform 계정의 사용량 기반 충전을 사용한다.

### 텍스트 부피 절감 (Tier 0 청킹)

`processors/chunker.py` 가 LLM 호출 직전 모든 원문을 다음 규칙으로 압축한다.

```python
def chunk(text: str, keywords: list[str], window_sentences: int = 2) -> list[str]:
    """키워드가 등장하는 문장의 ±window_sentences 만 모은 chunk 리스트."""
```

- 자막은 흔히 90% 이상이 무관한 잡담·광고. 정치인 이름이나 이슈 키워드 ±2문장만 남기면 통상 5~10% 부피로 감소.
- 청크가 너무 적으면(키워드 미등장) Tier 1 호출 자체를 생략 — 호출 0건이면 비용 0.

### Tier 1 모델 백엔드

`models.get_tier1_model()` 은 `TIER1_BACKEND` 로 백엔드를 선택한다.

#### Kubernetes 운영: SGLang Gemma4

SGLang은 OpenAI-compatible `/v1/chat/completions` 엔드포인트를 제공하므로 `langchain_openai.ChatOpenAI` 어댑터를 사용한다.

```bash
TIER1_BACKEND=sglang
SGLANG_BASE_URL=http://sglang-gemma4-31b.llm-serving.svc.cluster.local:30000/v1
SGLANG_MODEL=QuantTrio/gemma-4-31B-it-AWQ
SGLANG_API_KEY=EMPTY
```

#### 로컬 개발: Ollama

```python
from langchain_ollama import ChatOllama

OLLAMA_MODEL = ChatOllama(
    model="exaone3.5:7.8b",      # 환경변수 TIER1_MODEL 또는 OLLAMA_MODEL 로 교체 가능
    temperature=0.0,
    num_ctx=8192,
)
```

- 도구 함수는 LangChain 모델 객체를 직접 보유하고 호출. DeepAgents 오케스트레이터는 도구의 반환값(JSON)만 봄 → 오케스트레이터 컨텍스트에 자막 원문이 절대 누설되지 않음.
- Kubernetes 환경에는 Ollama가 없으므로 `TIER1_BACKEND=sglang` 을 사용한다. 로컬 개발자는 기존처럼 `TIER1_BACKEND=ollama` 또는 미설정 기본값으로 Ollama를 사용할 수 있다.

### Escalation 정책 (Tier 1 → Tier 2-batch)

`extract_stance` 만 escalation 대상이다. Tier 1 출력에 다음 중 하나가 충족되면 해당 (청크, 인물, 이슈) 튜플을 **batch buffer 에 enqueue** 한다 (즉시 SOTA 호출하지 않음).

- `confidence < 0.7` (Tier 1 이 자체 보고)
- `position == "mixed"` 또는 인용문 0개
- 같은 청크에서 `support` 와 `oppose` 가 동시에 나옴 (Tier 1 혼동)

Escalation 도 청크 단위라 한 인물·이슈당 평균 1~2회를 넘지 않는다. 운영 중 escalation 비율을 메트릭으로 노출 (`agent/.logs/escalation_rate.json`) 해 Tier 1 모델 교체 판단에 사용.

### 비동기 2-pass 실행 (Batch API 통합)

OpenAI Batch API 는 24시간 SLA 의 비동기 처리이므로 단일 `agent.invoke()` 안에서 결과를 받을 수 없다. 실행을 두 패스로 분리한다.

```
Pass A — research (sync)
  agent.invoke({"role":"user","content":"research <slug>"})
  ├ crawl_news / crawl_youtube
  ├ Tier 0 chunking
  ├ Tier 1 find_participants / extract_events
  ├ Tier 1 stance 1차 분류
  └ enqueue 미달 항목 → agent/.cache/batch/pending.jsonl
[Phase B — submit]
  publishers/batch_submitter.py
    POST /v1/batches → batch_id 저장 (.cache/batch/active.json)
[Phase C — poll & ingest]
  polling 또는 OpenAI webhook (보통 <1h, 최대 24h)
  완료 시 결과를 agent/.cache/llm/extract_stance/ 에 적재 (= 일반 LLM 캐시와 동일 키)
Pass D — apply (sync)
  agent.invoke({"role":"user","content":"apply stances for <slug>"})
  ├ extract_stance 호출 시 LLM 캐시 hit (Phase C 가 채움)
  ├ write_agent_section(section_id="stances") 내부에서 Pass E 자동 실행
  │   └ publishers/quality_gate.py — validate_stances()
  │       ├ Rule 1: URL 없는 비-미확인 → 미확인 강등
  │       ├ Rule 2: URL·캐시 있고 인용문-원문 불일치 → 미확인 강등
  │       └ Rule 3: URL 있고 캐시 미스 → 경고만, 강등 없음
  └ commit_changes
```

**macOS launchd** 로 두 잡을 분리해 로컬 PC 에서 트리거한다. Pass A+B 는 09:00 KST, Pass D 는 14:00 KST (Phase C polling 후 적용). batch 가 아직 미완이면 Pass D 는 retry 큐에 넣고 다음 주기에 재시도.

구현 파일 (`agent/launchd/`):

| 파일 | 역할 |
|---|---|
| `com.candydate.research.plist` | launchd 잡 정의 — 09:00 KST, `run_pass_ab.sh` 실행 |
| `com.candydate.apply.plist` | launchd 잡 정의 — 14:00 KST, `run_pass_d.sh` 실행 |
| `run_pass_ab.sh` | `.env` + `.venv` 로드 → `deep_agent.py --all` → `deep_agent.py --batch-submit` |
| `run_pass_d.sh` | `.env` + `.venv` 로드 → `deep_agent.py --batch-apply` (종료코드 1=미완료, 42=CB 트립) |

공통 로그: `/tmp/com.candydate.agent.log` (stdout + stderr 동일 파일). 등록:

```bash
ln -sf ~/Documents/works/candydate/agent/launchd/com.candydate.research.plist \
       ~/Library/LaunchAgents/com.candydate.research.plist
ln -sf ~/Documents/works/candydate/agent/launchd/com.candydate.apply.plist \
       ~/Library/LaunchAgents/com.candydate.apply.plist
launchctl load ~/Library/LaunchAgents/com.candydate.{research,apply}.plist
```

> **GitHub Actions 미사용 이유**: Tier 1 백엔드는 GPU 추론이 필요하다. 표준 GitHub Actions 러너에는 GPU가 없어 CPU 추론 속도(2~5 token/sec)로는 30분 Circuit Breaker를 초과한다. 운영 환경에서는 Kubernetes SGLang 서비스, 로컬 개발에서는 Ollama를 사용한다. Batch API는 어떤 환경에서도 OpenAI 서버에 HTTP 요청만 보내면 되므로 실행 환경에 무관하다.

`--no-batch` 플래그를 두면 escalation 도 동기로 처리 (개발·테스트용, Batch 50% 할인 포기).

### 품질 검수 게이트 (Pass E)

`append_agent_stances` 및 `write_agent_section(section_id="stances")` 에서 기존 블록과 `publishers/stance_merge.py` 로 병합한 뒤, 저장 직전에 `publishers/quality_gate.validate_stances()` 가 실행된다. 별도 CLI 플래그나 파이프라인 변경 없이 `tools.py` 한 곳에서 처리된다.

#### 검증 규칙

| Rule | 조건 | 처리 |
|---|---|---|
| **1** | 비-미확인 stance에 출처 URL 없음 | 미확인(미확인)으로 강등, URL 제거 |
| **2** | URL 있고 `.cache/sources/` 캐시 히트 + 인용문-원문 불일치 | 미확인으로 강등 |
| **3** | URL 있고 캐시 미스 (미수집 출처) | 경고 로그만, 강등하지 않음 |

- **미확인 stance**: 원래부터 `position: 미확인` 이면 Rule 적용 대상 제외.
- **캐시 키**: Naver 기사 → `sha256(url)[:16].txt`, YouTube → `{video_id}.txt` (`.cache/sources/` 하위).
- **텍스트 매칭 (Rule 2)**: 요약문에서 구두점·공백을 제거한 뒤 10자 슬라이딩 윈도우 구절이 원문에 하나라도 포함되면 통과.

#### 로그

강등 발생 시 `agent/.logs/quality_gate.json` 에 누적한다.

```json
[
  {
    "slug": "corporate-labor-dispute-2026",
    "name": "홍길동",
    "original_position": "지지",
    "reason": "출처 URL 없음",
    "url": null,
    "at": "2026-05-05T07:54:33+00:00"
  }
]
```

#### ROADMAP 108번과의 관계

ROADMAP "모든 stance·event 항목에 출처 URL 인용 의무화" 요건이 Rule 1 로 자동 충족된다. Hugo 렌더는 이미 `position: 미확인` 항목을 숨기므로, 근거 없는 stance 는 write 단계에서 강등되어 사이트에 노출되지 않는다.

### 일일 비용 추정 (참고, 자막 1h × 인물 100명 × 매일 부하 가정)

| 구성 | 입력 단가 (실효) | 출력 단가 | 일일 비용 |
|---|---|---|---|
| naive Sonnet 4.6 | $3.00/MTok | $15.00/MTok | $50~$100 |
| 본 설계 (Tier 0/1 + Tier 2 = Sonnet sync) | $3.00 | $15.00 | $1~$3 (escalation 만 SOTA) |
| **본 설계 (Tier 2 = GPT-5.4 + Batch -50% + 캐시 -90%)** | **~$0.125** | **~$7.50** | **$0.2~$0.6** |

Batch + 캐시 결합 시 naive 대비 **약 99% 절감**, sync Sonnet 안 대비도 추가 75~80% 절감.

Naive 대비 **약 95~98% 비용 절감**이 목표치다.

## Incremental Update 전략 (입출력 토큰 동시 절감)

전체 페이지 재생성 없이 섹션 단위로 패치한다. 목표는 세 가지:

1. **출력 토큰 절감** — 변경된 블록만 새로 생성.
2. **입력 토큰 절감** — 페이지 전체를 LLM 컨텍스트에 노출하지 않음.
3. **인간 편집 보존** — `<!-- human-edit -->` 블록은 절대 건드리지 않음.

### 마커 컨벤션

```markdown
<!-- agent:events -->
## 최근 행적
...agent-generated content...
<!-- /agent:events -->

<!-- agent:related-issues -->
## 관련 이슈
...stance badges...
<!-- /agent:related-issues -->

<!-- human-edit -->
## 편집자 노트
...human content preserved...
<!-- /human-edit -->
```

- 모든 agent 관리 섹션은 `<!-- agent:{section_id} --> ... <!-- /agent:{section_id} -->` 쌍으로 마킹.
- 페이지당 다수 섹션을 가질 수 있으며, 각 섹션은 독립적으로 패치된다.

### 컨텍스트 격리 (입력 토큰 폭증 방지)

LLM 에이전트가 위키 페이지를 직접 `read_file` 하는 것을 금지한다. 대신 Python 도구가 정규식으로 해당 섹션만 추출해 LLM 에 넘기고, 결과를 다시 같은 위치에 끼워 넣는다.

```python
# tools.py — 의사 코드
SECTION_RE = re.compile(
    r"<!--\s*agent:(?P<id>[\w\-]+)\s*-->(?P<body>.*?)<!--\s*/agent:(?P=id)\s*-->",
    re.DOTALL,
)

def read_agent_section(kind: str, slug: str, section_id: str) -> dict:
    text = (WIKI_ROOT / kind / f"{slug}.md").read_text()
    for m in SECTION_RE.finditer(text):
        if m.group("id") == section_id:
            return {"content": m.group("body").strip(), "exists": True}
    return {"content": "", "exists": False}

def write_agent_section(kind: str, slug: str, section_id: str, content: str) -> dict:
    path = WIKI_ROOT / kind / f"{slug}.md"
    text = path.read_text()
    new_block = f"<!-- agent:{section_id} -->\n{content}\n<!-- /agent:{section_id} -->"
    new_text, n = re.subn(
        rf"<!--\s*agent:{section_id}\s*-->.*?<!--\s*/agent:{section_id}\s*-->",
        new_block, text, count=1, flags=re.DOTALL,
    )
    if n == 0:
        return {"written": False, "diff_lines": 0}  # 마커 없음 → 안전 거부
    path.write_text(new_text)
    return {"written": True, "diff_lines": new_text.count("\n") - text.count("\n")}
```

- 에이전트 시야에 들어오는 텍스트는 해당 섹션 본문(보통 수백~수천 자)뿐. 페이지 나머지는 보이지 않음.
- 마커가 없는 페이지에 대한 `write_agent_section` 호출은 거부됨 → 인간 편집 영역 침범 불가.
- `<!-- human-edit -->` 블록은 정규식 패턴에서 원천적으로 매칭되지 않음.

## 인물 식별 (Entity Resolution)

동명이인·별칭 문제를 방지하기 위해 `data/people/{slug}.yaml` 의 `aliases` 목록을 사용한다.

- 인물 모드 크롤링: aliases 중 하나라도 포함된 기사만 수집.
- 추출 단계: 컨텍스트를 다시 확인해 오귀속(false attribution)을 필터링.

### 신규 인물 자동 등록 (Discovery via Issue)

이슈 모드에서는 사전에 등록된 인물 외에도 텍스트에 등장한 모든 발언자를 추적 대상으로 삼는다. 흐름은 다음과 같다.

1. `find_participants` 가 이슈 관련 텍스트에서 발언·입장 표명이 있는 인물 후보를 모은다 (mention_count ≥ 2 필터). 이슈의 주체(해임·비판 대상)와 실제 발언자를 구별하도록 `PARTICIPANTS_PROMPT` (v2) 에 명시적 규칙이 있다.
2. 후보 이름을 기존 `data/people/*.yaml` 의 `name_ko` 및 `aliases` 와 매칭한다.
3. 매칭 실패 + mention 횟수 ≥ 임계값(기본 2) 시 `register_person` 으로 stub 생성. `register_person` 내부 처리 순서:
   a. `_is_valid_person_name()` — 한국 성씨 목록 검사 + 조직명 키워드 필터 (단체·직책명 거부)
   b. `_find_existing_slug()` — 동일 `name_ko` 를 가진 기존 파일을 먼저 확인 (romanizer 표기 vs curated 표기 불일치 케이스 처리)
   c. `_has_duplicate()` — 위 두 단계를 통과한 경우만 동명이인 여부 검사

```yaml
# data/people/{slug}.yaml — agent 가 생성한 stub 예시
slug: park-eun-jung
name_ko: 박은정
name_en: null            # 사람이 검수하며 채움
category: politician     # find_participants 의 role_hint 기반 추정
status: stub             # stub | curated
aliases:
  - 박은정
discovered_via_issue: real-estate-tax-2026
discovered_at: 2026-04-29
sources:
  news_keywords:
    - "박은정"
  youtube_channels: []
```

- `status: stub` 인 인물은 wiki 페이지 생성 시 "검수 필요" 배지가 붙는다.
- 사람이 검수해 별칭·카테고리 등을 보강하고 `status: curated` 로 승격하면 일반 인물처럼 취급된다.
- Agent 는 기존 `curated` 인물 파일을 절대 수정하지 않는다. `stub` 인물의 경우에도 `aliases`/`sources` 같은 큐레이션 필드는 사람이 검수한 뒤 잠긴다.
- 동명이인 의심(이미 같은 `name_ko` 의 인물이 존재) 시 stub 을 만들지 않고 `data/people/_pending/` 에 후보 정보를 기록한 뒤 사람의 disambiguation 을 기다린다.

## 이슈 모델 (Issue & Stance)

이슈는 인물 평가의 공통 축이자 **인물 발견의 진입점**이다. 사람이 `data/issues/{slug}.yaml` 로 이슈를 정의하면, Agent 는 이슈 텍스트에 등장하는 모든 발언자를 발견·등록(stub 생성)하고 각자의 입장을 추출한다. 즉, 사람이 인물을 미리 등록하지 않아도 이슈 한 건만 정의하면 관련 인물 군이 자동 확장된다.

### 이슈 시드 스키마 (`data/issues/{slug}.yaml`)

```yaml
slug: real-estate-tax-2026
title_ko: 종합부동산세 개편 논쟁 (2026)
title_en: Comprehensive Real Estate Tax Reform Debate (2026)
category: policy        # policy | scandal | election | social | foreign
status: ongoing         # ongoing | closed
started_at: 2026-01-15
summary: |
  2026년 정부의 종부세 개편안을 둘러싼 여야 입장 차이.
keywords:               # (필수) 크롤링용 검색어
  - "종부세"
  - "종합부동산세"
stances:                # (선택) 입장 판정 기준 (일관성 확보용)
  support: "종부세 폐지 또는 완화에 찬성하며 세부담 경감을 주장하는 입장"
  oppose: "종부세 유지 또는 강화를 주장하며 자산 불평등 완화를 강조하는 입장"
seed_people:            # (선택) 우선 추적할 인물 slug. 비워두면 전부 자동 발견.
  - lee-jae-myung
sources:                # (선택) 사람이 큐레이팅한 핵심 출처
  - url: https://example.com/article
    title: "정부, 종부세 개편안 발표"
    date: 2026-01-15
```

> `status`는 `ongoing` | `closed` 두 값만 쓴다. 위키 이슈 페이지 프론트매터와 `data/cli/main.py issue list --status`에 대응한다. `deep_agent.py --all`은 `ongoing`인 이슈만 순회한다(`--issue` 단건은 status 무관). Agent의 이슈 조사 쿼리(`_issue_context`)에는 포함되지 않아 수집 범위·키워드에 영향을 주지 않는다.

> 이전 스키마의 `related_people:` 은 "이 명단에 있는 사람만 추적"하는 화이트리스트였다. 새 모델에서는 `seed_people:` 로 이름이 바뀌고 의미도 "우선순위 힌트"로 약화된다 — 명단에 없는 인물도 텍스트에 등장하면 자동 등록 후 추적된다.
> `stances` 필드는 입장 추출 시 LLM에게 제공되는 명시적 가이드라인이다. 이를 통해 뉴스 맥락에 따라 지지/반대 판정이 역전되는 문제를 방지하고 일관된 데이터를 유지.

### 입장(stance) 분류

`extract_stance` 는 다음 중 하나의 `position` 값을 반환한다. YAML에 정의된 `stances` 기준이 있을 경우 이를 최우선으로 적용한다.

| position | 의미 |
|---|---|
| `support` | 명시적 지지·찬성 |
| `oppose` | 명시적 반대 |
| `neutral` | 중립·관망 |
| `mixed` | 부분 지지/부분 반대, 또는 조건부 입장 |
| `unknown` | 발언 근거 불충분 (페이지에 노출하지 않음) |

각 stance 는 반드시 1개 이상의 `quotes[]` (출처 URL + 발췌 인용) 를 포함해야 한다. 근거 없는 입장 귀속은 hallucination 으로 간주해 폐기한다.

### 양방향 렌더링

- **이슈 페이지 (`wiki/content/issues/{slug}.md`)** — 이슈 요약 + "인물별 입장" 표/섹션 (인물 페이지로 링크).
- **인물 페이지 (`wiki/content/people/{slug}.md`)** — 기존 행적 섹션 + "관련 이슈" 섹션 (이슈 페이지로 링크, position 뱃지 포함).

두 섹션 모두 `<!-- agent:stances -->` ~ `<!-- /agent:stances -->` 블록으로 마킹되어 섹션 단위 패치가 가능하다.

## 외부 API quota (YouTube Data API v3)

자막 본문은 `youtube-transcript-api` / `yt-dlp` 가 키 없이 처리하므로 무료. 하지만 **채널 영상 발견·메타데이터 조회** 단계는 YouTube Data API v3 를 쓴다.

### 비용 구조

- 무료 quota: **일 10,000 units / 프로젝트** (Google Cloud).
- 단가: `search.list` = 100 units, `videos.list` / `channels.list` = 1 unit 등.
- 본 프로젝트 표준 사이클(인물 100명 × 채널 폴링) ≈ 10,000 units → quota 한도에 정확히 닿음. 인물 200명을 넘기면 한도 초과.

### 가드레일

`quotas/youtube.py` 가 모든 호출을 가로채 다음을 강제한다.

- 매 호출 직전 `units_used` 누적 → 80% 초과 시 경고 로그, 100% 도달 시 `QuotaExhausted` 예외.
- 일일 카운터는 `agent/.cache/quota/youtube_{YYYYMMDD}.json` 에 기록.
- 채널 신규 영상 폴링은 가능하면 **채널 RSS** (`/feeds/videos.xml?channel_id=...`, quota 무관) 우선 사용. RSS 가 누락된 경우만 `search.list` 폴백.
- `--no-youtube` 플래그로 단일 실행에서 YouTube 호출 자체를 차단.

### 확장 트리거

다음 중 둘 이상 충족 시 quota 증액 요청 (Google Cloud Console, 무료, 심사 필요).

- 7일 평균 사용률 > 70%
- 단일 일자에 `QuotaExhausted` 트립 발생
- 추적 인물 수 > 150명

## LLM 결과 캐싱 (Response Cache)

원문 캐싱(`agent/.cache/sources/`)으로는 부족하다. 같은 기사를 재처리하거나 로직 변경으로 재실행할 때 동일한 LLM 호출이 반복되면 토큰만 태운다. **모든 LLM 호출(Tier 1/2)의 결과를 영속 캐시에 저장**한다.

### 캐시 키

```
sha256(
    tool_name +    # "extract_events" 등
    model_id +     # "ollama:qwen2.5:7b" or "anthropic:claude-sonnet-4-6"
    prompt_version + # 프롬프트 버전 (변경 시 캐시 자동 무효화)
    input_text +   # 청킹된 입력 텍스트
    extra_args     # person_slug, issue_slug 등
)
```

### 저장 위치

```
agent/.cache/llm/
  ├── extract_events/
  │   └── {key_prefix}/{full_key}.json
  ├── extract_stance/
  └── find_participants/
```

값에는 `{result, model_id, prompt_version, created_at, input_token_count, output_token_count}` 를 함께 저장 → 추후 비용 분석에 사용.

### 무효화 (Invalidation)

- **prompt_version 자동 무효화**: `prompts.py` 의 각 프롬프트 상수 옆에 `VERSION = "v3"` 같은 토큰을 두고 키에 포함. 프롬프트를 수정하면 자연스럽게 캐시 미스.
- **TTL 없음 (기본값)**: 같은 입력 → 같은 출력. 정치 발언 데이터는 사실상 불변이므로 무한 캐싱이 안전.
- **수동 무효화**: `python deep_agent.py --invalidate-cache extract_stance` 로 도구별 일괄 삭제.
- 캐시 hit 시 `agent/.logs/cache_hit_rate.json` 에 기록.

### 적용 범위

- Tier 1: 토큰 비용은 0이지만 GPU 시간 절약 효과 → 캐싱 적용.
- Tier 2 (SOTA): 직접적인 $ 절감 → 캐싱 필수 적용.
- 오케스트레이터 LLM 호출(메시지 단위)은 캐싱하지 않음 (대화 흐름이 매번 다름).

## Circuit Breaker (안전 한도)

이슈 ↔ 인물 양방향 확장과 stub 자동 등록은 자칫 폭주하면 한 번의 GitHub Actions 실행으로 수천 명의 stub 과 수천 달러의 청구서를 만든다. **하드 리미트를 코드에 못박는다.**

### 한도 정의

`agent/limits.py` 에 단일 진실 공급원으로 보관.

```python
@dataclass(frozen=True)
class RunLimits:
    max_new_stubs: int = 5            # 1회 실행당 신규 인물 stub 생성 상한
    max_tier2_usd: float = 1.0        # 1회 실행당 Tier 2 (SOTA) 비용 상한
    max_tier2_calls: int = 50         # 1회 실행당 Tier 2 호출 횟수 상한
    max_wallclock_minutes: int = 30   # 1회 실행 총 시간 상한
    max_pages_modified: int = 200     # 1회 실행당 wiki 페이지 수정 상한
```

CLI 플래그(`--max-stubs`, `--cost-cap`, `--max-calls`, `--time-cap`, `--max-pages`) 또는 환경변수(`CANDYDATE_MAX_STUBS` 등)로 덮어쓸 수 있으나, 기본값은 의도적으로 보수적이다.

### 트리핑(Tripping) 동작

각 도구 호출 직전 `limits.py` 의 누적 카운터를 점검한다. 한도 초과 시 즉시 `LimitExceeded` 예외를 던지고:

1. 오케스트레이터에는 도구 결과로 명시적인 에러 메시지를 반환 (조용히 실패하지 않음).
2. 진행 중이던 작업은 현재까지의 부분 결과를 커밋 (`[agent] partial: hit max_new_stubs limit`).
3. `agent/.logs/limits_tripped.json` 에 어느 한도가 깨졌는지 기록.
4. 종료 코드 `42` (한도 트립) 으로 프로세스 종료 → CI 가 인지.

### 비용 추정 (Tier 2)

`models.py` 가 Tier 2 호출마다 input/output 토큰 수와 단가를 곱해 누적 USD 를 계산. 단가 테이블은 모델별로 하드코딩(Sonnet 4.6: $3/MTok in, $15/MTok out 등 — 실제 단가는 출시 시점 공식가로 갱신).

### 안전한 기본값 (왜 5명/$1 인가)

- 신규 인물 5명: 정상 운영에서 하루 1~3명 발견이 평균. 5명 초과는 거의 항상 (a) NER 오인식 폭주 또는 (b) 동명이인 매칭 실패의 신호.
- $1: Tier 2 escalation 이 인물 1건당 ~$0.01 수준이라 가정하면 ~100건. 정상 운영의 10배 여유. 이걸 넘으면 무한 루프 의심.

CI 에서 한도가 자주 트립되면 한도가 너무 빡빡한 게 아니라 시스템이 잘못 도는 신호로 본다 — 한도부터 올리지 말고 원인부터 찾는다.

## 비용 관리 (운영 디테일)

비용 전략의 큰 그림은 위 "비용·모델 전략" / "LLM 결과 캐싱" / "Circuit Breaker" 절 참고. 그 외 운영 차원의 절감 장치:

- 크롤링 원문은 `agent/.cache/sources/` 에 URL 해시별로 저장해 재크롤링 방지.
- 청킹 단계에서 키워드 미등장 텍스트는 Tier 1 호출 자체를 건너뛴다 (호출 0건 = 비용 0).
- `write_agent_section` 의 부분 치환으로 변경 없는 섹션은 토큰을 재출력하지 않는다.
- Tier 2 escalation 비율을 `agent/.logs/escalation_rate.json` 에 기록 — 일정 비율 초과 시 Tier 1 모델 교체 검토.
- `--dry-run` 플래그: LLM 호출 결과를 stdout에만 출력하고 커밋하지 않는다.
- `--no-escalate` 플래그: Tier 2 호출을 강제 차단 (예: 개발/CI 환경).

## 모듈 구조

```
agent/
├── deep_agent.py          # create_deep_agent() 호출 + CLI 진입점. --all 은 status: ongoing 인 이슈만 루프, 이슈별 Circuit Breaker 카운터 초기화 (--issue 는 status 무관)
├── tools.py               # 커스텀 도구 함수 (crawl_*, find_*, extract_*, register_person, create_wiki_page, read/write_agent_section, commit_changes). create_wiki_page 에 비ASCII slug 검증 추가
├── prompts.py             # system_prompt (마커 형식·금지사항·도구 호출 순서 포함) + 도구별 프롬프트 (각 프롬프트는 VERSION 상수 보유 → 캐시 키)
├── models.py              # Tier 1 백엔드(SGLang/Ollama) / Tier 2 SOTA 모델 핸들 (싱글톤) + TIER2_BATCH_MODEL 상수 + Tier 2 비용 누적
├── cache.py               # LLM 응답 캐시 (sha256 키, agent/.cache/llm/)
├── limits.py              # Circuit Breaker — RunLimits + 누적 카운터 + LimitExceeded. max_new_stubs 기본값 20
├── requirements.txt       # deepagents, langchain-openai, langchain-ollama, kiwipiepy, korean_romanizer, ...
├── .env.example
├── crawlers/
│   ├── __init__.py
│   ├── naver_news.py      # Naver News RSS + HTML 스크래퍼
│   └── youtube_transcript.py  # yt-dlp 기반 자막 수집
├── processors/
│   ├── __init__.py
│   ├── dedup.py              # URL/내용 해시 기반 중복 제거
│   ├── chunker.py            # [Tier 0] 키워드 ±N문장 윈도우 청킹
│   ├── ner_kr.py             # [Tier 0] kiwipiepy 기반 한국어 인명 NER
│   ├── participant_finder.py # [Tier 1] 인물 후보 정규화·매칭. mention_count ≥ 2 필터, PARTICIPANTS_PROMPT v2 (이슈 주체 vs 발언자 구별)
│   ├── person_registry.py    # data/people/ stub 생성. _is_valid_person_name + _find_existing_slug + _has_duplicate 순으로 처리
│   ├── extractor.py          # [Tier 1] 행적 이벤트 추출
│   └── stance_extractor.py   # [Tier 1→2] 입장 추출, escalation 포함
├── publishers/
│   ├── __init__.py
│   ├── batch_submitter.py # OpenAI Batch API 제출·polling·결과 적재
│   ├── git_committer.py   # [agent] Git 커밋 자동화. 삭제 파일 repo.index.remove 별도 처리
│   └── quality_gate.py    # Pass E — validate_stances(): Rule1(URL없음)·Rule2(인용문불일치)·Rule3(캐시미스). 강등 로그 → .logs/quality_gate.json
└── quotas/
    ├── __init__.py
    └── youtube.py         # YouTube Data API v3 quota 추적·임계 알람
```

`tools.py` 의 함수들은 `crawlers/` · `processors/` 모듈을 호출하는 얇은 래퍼이며, 빌트인 파일/계획/서브에이전트 도구는 `create_deep_agent()` 가 자동으로 등록한다.

## 향후 설계 방향 (Planned Refactors)

여기 적힌 항목은 현재 설계가 아니라 **다음 반복에서 검토할 변경 후보**다. 충분한 근거(공식 API 확인, PoC, 비용·UX 측정)가 모이면 본 설계로 승격한다.

### 빌트인 파일 도구 통합 (`read_file` / `edit_file` 단일화)

**현재 설계** — `read_agent_section` / `write_agent_section` 라는 자체 도구를 별도로 두고, 빌트인 `read_file` / `edit_file` 의 wiki 경로 사용을 시스템 프롬프트로 금지한다. 도구 표면적이 늘어나고 에이전트가 두 가지 인터페이스를 학습해야 한다.

**변경 후보** — 빌트인 `read_file` / `edit_file` 자체를 경로 인지(path-aware) 동작으로 오버라이드해, 단일 도구로 wiki 와 그 외(`data/`, 캐시 등)를 모두 처리한다. 에이전트의 멘탈 모델이 하나로 통일된다.

**의도된 동작:**

| 호출 | 일반 경로(`data/`, 캐시) | wiki 경로(`wiki/content/{people,issues}/*.md`) |
|---|---|---|
| `read_file(path)` | 파일 전체 반환 | 모든 `<!-- agent:* -->` 블록을 섹션 ID 헤더와 함께 반환 (human-edit 블록 자동 제외) |
| `edit_file(path, old, new)` | 일반 부분 치환 | `old`/`new` 가 agent 블록 *내부* 에 완전히 포함되지 않으면 거부 (human-edit 영역 침범 차단) |
| `write_file(path, content)` | 일반 작성 | wiki 경로에서는 거부 (전면 덮어쓰기는 명시적으로 금지, 섹션 단위만 허용) |

**PoC 결과 (2026-04-29 조사 완료):**

> **결론: 현 설계(`read_agent_section` / `write_agent_section` 자체 도구) 유지.**

1. **`tools=[]` 이름 오버라이드 — 불가.** DeepAgents 의 `tools` 파라미터는 **additive** 다. 같은 이름의 커스텀 함수를 넘겨도 빌트인을 덮어쓰지 않고 병렬 등록된다. 공식 docs 어디에도 우선순위 규칙이 없고, 결과적으로 동일 이름 함수가 두 개 등록되어 에이전트가 어느 쪽을 부를지 예측 불가.
2. **`disable_builtin=` 파라미터 — 없음.** API 레퍼런스와 공식 커스터마이제이션 가이드 모두 이런 파라미터를 노출하지 않는다.
3. **"pluggable backend" = `backend` 파라미터.** `create_deep_agent(backend=...)` 로 파일시스템 구현체를 교체할 수 있다. 내장 구현: `StateBackend`(기본, ephemeral), `FilesystemBackend`(로컬 디스크), `StoreBackend`(크로스스레드 영속), `CompositeBackend`(경로별 라우팅). `CompositeBackend` 를 써서 `wiki/` 경로를 커스텀 백엔드로 보내는 방식은 원리상 가능하지만, **`BackendProtocol` 인터페이스가 미문서화**여서 커스텀 구현은 내부 API 의존 + 버전 깨짐 위험이 크다.

**왜 현 설계를 유지하는가:**
- `read_agent_section` / `write_agent_section` 는 이미 구현 방향이 확정되었고, 동작이 명시적·테스트 가능하다.
- 동일 이름 오버라이드 불가 + 백엔드 커스텀 인터페이스 미문서화 → 통합 경로가 내부 구현에 기댄 해킹이 된다.
- 도구 표면적은 두 개 더 늘어나지만, wiki-safe 보장을 얻는 대가로 수용 가능하다.
- **재평가 트리거:** `FilesystemMiddleware` 소스 코드가 접근 가능해지거나, `BackendProtocol` 인터페이스가 공식 문서화되면 `CompositeBackend` 커스텀 구현 경로를 재검토한다. 소스를 직접 읽을 수 있으면 (a) `tools=[]` 처리 순서, (b) 미들웨어 등록 흐름, (c) 백엔드 추상화 계층의 실제 메서드 시그니처를 확인할 수 있어 현재 결론이 바뀔 수 있다.

**재조사 (2026-04-29, deepagents v0.5.4 설치본 직접 확인):**

> **결론 변경 없음 — 현 설계 유지.**

재평가 트리거가 발동했음을 확인. 그러나 트리거 발동이 곧 설계 변경을 의미하지는 않음:

| 트리거 조건 | v0.5.4 실태 |
|---|---|
| `FilesystemMiddleware` 소스 접근 | ✅ `deepagents/middleware/filesystem.py` (1697 줄) shipped |
| `BackendProtocol` 공식 문서화 | ✅ `deepagents/backends/protocol.py:318+` 에 abc.ABC + 메서드별 docstring + Examples + 동기/비동기 페어 모두 노출 |
| `CompositeBackend` 사용 가이드 | ✅ `FilesystemMiddleware` docstring 에 `CompositeBackend(default=..., routes={"/memories/": ...})` 예시 |

소스를 읽고 확인된 추가 사실:

1. **빌트인 도구는 `FilesystemMiddleware.tools = [...]` 로 주입** (`graph.py:174-178` `_REQUIRED_MIDDLEWARE` 로 강제). `tools=` 인자와 별도 경로이므로 v0.5.4 에서도 동일 이름 오버라이드 불가는 변함 없음.
2. **`_ToolExclusionMiddleware` 는 존재하지만 private + `HarnessProfile.excluded_tools` 경유**. `create_deep_agent` 호출 시점에 caller 가 직접 빌트인 도구를 빼는 공개 API 는 여전히 없음.
3. **`BackendProtocol` 커스텀 구현은 이제 실현 가능**. `read/write/edit/grep/glob/ls/upload_files/download_files` 모두 `raise NotImplementedError` 기본 구현이라 필요한 메서드만 채워 넣으면 됨.

**그럼에도 현 설계를 유지하는 사유 (재조사 기준):**

- **인터페이스 mismatch 해소 안 됨.** 빌트인 `read_file(file_path: str, offset: int, limit: int) -> ReadResult` 는 라인 단위 path-based. 우리 도메인은 `(kind, slug, section_id)` 의 섹션 마커 정규식 기반. `BackendProtocol` 을 구현해도 LLM 이 부르는 도구 시그니처는 빌트인 그대로이므로, `/wiki/people/lee-jae-myung#events` 같은 가짜 path 스킴을 프롬프트로 강제해야 함 — 도구 추가 비용보다 큼.
- **컨텍스트 격리 표면 손실.** 현 설계는 LLM 이 보는 도구 자체를 `read_agent_section` 으로 좁혀 `<!-- human-edit -->` 블록과 페이지 frontmatter 를 노출하지 않음. backend 레이어로 내리면 빌트인 `read_file` 이 그대로 노출되어 (path validation 없으면) 사람 편집 영역까지 LLM 컨텍스트로 들어감. backend 안에서 `<!-- human-edit -->` 마스킹을 다시 구현해야 하므로 코드 줄 수는 줄지 않음.
- **circuit-breaker 통합 거리 증가.** `tools.py:write_agent_section` 이 직접 `RunCounter.check_pages()` / `record_page_modified()` 를 호출. backend `edit/write` 로 옮기면 limits 가 도구 레이어에서 backend 레이어로 한 단계 멀어지고, runtime context 에서 counter 싱글톤을 다시 잡아야 함.
- **`CompositeBackend` routes 는 prefix 라우팅.** `wiki/` 전체를 커스텀 backend 로 보내는 구조는 가능하지만, 그 backend 안에서 결국 "section marker 인지 → 파싱 → 검증" 을 다시 짜야 함. 현재 `tools.py` 의 `SECTION_RE` 기반 로직과 동등. 코드 이동만 발생.

**다음 재평가 조건 (있다면):**

deepagents 가 다음 중 하나를 도입하면 다시 검토:
- (a) `create_deep_agent(disable_builtin_tools=["read_file","edit_file"])` 같은 호출 사이트 공개 API — 빌트인을 끄는 비용이 사라짐
- (b) Tool-level path scoping (`FilesystemPermission` 의 read/write 분리 + per-tool path glob) — 현재 `permissions=` 가 "deny all writes outside /wiki/content/" 같은 정밀도까지 가면 자체 `write_agent_section` 의 가드 로직 일부를 위임 가능

이 두 API 가 등장하기 전까지는 현 설계가 비용·안전성·코드 명료성 모두에서 우세.

## 참고

- [DeepAgents (LangChain)](https://docs.langchain.com/oss/python/deepagents/) — 본 에이전트의 런타임
- [LangGraph](https://langchain-ai.github.io/langgraph/) — DeepAgents의 실행 엔진
- [Ollama](https://ollama.com/) — 로컬 개발용 Tier 1 LLM 런타임
- [SGLang](https://github.com/sgl-project/sglang) — Kubernetes 운영용 Tier 1 OpenAI-compatible serving
- [langchain-openai](https://python.langchain.com/docs/integrations/chat/openai/) — OpenAI 및 SGLang OpenAI-compatible LangChain 어댑터
- [langchain-ollama](https://python.langchain.com/docs/integrations/chat/ollama/) — Ollama LangChain 어댑터
- [kiwipiepy](https://github.com/bab2min/kiwipiepy) — Tier 0 한국어 형태소·NER (순수 Python, JVM 불필요)
- [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) — Git + Markdown incremental 패턴
- [EveryPolitician](https://everypolitician.org/) — 인물 데이터 모델
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)
