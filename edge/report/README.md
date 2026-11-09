# report API (Cloudflare Worker)

공개 엔드포인트: `POST https://wiki.candidate.win/api/report`

Hugo(GitHub Pages)는 정적만 서빙하므로, 동일 호스트 경로를 Cloudflare Worker가 받아 Issues를 생성한다. 시크릿 `CANDYDATE_ISSUES_TOKEN`은 Worker에만 둔다.

```bash
cd edge/report
npm i -g wrangler   # 또는 npx
wrangler secret put CANDYDATE_ISSUES_TOKEN
# Cloudflare 대시보드에서 wiki.candidate.win/api/report* 라우트를 이 Worker에 연결
wrangler deploy
```

요청 JSON은 `wiki/static/js/report-issue-url.js`의 `buildReportPayload`와 같다. 응답은 `{ ok: true|false }`만 반환하며, GitHub 오류 전문은 클라이언트에 노출하지 않는다.
