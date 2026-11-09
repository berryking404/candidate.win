/** 정정·삭제 모달 → GitHub Issue form 사전채움 URL 빌더 (필드 id ↔ 쿼리 키). */
(function (root) {
  var REPO_NEW_ISSUE =
    "https://github.com/berryking404/candidate.win/issues/new";

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
   * @returns {string}
   */
  function buildReportIssueUrl(opts) {
    var type = opts.type === "takedown" ? "takedown" : "correction";
    var pageUrl = opts.pageUrl || "";
    var desc = opts.desc || "";
    var source = opts.source || "";
    var meta = parsePageMeta(pageUrl);
    var params = new URLSearchParams();
    params.set(
      "template",
      type === "takedown" ? "takedown.yml" : "correction.yml"
    );
    if (pageUrl) params.set("page-url", pageUrl);
    if (meta.slug) params.set("target-slug", meta.slug);
    if (meta.kind) params.set("target-kind", meta.kind);
    if (type === "takedown") {
      if (desc) {
        params.set("reason", desc);
        params.set("scope", desc);
      }
      if (source) params.set("legal-basis", source);
    } else {
      if (desc) params.set("incorrect", desc);
      if (source) params.set("sources", source);
    }
    return REPO_NEW_ISSUE + "?" + params.toString();
  }

  root.CandydateReport = {
    parsePageMeta: parsePageMeta,
    buildReportIssueUrl: buildReportIssueUrl,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
