import path from "node:path";
import {
  PROJECT_ROOT,
  createBrowser,
  finalizeReport,
  makeCheck,
  parseCli,
  printReport,
  readJson,
  resolveTargets,
  safeStem,
  usage,
  writeGateReports,
  writeJson,
} from "./_shared.mjs";

const VIEWPORTS = [360, 768, 1280, 1440, 1920];

const A11Y_EXPRESSION = `(() => {
  const visible = (element) => {
    if (!element || element.nodeType !== 1) return false;
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
  const parse = (value) => {
    const numbers = value.match(/[\\d.]+/g)?.map(Number) || [];
    if (numbers.length < 3) return [0, 0, 0, 1];
    return [numbers[0], numbers[1], numbers[2], numbers[3] ?? 1];
  };
  const blend = (front, back) => {
    const alpha = front[3] + back[3] * (1 - front[3]);
    if (!alpha) return [255, 255, 255, 1];
    return [0, 1, 2].map((index) => (front[index] * front[3] + back[index] * back[3] * (1 - front[3])) / alpha).concat(alpha);
  };
  const backgroundFor = (element) => {
    const layers = [];
    let node = element;
    while (node && node.nodeType === 1) {
      layers.push(parse(getComputedStyle(node).backgroundColor));
      node = node.parentElement;
    }
    let color = [255, 255, 255, 1];
    for (let index = layers.length - 1; index >= 0; index -= 1) color = blend(layers[index], color);
    return color;
  };
  const luminance = (color) => {
    const channel = color.slice(0, 3).map((value) => value / 255).map((value) => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
    return .2126 * channel[0] + .7152 * channel[1] + .0722 * channel[2];
  };
  const ratio = (front, back) => {
    const fg = blend(front, back);
    const a = luminance(fg);
    const b = luminance(back);
    return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
  };
  const contrastFailures = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const measured = new Set();
  while (walker.nextNode()) {
    const text = walker.currentNode.textContent.trim();
    const element = walker.currentNode.parentElement;
    if (!text || !visible(element) || /^(script|style|noscript|template)$/i.test(element.localName)) continue;
    const key = cssPath(element) + "|" + text.slice(0, 80);
    if (measured.has(key)) continue;
    measured.add(key);
    const style = getComputedStyle(element);
    const value = ratio(parse(style.color), backgroundFor(element));
    if (value < 4.5) contrastFailures.push({ selector: cssPath(element), text: text.slice(0, 100), ratio: Math.round(value * 100) / 100, color: style.color, background: backgroundFor(element).map((part) => Math.round(part * 100) / 100) });
  }
  for (const element of document.querySelectorAll("input[placeholder], textarea[placeholder]")) {
    if (!visible(element)) continue;
    const style = getComputedStyle(element, "::placeholder");
    const value = ratio(parse(style.color), backgroundFor(element));
    if (value < 4.5) contrastFailures.push({ selector: cssPath(element) + "::placeholder", text: element.placeholder.slice(0, 100), ratio: Math.round(value * 100) / 100, color: style.color, background: backgroundFor(element).map((part) => Math.round(part * 100) / 100) });
  }
  const focusableSelector = "a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), [role=button]:not([aria-disabled=true]), [role=link], [tabindex]:not([tabindex='-1'])";
  const focusable = [...document.querySelectorAll(focusableSelector)].filter(visible).map(cssPath);
  const unlabeledIconControls = [...document.querySelectorAll("button, [role=button], a[href]")].filter(visible).filter((element) => {
    const text = (element.innerText || "").trim();
    const name = element.getAttribute("aria-label") || element.getAttribute("title") || element.querySelector("img[alt]")?.alt || "";
    return !text && !name;
  }).map(cssPath);
  const attrs = [...document.querySelectorAll("[aria-label], [title]")].map((element) => ({
    selector: cssPath(element),
    ariaLabel: element.getAttribute("aria-label"),
    title: element.getAttribute("title"),
  }));
  const runningAnimations = document.getAnimations().filter((animation) => animation.playState === "running").length;
  return {
    url: location.href,
    viewport: { width: innerWidth, height: innerHeight },
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    contrastChecked: measured.size,
    contrastFailures: contrastFailures.slice(0, 200),
    focusable,
    unlabeledIconControls,
    attrs,
    reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
    runningAnimations,
  };
})()`;

