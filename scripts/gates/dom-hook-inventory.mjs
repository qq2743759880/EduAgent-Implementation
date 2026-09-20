import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import {
  PROJECT_ROOT,
  ensureDir,
  finalizeReport,
  makeCheck,
  parseCli,
  printReport,
  readJson,
  resolveTargets,
  usage,
  writeGateReports,
  writeJson,
} from "./_shared.mjs";

const FROZEN_MD = path.join(PROJECT_ROOT, "docs", "dom-hooks-frozen.md");
const FROZEN_JSON = path.join(PROJECT_ROOT, "docs", "dom-hooks-frozen.json");

const CATEGORY_LABELS = {
  "get-element-by-id": "getElementById",
  "query-selector": "querySelector",
  "query-selector-all": "querySelectorAll",
  "class-list": "classList operations",
  closest: "closest",
  matches: "matches",
  "event-delegation": "event delegation selectors",
  "dynamic-selector": "dynamic/template selectors",
  "form-name-tag": "form.elements / name / tagName",
  "dom-relations": "parentNode / nextSibling family",
};

function normalizeExpression(value) {
  return value.replace(/\s+/g, " ").trim().slice(0, 600);
}

function lineIndex(text) {
  const starts = [0];
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === "\n") starts.push(index + 1);
  }
  return (offset) => {
    let low = 0;
    let high = starts.length - 1;
    while (low <= high) {
      const middle = (low + high) >> 1;
      if (starts[middle] <= offset) low = middle + 1;
      else high = middle - 1;
    }
    return high + 1;
  };
}

