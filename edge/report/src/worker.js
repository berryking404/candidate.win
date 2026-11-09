import { buildGitHubIssue, validatePayload } from "./issue.js";

const REPO = "berryking404/candidate.win";
const ALLOWED_ORIGINS = new Set([
  "https://wiki.candidate.win",
  "http://localhost:1313",
  "http://127.0.0.1:1313",
]);

function corsHeaders(origin) {
  const allow = origin && ALLOWED_ORIGINS.has(origin) ? origin : "https://wiki.candidate.win";
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function json(status, body, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders(origin),
    },
  });
}

async function createIssue(token, issue) {
  const res = await fetch(`https://api.github.com/repos/${REPO}/issues`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "candidate-win-report-api",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title: issue.title,
      body: issue.body,
      labels: issue.labels,
    }),
  });
  return res;
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    const url = new URL(request.url);
    if (request.method !== "POST" || !url.pathname.endsWith("/api/report")) {
      return json(404, { ok: false }, origin);
    }
    if (origin && !ALLOWED_ORIGINS.has(origin)) {
      return json(403, { ok: false }, origin);
    }
    let raw;
    try {
      raw = await request.json();
    } catch {
      return json(400, { ok: false }, origin);
    }
    const validated = validatePayload(raw);
    if (!validated.ok) {
      return json(400, { ok: false }, origin);
    }
    const token = env.CANDYDATE_ISSUES_TOKEN;
    if (!token) {
      return json(503, { ok: false }, origin);
    }
    const issue = buildGitHubIssue(validated.payload);
    let ghRes;
    try {
      ghRes = await createIssue(token, issue);
    } catch {
      return json(502, { ok: false }, origin);
    }
    if (!ghRes.ok) {
      return json(502, { ok: false }, origin);
    }
    return json(201, { ok: true }, origin);
  },
};

export { buildGitHubIssue, validatePayload };
