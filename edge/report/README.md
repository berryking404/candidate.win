# report API (Cloudflare Worker)

공개 엔드포인트: `POST https://wiki.candidate.win/api/report`

Hugo(GitHub Pages)는 정적만 서빙하므로, 동일 호스트 경로를 Cloudflare Worker가 받아 Issues를 생성한다. 시크릿 `CANDYDATE_ISSUES_TOKEN`은 Worker에만 둔다.

## Deploy (정본 = GitHub Actions)

워크플로: `.github/workflows/deploy-report-worker.yml`

1. Repo Secrets에 `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CANDYDATE_ISSUES_TOKEN` 등록
2. `edge/report/**` 변경을 `main`에 merge하거나 `gh workflow run deploy-report-worker.yml`
3. CI가 `wrangler deploy` + Worker secret 주입 + `wrangler.toml` `[[routes]]` (`wiki.candidate.win/api/report*`) 적용

로컬 수동 `wrangler`는 비상용이다. 일상 배포는 Actions만 쓴다.

요청 JSON은 `wiki/static/js/report-issue-url.js`의 `buildReportPayload`와 같다. 응답은 `{ ok: true|false }`만 반환하며, GitHub 오류 전문은 클라이언트에 노출하지 않는다.