function staticSelector(argument) {
  const value = argument.trim();
  if (/^(['"])(?:\\.|(?!\1).)*\1$/s.test(value)) return value.slice(1, -1);
  if (/^`[^$`]*`$/s.test(value)) return value.slice(1, -1);
  return null;
}

function scanSource(name, text) {
  const entries = [];
  const getLine = lineIndex(text);
  const seen = new Set();
  const add = (category, match, selector = null) => {
    const expression = normalizeExpression(match[0]);
    const key = `${category}|${match.index}|${expression}`;
    if (seen.has(key)) return;
    seen.add(key);
    entries.push({ category, line: getLine(match.index), selector, expression });
  };
  const collectCalls = (category, pattern) => {
    for (const match of text.matchAll(pattern)) add(category, match, staticSelector(match[1] || ""));
  };

  collectCalls("get-element-by-id", /\bgetElementById\s*\(\s*([^)]*?)\s*\)/gs);
  collectCalls("query-selector-all", /\bquerySelectorAll\s*\(\s*([^)]*?)\s*\)/gs);
  collectCalls("query-selector", /\bquerySelector(?!All)\s*\(\s*([^)]*?)\s*\)/gs);
  collectCalls("closest", /\bclosest\s*\(\s*([^)]*?)\s*\)/gs);
  collectCalls("matches", /\bmatches\s*\(\s*([^)]*?)\s*\)/gs);

  for (const match of text.matchAll(/\bclassList\s*\.\s*(?:add|remove|toggle|contains|replace)\s*\([^)]*\)/gs)) {
    add("class-list", match);
  }

  for (const match of text.matchAll(/\b(?:querySelectorAll|querySelector|closest|matches)\s*\(\s*([^)]*?)\s*\)/gs)) {
    if (staticSelector(match[1]) === null) add("dynamic-selector", match);
  }

  for (const listener of text.matchAll(/\baddEventListener\s*\(\s*(['"`])([^'"`]+)\1/gs)) {
    const window = text.slice(listener.index, listener.index + 1000);
    const delegated = window.match(/(?:target|srcElement)[\s\S]{0,240}?\.(?:closest|matches)\s*\(\s*([^)]*?)\s*\)/);
    if (delegated) {
      const synthetic = [normalizeExpression(window.slice(0, delegated.index + delegated[0].length)), delegated[1]];
      synthetic.index = listener.index;
      add("event-delegation", synthetic, staticSelector(delegated[1]));
    }
  }

  for (const match of text.matchAll(/\b(?:form\s*\.\s*elements|elements\s*\[|\.elements\b|\.tagName\b|\.name\b|\[\s*name\s*=)/g)) {
    add("form-name-tag", match);
  }
  for (const match of text.matchAll(/\.(?:parentNode|parentElement|nextSibling|nextElementSibling|previousSibling|previousElementSibling|firstElementChild|lastElementChild|children)\b/g)) {
    add("dom-relations", match);
  }

  entries.sort((a, b) => a.line - b.line || a.category.localeCompare(b.category));
  const counts = Object.fromEntries(Object.keys(CATEGORY_LABELS).map((key) => [key, 0]));
  for (const entry of entries) counts[entry.category] += 1;
  return { name, counts, total: entries.length, entries };
}

function fingerprintCounts(page) {
  const counts = new Map();
  for (const entry of page.entries) {
    const key = `${entry.category}|${entry.expression}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
}

function comparePage(current, frozen) {
  const currentCounts = fingerprintCounts(current);
  const frozenCounts = fingerprintCounts(frozen);
  const missing = [];
  const added = [];
  for (const [fingerprint, count] of frozenCounts) {
    const delta = count - (currentCounts.get(fingerprint) || 0);
    if (delta > 0) missing.push({ fingerprint, count: delta });
  }
  for (const [fingerprint, count] of currentCounts) {
    const delta = count - (frozenCounts.get(fingerprint) || 0);
    if (delta > 0) added.push({ fingerprint, count: delta });
  }
  return { missing, added };
}

function escapeCell(value) {
  return String(value).replace(/\|/g, "\\|").replace(/`/g, "\\`");
}

function markdownForInventory(inventory) {
  const totalHooks = inventory.pages.reduce((sum, page) => sum + page.total, 0);
  const lines = [
    "# DOM Hooks Frozen Inventory",
    "",
    `Generated: ${inventory.generated_at}`,
    "",
    `Source scope: \`edu-frontend/public/*.html\` (${inventory.page_count} current pages, ${totalHooks} hook expressions).`,
    "",
    "> The dispatch document says 19 pages, while the current directory contains 25. The inventory intentionally follows the live filesystem so new pages cannot escape G3.",
    "",
    "Regenerate: `node scripts/gates/dom-hook-inventory.mjs --all`",
    "",
    "Verify: `node scripts/gates/dom-hook-inventory.mjs --all --check`",
    "",
    "A changed line number is allowed. A removed or newly introduced normalized hook expression is drift and makes `--check` fail until this inventory is deliberately regenerated.",
    "",
  ];

  for (const page of inventory.pages) {
    lines.push(`## ${page.name}`, "", `Total hooks: ${page.total}`, "", "| Category | Count |", "|---|---:|");
    for (const [category, label] of Object.entries(CATEGORY_LABELS)) {
      lines.push(`| ${label} | ${page.counts[category]} |`);
    }
    lines.push("", "| Line | Category | Selector | Expression |", "|---:|---|---|---|");
    if (!page.entries.length) lines.push("| - | - | - | No matching hook expressions |");
    for (const entry of page.entries) {
      lines.push(`| ${entry.line} | ${CATEGORY_LABELS[entry.category]} | ${escapeCell(entry.selector || "-")} | \`${escapeCell(entry.expression)}\` |`);
    }
    lines.push("");
  }
  return `${lines.join("\n").replace(/\n+$/, "")}\n`;
}

let options;
try {
  options = parseCli(process.argv.slice(2), { allowCheck: true });
} catch (error) {
  console.error(error.message);
  console.error(usage("dom-hook-inventory.mjs", "Options: --check compares against docs/dom-hooks-frozen.json."));
  process.exit(2);
}

if (options.help) {
  console.log(usage("dom-hook-inventory.mjs", "Options: --check compares against docs/dom-hooks-frozen.json."));
  process.exit(0);
}

const targets = resolveTargets(options);
const scanned = targets.map((target) => {
  if (!target.sourcePath) return { name: target.name, error: "No matching public HTML source.", counts: {}, total: 0, entries: [] };
  return scanSource(target.name, readFileSync(target.sourcePath, "utf8"));
});

const pages = [];
if (options.check) {
  const frozen = readJson(FROZEN_JSON);
  for (const current of scanned) {
    const expected = frozen?.pages?.find((page) => page.name === current.name);
    if (!expected) {
      pages.push({ name: current.name, url: targets.find((target) => target.name === current.name)?.url, checks: [makeCheck("frozen-page", false, "Page is absent from the frozen inventory.")] });
      continue;
    }
    const drift = comparePage(current, expected);
    pages.push({
      name: current.name,
      url: targets.find((target) => target.name === current.name)?.url,
      total: current.total,
      drift,
      checks: [
        makeCheck("frozen-hooks-present", drift.missing.length === 0, `${drift.missing.length} frozen hook fingerprints missing.`),
        makeCheck("new-hooks-reviewed", drift.added.length === 0, `${drift.added.length} new hook fingerprints require review.`),
      ],
    });
  }
} else {
  for (const current of scanned) {
    pages.push({
      name: current.name,
      url: targets.find((target) => target.name === current.name)?.url,
      total: current.total,
      counts: current.counts,
      checks: [makeCheck("source-scan", !current.error, current.error || `${current.total} hook expressions captured across 10 categories.`)],
    });
  }
  if (options.all) {
    const inventory = {
      schema_version: 1,
      generated_at: new Date().toISOString(),
      page_count: scanned.length,
      dispatch_page_count: 19,
      scope_drift: scanned.length !== 19,
      categories: CATEGORY_LABELS,
      pages: scanned,
    };
    ensureDir(path.dirname(FROZEN_MD));
    writeJson(FROZEN_JSON, inventory);
    writeFileSync(FROZEN_MD, markdownForInventory(inventory), "utf8");
  }
}

const report = finalizeReport("G3 DOM Hook Inventory", pages, {
  mode: options.check ? "check" : "inventory",
  frozen_markdown: path.relative(PROJECT_ROOT, FROZEN_MD),
  frozen_json: path.relative(PROJECT_ROOT, FROZEN_JSON),
  current_page_count: scanned.length,
  dispatch_page_count: 19,
});
const files = writeGateReports("g3-dom-hook-inventory", report, options.out);
printReport(report, files);
process.exitCode = report.status === "PASS" ? 0 : 1;
