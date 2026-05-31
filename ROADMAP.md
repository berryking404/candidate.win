# Roadmap

## Phase 1 — Wiki 뼈대 (정적 사이트)

- [x] Hugo 사이트 초기화 (`wiki/`) — v0.161.0, `wiki/hugo.toml`
- [x] 인물 페이지 레이아웃 디자인 — `layouts/partials/people-single.html`
- [x] 이슈 페이지 레이아웃 디자인 — `layouts/partials/issues-single.html` (입장 표 포함)
- [x] 인물 시드 YAML 스키마 확정 — `data/people/lee-jae-myung.yaml` 예시
- [x] 이슈 시드 YAML 스키마 확정 — `data/issues/real-estate-tax-2026.yaml` 예시
- [x] 예시 인물 페이지 수동 작성 — `wiki/content/people/lee-jae-myung.md`
- [x] 예시 이슈 페이지 수동 작성 — `wiki/content/issues/real-estate-tax-2026.md`
- [x] GitHub Pages 배포 자동화 — `.github/workflows/deploy.yml` (Hugo 0.161.0, actions/deploy-pages)

## Phase 2 — Crawler MVP & Tier 0/1 전처리

- [x] Naver News RSS 크롤러 (`agent/crawlers/naver_news.py`) — Search API + 원문 스크래핑
- [x] YouTube 자막 크롤러 (`agent/crawlers/youtube_transcript.py`) — 채널 RSS 우선, API 폴백
- [x] **[YouTube quota]** 채널 RSS 우선 폴링 + `quotas/youtube.py` quota 추적 (80%/100% 임계 알람, `--no-youtube` 플래그)
- [x] 기사·자막 중복 제거 및 저장 (`agent/processors/dedup.py`) — URL + 내용 해시
- [x] **[Tier 0]** 키워드 ±N문장 청킹 (`agent/processors/chunker.py`)
- [x] **[Tier 0]** kiwipiepy 한국어 인명 NER (`agent/processors/ner_kr.py`)
- [x] **[Tier 1]** Ollama 모델 핸들 모듈 (`agent/models.py`) — Tier 2 비용 누적기 포함
- [ ] 크롤러 + 청킹 부피 측정 (자막 1시간 → 청크 합계 토큰 수 벤치마크)

## Phase 3 — LLM Agent 통합

- [x] DeepAgents 도구 정의 — `tools.py` (crawl_news/youtube, find_participants, register_person, extract_events/stance, read/write_agent_section, commit_changes)
- [x] **[Tier 2 = OpenAI]** 오케스트레이터 `openai:gpt-5.4-mini` — `deep_agent.py`
- [x] **[Tier 2-batch]** `extract_stance` → `pending.jsonl` enqueue 분기 — `processors/stance_extractor.py`
- [x] **[Tier 2-batch]** `publishers/batch_submitter.py` — 제출·polling·결과 캐시 적재
- [x] **[Tier 2-batch]** Batch 결과 → `agent/.cache/llm/extract_stance/` 동일 키 적재
- [x] **[2-pass cron]** macOS launchd 잡 분리: Pass A+B (09:00 KST) / Pass D (14:00 KST) — `agent/launchd/` 구현 완료 (2026-05-05)
- [x] CLI `--no-batch` / `--dry-run` / `--no-escalate` / `--no-youtube` 등 모든 플래그 — `deep_agent.py`
- [x] **[컨텍스트 격리]** `read_agent_section` / `write_agent_section` 정규식 구현 — `tools.py`
- [x] **[캐시]** `cache.py` — sha256 키 + VERSION 무효화, Batch 동일 키 스킴
- [x] **[Circuit Breaker]** `limits.py` — `RunLimits` + `RunCounter` + 종료코드 42
- [x] **[Tier 2 비용 추적]** `models.py` — 캐시 -90%·Batch -50% 반영 `CostAccumulator`, `limits.py` 연동
- [x] **[Tier 1]** 행적 추출 프롬프트 — `prompts.py` `EVENTS_PROMPT` (VERSION v1) + `processors/extractor.py`
- [x] **[Tier 1]** 입장 추출 프롬프트 — `prompts.py` `STANCE_PROMPT` (VERSION v1) + `processors/stance_extractor.py`
- [x] **[Tier 1→2]** escalation 트리거: confidence < 0.7 / position=mixed / quotes 없음
- [X] **[일관성]** 이슈별 명시적 입장 판정 기준(`stances` 필드) 도입 및 프롬프트 주입
- [x] **[메트릭]** `cache_hit_rate.json`, `limits_tripped.json`, `cost.json` — `.logs/`
- [x] 이슈 처리 시 발언자 자동 발견 → stub 등록 — `processors/person_registry.py` + `tools.py`
- [x] 이슈 ↔ 인물 양방향 링크 — Hugo 템플릿 (Phase 1) + agent section 마커
- [x] stub 인물 검수 워크플로 — `status: stub` 배지 (Hugo), `_pending/` 동명이인 격리
- [x] CLI 플래그 전체 구현 — `deep_agent.py`
- [x] 단일 인물 end-to-end 테스트 — `lee-jae-myung --dry-run --no-batch` (2026-04-29)
- [x] 단일 이슈 end-to-end 테스트 — `gender-conflict-2026 --dry-run --no-batch` (2026-04-29)
- [x] **[실명 검증]** `_is_valid_person_name()` — 한국 성씨 목록 + 조직명 키워드 필터로 기업·단체·직책 stub 생성 차단 — `processors/person_registry.py`
- [x] **[curated slug 불일치 해결]** `_find_existing_slug()` — romanizer 표기(`jeong-dong-yeong`)와 curated 표기(`jeong-dong-young`) 불일치를 동명이인으로 오판하지 않도록 선행 검사 — `processors/person_registry.py`
- [x] **[slug 검증]** `create_wiki_page` 에 비ASCII slug 거부 로직 추가 — 한글 파일명 생성 차단 — `tools.py`
- [x] **[발언자 필터 강화]** `PARTICIPANTS_PROMPT` v1→v2 — "이슈 주체(해임·비판 대상) ≠ 발언자" 규칙 명시, mention_count 우회(`matched_slug`) 조건 제거 — `processors/participant_finder.py`, `prompts.py`
- [x] **[프롬프트 정비]** 시스템 프롬프트에 wiki 마커 형식·금지사항·도구 호출 순서 명시, slug 사용 규칙(`register_person` 반환값 의무 사용) 추가 — `prompts.py`
- [x] **[git_committer 수정]** `repo.index.add` 가 삭제 파일을 처리 못하던 버그 수정 — 삭제 파일은 `repo.index.remove` 로 별도 처리 — `publishers/git_committer.py`
- [x] **[Tier 1 모델 교체]** `TIER1_MODEL` `qwen3:8b` → `exaone3.5:7.8b` (한국어 성능 향상) — `models.py`
- [x] `--all` 실행 시 이슈 루프로 통합, 이슈별 Circuit Breaker 카운터 초기화 — `deep_agent.py`
- [x] 전체 이슈 14건 end-to-end 실행 완료 (2026-05-01~05)

