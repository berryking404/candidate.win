/** 정정·삭제 모달 → /api/report 페이로드 빌더·제출 (GitHub URL 비노출). */
(function (root) {
  var REPORT_API = "/api/report";

  function parsePageMeta(pageUrl) {
    try {
      var u = new URL(pageUrl);
      var parts = u.pathname.replace(/\/+$/, "").split("/").filter(Boolean);
      var iPeople = parts.indexOf("people");
      var iIssues = parts.indexOf("issues");
      if (iPeople >= 0 && parts[iPeople + 1]) {
        return { kind: "person", slug: parts[iPeople + 1] };
      }
      if (iIssues >= 0 && parts[iIssues + 1]) {
        return { kind: "issue", slug: parts[iIssues + 1] };
      }
    } catch (e) {
      /* ignore invalid URL */
    }
    return { kind: "", slug: "" };
  }

  /**
   * @param {{type:string,pageUrl:string,desc:string,source?:string}} opts
   * @returns {object}
   */
  function buildReportPayload(opts) {
    var type = opts.type === "takedown" ? "takedown" : "correction";
    var pageUrl = opts.pageUrl || "";
    var desc = opts.desc || "";
    var source = opts.source || "";
    var meta = parsePageMeta(pageUrl);
    if (type === "takedown") {
      return {
        type: type,
        pageUrl: pageUrl,
        targetSlug: meta.slug || "",
        targetKind: meta.kind || "",
        reason: desc,
        scope: desc,
        legalBasis: source,
      };
    }
    return {
      type: type,
      pageUrl: pageUrl,
      targetSlug: meta.slug || "",
      targetKind: meta.kind || "",
      incorrect: desc,
      sources: source,
    };
  }

  /**
   * @param {object} payload
   * @returns {Promise<{ok:boolean}>}
   */
  function submitReport(payload) {
    return fetch(REPORT_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "omit",
    }).then(function (res) {
      if (!res.ok) return { ok: false };
      return res.json().then(
        function (data) {
          return { ok: !!(data && data.ok) };
        },
        function () {
          return { ok: false };
        }
      );
    });
  }

  root.CandydateReport = {
    REPORT_API: REPORT_API,
    parsePageMeta: parsePageMeta,
    buildReportPayload: buildReportPayload,
    submitReport: submitReport,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