const ACTIVE_FOCUS_EXPRESSION = `(() => {
  const element = document.activeElement;
  if (!element || element === document.body || element === document.documentElement) return null;
  const cssPath = (node) => {
    if (node.id) return "#" + CSS.escape(node.id);
    const parts = [];
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
  const style = getComputedStyle(element);
  const rect = element.getBoundingClientRect();
  const ring = (parseFloat(style.outlineWidth) > 0 && style.outlineStyle !== "none") || style.boxShadow !== "none";
  return { selector: cssPath(element), ring, outline: style.outline, boxShadow: style.boxShadow, visibleInViewport: rect.bottom > 0 && rect.top < innerHeight && rect.right > 0 && rect.left < innerWidth };
})()`;

function compareAttrs(current, expected) {
  const actual = new Map(current.map((item) => [item.selector, item]));
  const missing = [];
  for (const item of expected || []) {
    const found = actual.get(item.selector);
    if (!found || found.ariaLabel !== item.ariaLabel || found.title !== item.title) missing.push(item);
  }
  return missing;
}

async function tabAudit(cdp, expectedCount) {
  await cdp.evaluate("document.activeElement && document.activeElement.blur(); document.body.tabIndex = -1; document.body.focus(); true");
  const visits = [];
  const steps = Math.min(Math.max(expectedCount + 4, 8), 350);
  for (let index = 0; index < steps; index += 1) {
    await cdp.send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    const active = await cdp.evaluate(ACTIVE_FOCUS_EXPRESSION);
    if (active) visits.push(active);
  }
  const unique = new Map(visits.map((visit) => [visit.selector, visit]));
  return { visits, unique: [...unique.values()] };
}

let options;
try {
  options = parseCli(process.argv.slice(2), { allowBaseline: true });
} catch (error) {
  console.error(error.message);
  console.error(usage("viewport-a11y-gate.mjs", "Options: --update-baseline deliberately replaces the frozen aria-label/title snapshot."));
  process.exit(2);
}
if (options.help) {
  console.log(usage("viewport-a11y-gate.mjs", "Options: --update-baseline deliberately replaces the frozen aria-label/title snapshot."));
  process.exit(0);
}

const targets = resolveTargets(options);
const baselinePath = path.join(options.out, "viewport-a11y-snapshot.json");
const baseline = readJson(baselinePath, { schema_version: 1, pages: {} });
const browser = await createBrowser(options);
const snapshots = {};
const pages = [];

