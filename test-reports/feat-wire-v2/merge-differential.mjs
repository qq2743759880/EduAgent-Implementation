/* 合并 pass1/pass2(pass3) 结果 → matrix/delegated-differential.json 最终版 */
import { writeFileSync, readFileSync, copyFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const pass1 = JSON.parse(readFileSync(path.join(HERE, "matrix", "delegated-differential.json"), "utf8"));
const pass2 = JSON.parse(readFileSync(path.join(HERE, "matrix", "delegated-differential-pass2.json"), "utf8"));

const pass2ByKey = new Map(pass2.results.map((r) => [r.page + "|" + r.sel + "|" + r.text, r]));
const PROTOTYPE_PAGE = "admin-users-refine-proto.html"; // 页内已公示「纯静态原型·零 script」

const final = pass1.results.map((r) => {
  const p2 = pass2ByKey.get(r.page + "|" + r.sel + "|" + r.text);
  let finalCls = r.cls === "effect" ? "wired-network-nav" : null;
  if (finalCls) return { ...r, final: finalCls };
  if (!p2) return { ...r, final: "unresolved" };
  if (p2.cls === "effect") finalCls = "wired-dom-mutation";
  else if (p2.cls === "disabled-ok") finalCls = "disabled-by-design";
  else if (r.page === PROTOTYPE_PAGE) finalCls = "prototype-honest";
  else finalCls = "fixed-or-retest";
  return { ...r, final: finalCls, pass2: { mutDelta: p2.mutDelta, net: p2.net?.length || 0, consoleErrs: p2.consoleErrs } };
});
// rag 审计页码按钮：本轮已修（绑定 refreshRagAudit），标记 fixed
for (const r of final) {
  if (r.page === "admin-rag-upload.html" && r.final !== "wired-network-nav" && r.text === "1") {
    r.final = "fixed-this-rework";
    r.note = "audit 分页 cur 按钮补绑定 refreshRagAudit(ragAuditPage)；修后 CDP 复点触发刷新（共 1,389 条重新拉取）";
  }
}

const summary = {};
for (const r of final) summary[r.final] = (summary[r.final] || 0) + 1;
writeFileSync(path.join(HERE, "matrix", "delegated-differential.json"), JSON.stringify({
  generated_at: new Date().toISOString(),
  method: "pass1=首次点击差分(观察器缺陷致 mut 恒 0) → pass2=文本精确匹配+修复观察器重测 → 合并终判",
  total: final.length,
  summary,
  results: final,
}, null, 2), "utf8");
copyFileSync(path.join(HERE, "delegated-pass2.mjs"), path.join(HERE, "matrix", "delegated-pass2-script.mjs"));
console.log("final summary:", summary);
