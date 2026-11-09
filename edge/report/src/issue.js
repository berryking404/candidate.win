/** Pure helpers: modal payload → GitHub Issues API body (no secrets). */

const ALLOWED_TYPES = new Set(["correction", "takedown"]);
const MAX_TEXT = 8000;

/**
 * @param {unknown} raw
 * @returns {{ok:true, payload:object}|{ok:false, error:string}}
 */
export function validatePayload(raw) {
  if (!raw || typeof raw !== "object") {
    return { ok: false, error: "invalid_body" };
  }
  const type = raw.type === "takedown" ? "takedown" : raw.type === "correction" ? "correction" : null;
  if (!type || !ALLOWED_TYPES.has(type)) {
    return { ok: false, error: "invalid_type" };
  }
  const pageUrl = String(raw.pageUrl || "").trim();
  if (!pageUrl || pageUrl.length > 2000) {
    return { ok: false, error: "invalid_page" };
  }
  const targetSlug = String(raw.targetSlug || "").trim().slice(0, 200);
  const targetKind = String(raw.targetKind || "").trim().slice(0, 40);
  if (type === "correction") {
    const incorrect = String(raw.incorrect || "").trim();
    if (!incorrect || incorrect.length > MAX_TEXT) {
      return { ok: false, error: "invalid_desc" };
    }
    const sources = String(raw.sources || "").trim().slice(0, MAX_TEXT);
    return {
      ok: true,
      payload: { type, pageUrl, targetSlug, targetKind, incorrect, sources },
    };
  }
  const reason = String(raw.reason || "").trim();
  const scope = String(raw.scope || reason).trim();
  if (!reason || reason.length > MAX_TEXT) {
    return { ok: false, error: "invalid_desc" };
  }
  const legalBasis = String(raw.legalBasis || "").trim().slice(0, MAX_TEXT);
  return {
    ok: true,
    payload: { type, pageUrl, targetSlug, targetKind, reason, scope, legalBasis },
  };
}

/**
 * @param {object} payload validated payload
 * @returns {{title:string, body:string, labels:string[]}}
 */
export function buildGitHubIssue(payload) {
  const type = payload.type === "takedown" ? "takedown" : "correction";
  const slug = payload.targetSlug || "unknown";
  const title = `[${type}] ${slug}`.slice(0, 200);
  const lines = [];
  lines.push(`### 대상 페이지 URL\n\n${payload.pageUrl}`);
  lines.push(`### 대상 slug\n\n${payload.targetSlug || "(none)"}`);
  lines.push(`### 페이지 종류\n\n${payload.targetKind || "(none)"}`);
  if (type === "correction") {
    lines.push(`### 잘못된 내용\n\n${payload.incorrect}`);
    lines.push(`### 올바른 내용\n\n(모달 단일 서술 — 잘못된 내용/정정 요지를 위 필드에 포함)`);
    lines.push(`### 근거 출처\n\n${payload.sources || "(none)"}`);
  } else {
    lines.push(`### 삭제 범위\n\n${payload.scope}`);
    lines.push(`### 사유\n\n${payload.reason}`);
    lines.push(`### 법적 근거 또는 1차 출처\n\n${payload.legalBasis || "(none)"}`);
  }
  lines.push("\n---\n_Submitted via wiki report form (server-side)._");
  return {
    title,
    body: lines.join("\n\n"),
    labels: [type],
  };
}