try {
  await browser.setReducedMotion(true);
  for (const target of targets) {
    const viewportResults = [];
    let runtimeError = null;
    for (const width of VIEWPORTS) {
      try {
        await browser.setViewport(width, 900);
        await browser.navigate(target.url, options.settleMs);
        const audit = await browser.cdp.evaluate(A11Y_EXPRESSION);
        const screenshot = path.join(options.out, "g7-screenshots", safeStem(target.name), `${width}.jpg`);
        await browser.screenshot(screenshot);
        viewportResults.push({ width, screenshot: path.relative(PROJECT_ROOT, screenshot), ...audit });
      } catch (error) {
        runtimeError = `${width}px: ${error.message}`;
        break;
      }
    }

    let focus = { visits: [], unique: [] };
    if (!runtimeError && viewportResults.length) {
      await browser.setViewport(1280, 900);
      await browser.navigate(target.url, Math.min(options.settleMs, 500));
      focus = await tabAudit(browser.cdp, viewportResults.find((item) => item.width === 1280)?.focusable.length || 0);
    }

    const canonical = viewportResults.find((item) => item.width === 1280) || viewportResults[0] || { attrs: [], focusable: [], unlabeledIconControls: [] };
    snapshots[target.name] = { attrs: canonical.attrs || [] };
    const expected = baseline.pages?.[target.name]?.attrs;
    const lostAttrs = expected ? compareAttrs(canonical.attrs || [], expected) : [];
    const overflowViews = viewportResults.filter((item) => item.overflow);
    const contrastFailures = viewportResults.flatMap((item) => (item.contrastFailures || []).map((failure) => ({ width: item.width, ...failure })));
    const requested = new URL(target.url);
    const redirected = viewportResults.filter((item) => new URL(item.url).pathname !== requested.pathname);
    const focusWithoutRing = focus.unique.filter((item) => !item.ring);
    const focusObscured = focus.unique.filter((item) => !item.visibleInViewport);
    const focusable = canonical.focusable || [];
    const reached = new Set(focus.unique.map((item) => item.selector));
    const unreachable = focusable.filter((selector) => !reached.has(selector));
    const runningAnimations = viewportResults.reduce((max, item) => Math.max(max, item.runningAnimations || 0), 0);
    const checks = [
      makeCheck("five-viewports", !runtimeError && viewportResults.length === VIEWPORTS.length, runtimeError || `${viewportResults.length}/${VIEWPORTS.length} viewport screenshots captured.`),
      makeCheck("route-stable", redirected.length === 0, `${redirected.length}/${viewportResults.length} viewport loads redirected away from ${requested.pathname}.`),
      makeCheck("no-horizontal-overflow", overflowViews.length === 0, `${overflowViews.length}/${viewportResults.length} viewports overflow horizontally.`),
      makeCheck("contrast-4.5", contrastFailures.length === 0, `${contrastFailures.length} text samples are below 4.5:1.`),
      makeCheck("tab-reachable", unreachable.length === 0, `${focus.unique.length}/${focusable.length} visible focusable elements reached by Tab.`),
      makeCheck("focus-visible", focusWithoutRing.length === 0, `${focusWithoutRing.length}/${focus.unique.length} reached elements lack a visible focus ring.`),
      makeCheck("focus-not-obscured", focusObscured.length === 0, `${focusObscured.length}/${focus.unique.length} reached elements are outside the visible viewport after focus.`),
      makeCheck("icon-control-name", (canonical.unlabeledIconControls || []).length === 0, `${(canonical.unlabeledIconControls || []).length} visible icon-only controls lack an accessible name.`),
      makeCheck("aria-title-frozen", !expected || lostAttrs.length === 0, expected ? `${lostAttrs.length} frozen aria-label/title entries are missing or changed.` : "No prior snapshot; current attributes captured.", expected ? "error" : "warning"),
      makeCheck("reduced-motion", viewportResults.every((item) => item.reducedMotion) && runningAnimations === 0, `Media emulation active=${viewportResults.every((item) => item.reducedMotion)}; running animations=${runningAnimations}.`),
      makeCheck("console-errors", browser.cdp.diagnostics.length === 0, `${browser.cdp.diagnostics.length} uncaught runtime or console errors after the final load.`),
    ];
    pages.push({
      name: target.name,
      url: target.url,
      viewportResults,
      focus,
      lostAttrs,
      unreachable: unreachable.slice(0, 200),
      focusWithoutRing: focusWithoutRing.slice(0, 200),
      contrastFailures: contrastFailures.slice(0, 300),
      diagnostics: [...browser.cdp.diagnostics],
      checks,
    });
    console.log(`[G7] ${target.name}: ${checks.every((item) => item.pass || item.severity === "warning") ? "PASS" : "FAIL"}`);
  }
} finally {
  await browser.close();
}

if (options.updateBaseline || !Object.keys(baseline.pages || {}).length) {
  writeJson(baselinePath, {
    schema_version: 1,
    generated_at: new Date().toISOString(),
    chrome: browser.chromeVersion,
    page_count: Object.keys(snapshots).length,
    pages: snapshots,
  });
}

const report = finalizeReport("G7 Viewport and Accessibility Gate", pages, {
  chrome: browser.chromeVersion,
  viewports: VIEWPORTS,
  baseline: path.relative(PROJECT_ROOT, baselinePath),
  baseline_created: options.updateBaseline || !Object.keys(baseline.pages || {}).length,
  contrast_note: "Computed solid background-color stack; gradient/image contrast still requires screenshot review.",
});
const files = writeGateReports("g7-viewport-a11y-gate", report, options.out);
printReport(report, files);
process.exitCode = report.status === "PASS" ? 0 : 1;
