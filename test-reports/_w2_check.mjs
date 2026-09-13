import { checkReview, parseCritiqueEntries } from "file:///C:/Users/Administrator/.agents/skills/tt/scripts/review-gate.mjs";
import fs from "node:fs";
const dir = "E:/stu/project/stu/EduAgent实施手册/.ai-hub/plans/tasks";
const crit = fs.readFileSync(dir + "/W2-技术批判.md", "utf8");
const fix = fs.readFileSync(dir + "/W2-优化修改方案.md", "utf8");
let tracker = "";
try { tracker = fs.readFileSync("E:/stu/project/stu/EduAgent实施手册/.opencode/plans/critique-backlog-tracker.md", "utf8"); } catch {}
const entries = parseCritiqueEntries(crit);
console.log("entries total =", entries.length);
entries.forEach(e => console.log("  title=", e.title, "| url=", (e.url||"").slice(0,40), "| date=", e.date, "| valid=", e.valid));
const r = checkReview({ critiqueText: crit, fixText: fix, trackerText: tracker, id: "W2" });
console.log("RESULT ok =", r.ok);
r.checks.forEach(c => console.log("  " + (c.pass?"PASS":"FAIL") + " " + c.name + "  " + c.detail));