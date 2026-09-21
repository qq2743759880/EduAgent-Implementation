import { readFileSync } from "node:fs";
import path from "node:path";
import {
  PROJECT_ROOT,
  assertDevBase,
  createBrowser,
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

const LAYOUT_PROPERTIES = ["display", "height", "maxHeight", "position", "overflow", "overflowX", "overflowY", "pointerEvents"];

function collectGeometrySelectors(source) {
  const terms = "offsetWidth|offsetHeight|scrollWidth|scrollHeight|clientWidth|clientHeight|getBoundingClientRect";
  const selectors = new Set();
  const assignments = new Map();
  for (const match of source.matchAll(new RegExp("(?:const|let|var)\\s+([A-Za-z_$][\\w$]*)\\s*=\\s*(?:document\\.)?(getElementById|querySelector)\\s*\\(\\s*(['\"`])([^'\"`$]+)\\3\\s*\\)", "g"))) {
    assignments.set(match[1], match[2] === "getElementById" ? `#${match[4]}` : match[4]);
  }
  for (const [variable, selector] of assignments) {
    if (new RegExp(`\\b${variable.replace(/[$]/g, "\\$")}\\s*\\.\\s*(?:${terms})\\b`).test(source)) selectors.add(selector);
  }
  for (const match of source.matchAll(new RegExp("(?:document\\.)?(getElementById|querySelector)\\s*\\(\\s*(['\"`])([^'\"`$]+)\\2\\s*\\)[\\s\\S]{0,80}?\\.\\s*(?:" + terms + ")\\b", "g"))) {
    selectors.add(match[1] === "getElementById" ? `#${match[3]}` : match[3]);
  }
  return [...selectors].sort();
}

function compareSnapshot(current, expected) {
  const missing = [];
  const changed = [];
  const expectedGeometry = new Map((expected?.geometry || []).map((item) => [item.selector, item]));
  const currentGeometry = new Map((current.geometry || []).map((item) => [item.selector, item]));
  for (const [selector, baseline] of expectedGeometry) {
    const actual = currentGeometry.get(selector);
    if (!actual) {
      missing.push({ type: "geometry", selector });
      continue;
    }
    for (const property of LAYOUT_PROPERTIES) {
      if (actual.style[property] !== baseline.style[property]) {
        changed.push({ type: "layout", selector, property, expected: baseline.style[property], actual: actual.style[property] });
      }
    }
  }

  const expectedLayers = new Map((expected?.zLayers || []).map((item) => [item.selector, item.zIndex]));
  const currentLayers = new Map((current.zLayers || []).map((item) => [item.selector, item.zIndex]));
  for (const [selector, zIndex] of expectedLayers) {
    if (!currentLayers.has(selector)) missing.push({ type: "z-index", selector });
    else if (currentLayers.get(selector) !== zIndex) changed.push({ type: "z-index", selector, expected: zIndex, actual: currentLayers.get(selector) });
  }
  return { missing, changed };
}

const INSPECT_EXPRESSION = (selectors) => `(() => {
  const geometrySelectors = ${JSON.stringify(selectors)};
  const visible = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
  };
  const cssPath = (element) => {
    if (!element || element.nodeType !== 1) return "";
    if (element.id) return "#" + CSS.escape(element.id);
    const parts = [];
    let node = element;
    while (node && node !== document.documentElement && parts.length < 7) {
      let part = node.localName;
      const stable = [...node.classList].filter((name) => !/^(active|open|show|hidden|loading|disabled|on|selected)$/.test(name)).slice(0, 2);
      if (stable.length) part += stable.map((name) => "." + CSS.escape(name)).join("");
      const peers = node.parentElement ? [...node.parentElement.children].filter((peer) => peer.localName === node.localName) : [];
      if (peers.length > 1) part += ":nth-of-type(" + (peers.indexOf(node) + 1) + ")";
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(" > ");
  };
  const styleRecord = (element) => {
    const style = getComputedStyle(element);
    return Object.fromEntries(${JSON.stringify(LAYOUT_PROPERTIES)}.map((property) => [property, style[property]]));
  };
  const geometry = [];
  for (const selector of geometrySelectors) {
    let element = null;
    try { element = document.querySelector(selector); } catch {}
    if (element) geometry.push({ selector, path: cssPath(element), style: styleRecord(element), rect: element.getBoundingClientRect().toJSON() });
  }
  const zLayers = [...document.querySelectorAll("body *")]
    .filter(visible)
    .map((element) => ({ element, zIndex: getComputedStyle(element).zIndex }))
    .filter(({ zIndex }) => zIndex !== "auto" && zIndex !== "0")
    .map(({ element, zIndex }) => ({ selector: cssPath(element), zIndex }))
    .slice(0, 300);
  const thirdPartySelector = ".markdown, .markdown-body, [class*=markdown], pre, .chart, [class*=chart], [data-chart], .table-scroll, .w-md-editor, canvas";
  const thirdParty = [...document.querySelectorAll(thirdPartySelector)].filter(visible).map((element) => {
    const target = element.matches("canvas") && element.parentElement ? element.parentElement : element;
    const background = getComputedStyle(target).backgroundColor;
    return { selector: cssPath(element), background, opaque: !/^rgba?\\(0, 0, 0(?:, 0)?\\)$/.test(background) && background !== "transparent" };
  }).slice(0, 300);
  const interactiveSelector = "a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], [tabindex]:not([tabindex='-1'])";
  const interactive = [...document.querySelectorAll(interactiveSelector)].filter(visible).map((element) => {
    const rect = element.getBoundingClientRect();
    return { selector: cssPath(element), tag: element.localName, width: Math.round(rect.width * 10) / 10, height: Math.round(rect.height * 10) / 10, disabled: Boolean(element.disabled || element.getAttribute("aria-disabled") === "true") };
  }).slice(0, 1200);
  return {
    url: location.href,
    title: document.title,
    geometry,
    zLayers,
    thirdParty,
    interactive,
    viewport: { width: innerWidth, height: innerHeight },
  };
})()`;

let options;
try {
  options = parseCli(process.argv.slice(2), { allowBaseline: true });
} catch (error) {
  console.error(error.message);
  console.error(usage("style-dep-gate.mjs", "Options: --update-baseline deliberately replaces the frozen computed-style snapshot."));
  process.exit(2);
}
if (options.help) {
  console.log(usage("style-dep-gate.mjs", "Options: --update-baseline deliberately replaces the frozen computed-style snapshot."));
  process.exit(0);
}

const targets = resolveTargets(options);
await assertDevBase(options, targets);
const baselinePath = path.join(options.out, "style-dep-snapshot.json");
const existingBaseline = readJson(baselinePath, { schema_version: 1, pages: {} });
const browser = await createBrowser(options);
const captured = {};
const pages = [];

try {
  await browser.setViewport(1280, 900);
  await browser.setReducedMotion(true);
  for (const target of targets) {
    const source = target.sourcePath ? readFileSync(target.sourcePath, "utf8") : "";
    const geometrySelectors = collectGeometrySelectors(source);
    let snapshot = { url: "", geometry: [], zLayers: [], thirdParty: [], interactive: [] };
    let runtimeError = null;
    try {
      await browser.navigate(target.url, options.settleMs);
      snapshot = await browser.cdp.evaluate(INSPECT_EXPRESSION(geometrySelectors));
    } catch (error) {
      runtimeError = error.message;
    }
    captured[target.name] = snapshot;

    const expected = existingBaseline.pages?.[target.name];
    const drift = expected ? compareSnapshot(snapshot, expected) : { missing: [], changed: [] };
    const tooSmall = snapshot.interactive.filter((item) => item.width < 44 || item.height < 44);
    const transparent = snapshot.thirdParty.filter((item) => !item.opaque);
    const requested = new URL(target.url);
    const actual = snapshot.url ? new URL(snapshot.url) : null;
    const routeMatches = actual && actual.pathname === requested.pathname;
    const checks = [
      makeCheck("runtime-inspection", !runtimeError, runtimeError || `${snapshot.interactive.length} interactive elements inspected.`),
      makeCheck("route-stable", routeMatches, actual ? `Expected ${requested.pathname}, rendered ${actual.pathname}.` : "No rendered URL."),
      makeCheck("layout-blacklist", !expected || (drift.missing.length === 0 && drift.changed.length === 0), expected ? `${drift.missing.length} missing and ${drift.changed.length} changed frozen style entries.` : "No prior snapshot; current values captured.", expected ? "error" : "warning"),
      makeCheck("third-party-background", transparent.length === 0, `${transparent.length}/${snapshot.thirdParty.length} third-party or rich-content containers have transparent backgrounds.`),
      makeCheck("interactive-target-44", tooSmall.length === 0, `${tooSmall.length}/${snapshot.interactive.length} visible targets are smaller than 44x44 CSS px.`),
      makeCheck("console-errors", browser.cdp.diagnostics.length === 0, `${browser.cdp.diagnostics.length} uncaught runtime or console errors.`),
    ];
    pages.push({
      name: target.name,
      url: target.url,
      geometrySelectors,
      snapshot,
      drift,
      tooSmall: tooSmall.slice(0, 100),
      transparent: transparent.slice(0, 100),
      diagnostics: [...browser.cdp.diagnostics],
      checks,
    });
    console.log(`[G6] ${target.name}: ${checks.every((item) => item.pass || item.severity === "warning") ? "PASS" : "FAIL"}`);
  }
} finally {
  await browser.close();
}

if (options.updateBaseline || !Object.keys(existingBaseline.pages || {}).length) {
  writeJson(baselinePath, {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    chrome: browser.chromeVersion,
    page_count: Object.keys(captured).length,
    pages: captured,
  });
}

const report = finalizeReport("G6 Style Dependency Gate", pages, {
  chrome: browser.chromeVersion,
  baseline: path.relative(PROJECT_ROOT, baselinePath),
  baseline_created: options.updateBaseline || !Object.keys(existingBaseline.pages || {}).length,
});
const files = writeGateReports("g6-style-dep-gate", report, options.out);
printReport(report, files);
process.exitCode = report.status === "PASS" ? 0 : 1;