## Phase 3.5 — 검토 후보 (Planned Refactors)

상세 근거는 [agent/DESIGN.md "향후 설계 방향"](agent/DESIGN.md) 절. 검증 통과 시 본 설계로 승격, 실패 시 현 설계 유지.

- [ ] 이슈 keywords 작성 가이드라인 문서화 — 인물 실명을 keywords[0]에 쓰면 NER 과다 추출 → 이슈 중립 키워드만 사용하도록 CLAUDE.md / README 가이드 추가
- [x] DeepAgents 빌트인 오버라이드 가능성 PoC *(2026-04-29 조사 완료 — 결론: 현 설계 유지)*
  - [x] `tools=[my_read_file]` 같은 이름 함수의 우선순위 동작 확인 → **additive, 오버라이드 불가**
  - [x] `disable_builtin=` 등 옵션 또는 "pluggable backend" API 표면 확인 ([공식 customization 가이드](https://docs.langchain.com/oss/python/deepagents/customization/) / API reference) → **`disable_builtin=` 없음; `backend=CompositeBackend(...)` 는 존재하나 `BackendProtocol` 커스텀 구현이 미문서화**
  - [x] PoC 결과를 본 ROADMAP 항목에 기록 → 완료 (DESIGN.md "향후 설계 방향" 참고)
- ~~(PoC 통과 시) `read_file` / `edit_file` 단일화~~ — PoC 실패로 보류
- ~~(PoC 통과 시) 시스템 프롬프트에서 "wiki 경로 read_file 금지" 문구 제거~~ — PoC 실패로 보류
- [x] (PoC 실패 시) 자체 도구 안 유지 결정을 DESIGN.md 에 명시적으로 기록 → 완료
- [x] *(재평가 조건 충족 — 2026-04-29 재조사)* v0.5.4 에서 `BackendProtocol` 공식 문서화 + `FilesystemMiddleware` 소스 공개 확인. **현 설계 유지** — 사유: (a) 빌트인 `read_file(path)` vs `read_agent_section(kind,slug,section_id)` 인터페이스 mismatch, (b) 빌트인 사용 시 `<!-- human-edit -->` 영역 LLM 노출 표면 재오픈, (c) `RunCounter.check_pages()` 통합 거리 증가. DESIGN.md "향후 설계 방향" 절에 결론 기록.

## Phase 4 — 자동화 & 확장

- [x] macOS launchd 스케줄러 — `agent/launchd/com.candydate.research.plist` (09:00 KST, Pass A+B) + `agent/launchd/com.candydate.apply.plist` (14:00 KST, Pass C+D). 래퍼: `run_pass_ab.sh` / `run_pass_d.sh`. 로그: `/tmp/com.candydate.agent.log`. 등록: `launchctl load ~/Library/LaunchAgents/com.candydate.{research,apply}.plist`
- [x] 인물 커버리지 확장 (정치인 → 언론인 → 인플루언서)
- [x] 이슈 커버리지 확장 (정책 이슈 → 사회 화제 → 선거 쟁점)
- [ ] YouTube quota 증액 트리거 — 7일 평균 사용률 70% 또는 추적 인물 150명 초과 시 Google Cloud 증액 신청
- [x] 품질 검수 게이트 (hallucination 필터, 입장 오귀속 검증) — `write_agent_section(section_id="stances")` 직전 호출. `publishers/quality_gate.py`: Rule1(URL 없음), Rule2(인용문-원문 불일치→캐시 조회), Rule3(캐시 미스→패널티 없음). 강등 로그: `.logs/quality_gate.json` (2026-05-05)
- [x] 검색 기능 추가 — Pagefind 정적 검색. `/search/` 별도 페이지, people+issues 전체 인덱싱. `deploy.yml`에 `npx pagefind@latest --site public` 추가. nav에 검색 링크. (2026-05-05)

## Backlog

- 다국어 지원 (영어 wiki)
- 외부 기여자를 위한 PR 기반 편집 플로우
- 타임라인 뷰 (인물별 연대표)
- Wikidata 연동 (구조화 메타데이터 동기화)

## 운영·법무 정책 (public repo 운영 전제)

정정·삭제 요청 등 콘텐츠 분쟁은 별도 폼·이메일을 두지 않고 **GitHub Issues 단일 채널**로 관리한다. 모든 처리 이력이 공개·추적 가능해 투명성과 운영 비용 양면에서 유리하다.

- [x] Issue 템플릿 `.github/ISSUE_TEMPLATE/correction.yml` — 출처 필수, 1차 출처 우선, 허위신고 책임 인지 체크박스
- [x] Issue 템플릿 `.github/ISSUE_TEMPLATE/takedown.yml` — 법적 근거 필수, 공적 발언 삭제 불가 안내, 책임 인지 체크박스
- [x] Hugo partial `wiki/layouts/partials/correction-link.html` 작성 — 사전 채움 URL 빌더 (필드 `id` ↔ 쿼리 키 1:1 매칭)
- [x] `CODE_OF_CONDUCT.md` 초안 작성 — Contributor Covenant v2.1 기반 + 본 프로젝트 특화 조항. 포함 사항:
  - **실명 인물을 다루는 위키 특성**상 토론·이슈 작성 시 인신공격 금지, 출처 동반 의무
  - **정치적 중립성 선언** — 특정 정파·인물 옹호/공격 목적의 기여 거부
  - 정정·삭제 요청은 GitHub Issues 채널만 사용 (개인 메일·DM 시 무응답)
  - 허위 정정 요청 반복 시 `correction` 라벨 봇이 신고자 차단 (운영진 재량)
  - 처리 이력 공개 정책 — 모든 정정/삭제 결정은 PR commit + closed issue 로 추적
  - 운영진 연락처 (이메일·메인테이너 핸들)
  - 위반 신고 절차 + 처리 SLA
- [ ] 라벨 체계 생성: `correction`, `takedown`, `verified`, `disputed`, `resolved`
- [x] SLA 명시 — 1차 응답 7일 / 처리 완료 30일, README `## 정정·삭제 요청` 절에 기재 완료
- [x] `wiki/hugo.toml` 에 `[params] repoURL` 설정 완료
- [x] Hugo `single.html` (people, issues) 푸터에 partial 호출 연결
- [ ] 처리된 이슈는 commit message 에 `Closes #N` 으로 연결해 변경 이력과 요청을 매핑
- [X] 모든 stance·event 항목에 출처 URL 인용 의무화 (근거 없는 항목은 렌더링하지 않음)
- [x] `status: stub` 인물 페이지에 "검수 미완료" 안내 배지 노출 — `layouts/partials/people-single.html` (배지 + ⚠️ 안내 문구)
- [x] 민감 정보 사전 검증 — gitleaks pre-commit hook (`.pre-commit-config.yaml`) + GitHub Actions (`secret-scan.yml`) 이중 게이트
- [x] 라이선스 파일 — 코드 `LICENSE` (MIT) + 콘텐츠 `LICENSE-content` (CC BY-NC 4.0), README 라이선스 절 업데이트
- [x] 라이선스/이용약관 wiki 페이지 — `wiki/content/policy.md` (CC BY-NC 4.0, 정정권, 공적 발언 삭제 제한, 면책 조항). 사이트 푸터에 링크 추가
