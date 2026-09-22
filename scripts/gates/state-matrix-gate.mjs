import path from "node:path";
import {
  PROJECT_ROOT,
  assertDevBase,
  createBrowser,
  finalizeReport,
  makeCheck,
  parseCli,
  printReport,
  resolveTargets,
  roleForPage,
  roleReasonForPage,
  safeStem,
  usage,
  writeGateReports,
} from "./_shared.mjs";

const STATES = ["empty", "loading", "error", "forbidden", "disabled", "long-text", "token-expired", "server-500"];

function ok(data) {
  return { code: 0, message: "ok", data };
}

function authUser(role) {
  return ok({ user_id: 1, id: 1, username: role === "student" ? "gate-student" : "gate-admin", nickname: role === "student" ? "Gate Student" : "Gate Admin", role: role || "admin", status: 1 });
}

function emptyData(url) {
  const pathname = new URL(url).pathname;
  if (/\/(history|messages|recommendations|calendar|sessions|tracks)(?:\/|$)/.test(pathname)) return [];
  if (/\/profile(?:\/|$)/.test(pathname)) return { nickname: "Gate User", weekly_available_hours: 0, learning_goals: [], subject_preferences: [], level_assessments: [], interest_tags: [] };
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
}

function populatedData(state) {
  const long = "A deliberately long gate value without spaces_".repeat(22);
  return {
    items: [{
      id: 1,
      user_id: 1,
      title: state === "long-text" ? long : "Gate state item",
      name: state === "long-text" ? long : "Gate state item",
      series_name: state === "long-text" ? long : "Gate state course",
      content: state === "long-text" ? long : "Gate state content",
      description: state === "long-text" ? long : "Gate state description",
      status: state === "disabled" ? "disabled" : "active",
      enabled: state !== "disabled",
      disabled: state === "disabled",
      role: "student",
      role_code: "student",
      progress: 0,
      created_at: "2026-09-20T00:00:00Z",
    }],
    total: 1,
    page: 1,
    page_size: 20,
    total_pages: 1,
  };
}

function mockResponse(url, state, role) {
  const pathname = new URL(url).pathname;
  if (pathname.endsWith("/api/auth/me") && !["forbidden", "token-expired", "server-500"].includes(state)) {
    return { status: 200, body: authUser(role) };
  }
  if (state === "empty") return { status: 200, body: ok(emptyData(url)) };
  if (state === "forbidden") return { status: 403, body: { code: 40300, message: "Gate injected forbidden state", data: null } };
  if (state === "disabled") return { status: 200, body: ok(populatedData(state)) };
  if (state === "long-text") return { status: 200, body: ok(populatedData(state)) };
  if (state === "token-expired") return { status: 401, body: { code: 40101, message: "Gate injected expired token", data: null } };
  if (state === "server-500") return { status: 500, body: { code: 50000, message: "Gate injected server error", data: null } };
  return { status: 200, body: ok(emptyData(url)) };
}

const LAYOUT_EXPRESSION = `(() => {
  const root = document.documentElement;
  if (!root || !document.body) return { url: location.href, title: document.title, bodyTextLength: 0, bodyHeight: 0, viewport: { width: innerWidth, height: innerHeight }, horizontalOverflow: false, broken: [], transitional: true };
  const visible = (element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity) !== 0 && rect.width > 0 && rect.height > 0;
  };
  const cssPath = (element) => {
    if (element.id) return "#" + CSS.escape(element.id);
    const parts = [];
    let node = element;
    while (node && node !== document.documentElement && parts.length < 6) {
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
  const broken = [...document.querySelectorAll("body *")].filter(visible).filter((element) => {
    const style = getComputedStyle(element);
    return element.scrollWidth > element.clientWidth + 4 && ["visible", "clip"].includes(style.overflowX);
  }).map((element) => ({ selector: cssPath(element), clientWidth: element.clientWidth, scrollWidth: element.scrollWidth })).slice(0, 100);
  return {
    url: location.href,
    title: document.title,
    bodyTextLength: (document.body?.innerText || "").trim().length,
    bodyHeight: root.scrollHeight,
    viewport: { width: innerWidth, height: innerHeight },
    horizontalOverflow: root.scrollWidth > root.clientWidth + 1,
    broken,
    transitional: false,
  };
})()`;

let options;
try {
  options = parseCli(process.argv.slice(2));
} catch (error) {
  console.error(error.message);
  console.error(usage("state-matrix-gate.mjs"));
  process.exit(2);
}
if (options.help) {
  console.log(usage("state-matrix-gate.mjs"));
  process.exit(0);
}

if (!process.env.EDU_GATE_TOKEN) process.env.EDU_GATE_TOKEN = "gate-state-token";
const targets = resolveTargets(options);
await assertDevBase(options, targets);
// T13B scan identity must be resolved BEFORE createBrowser: the identity injection
// registers Page.addScriptToEvaluateOnNewDocument at browser startup.
options.studentIdentity = targets.some((target) => roleForPage(target.name) === "student");
const browser = await createBrowser(options);
const pages = [];

try {
  await browser.setViewport(1280, 900);
  await browser.setReducedMotion(true);
  for (const target of targets) {
    // T13B scan identity (per-page flip: last-writer-wins between the two registered
    // identity scripts — see _shared.mjs createBrowser).
    // G9 note: the state mocks intercept /api/*, and mockResponse answers auth/me as
    // admin by default — for a student-role page the mock honors the page identity
    // so the guard sees a student, matching the real page contract.
    const pageRole = roleForPage(target.name);
    options.studentIdentity = pageRole === "student";
    const stateResults = [];
    for (const state of STATES) {
      let intercepted = 0;
      const held = [];
      let runtimeError = null;
      const onPaused = async (event) => {
        intercepted += 1;
        if (state === "loading" && event.request.method !== "OPTIONS") {
          held.push(event.requestId);
          return;
        }
        try {
          if (event.request.method === "OPTIONS") {
            await browser.cdp.send("Fetch.fulfillRequest", {
              requestId: event.requestId,
              responseCode: 204,
              responseHeaders: [
                { name: "Access-Control-Allow-Origin", value: "*" },
                { name: "Access-Control-Allow-Headers", value: "*" },
                { name: "Access-Control-Allow-Methods", value: "GET,POST,PUT,PATCH,DELETE,OPTIONS" },
              ],
            });
            return;
          }
          if (state === "error") {
            await browser.cdp.send("Fetch.failRequest", { requestId: event.requestId, errorReason: "ConnectionRefused" });
            return;
          }
          const response = mockResponse(event.request.url, state, pageRole);
          const body = Buffer.from(JSON.stringify(response.body), "utf8").toString("base64");
          await browser.cdp.send("Fetch.fulfillRequest", {
            requestId: event.requestId,
            responseCode: response.status,
            responsePhrase: response.status === 200 ? "OK" : "Gate Injected",
            responseHeaders: [
              { name: "Content-Type", value: "application/json; charset=utf-8" },
              { name: "Access-Control-Allow-Origin", value: "*" },
              { name: "Cache-Control", value: "no-store" },
            ],
            body,
          });
        } catch {}
      };

      let layout = { url: "", bodyTextLength: 0, horizontalOverflow: false, broken: [] };
      let readyWindow = null;
      try {
        await browser.cdp.send("Fetch.enable", { patterns: [
          { urlPattern: "*://127.0.0.1:*/api/*", requestStage: "Request" },
          { urlPattern: "*://localhost:*/api/*", requestStage: "Request" },
        ] });
        browser.cdp.on("Fetch.requestPaused", onPaused);
        await browser.navigate(target.url, state === "loading" ? Math.min(options.settleMs, 650) : options.settleMs);
        // GATE-V3 data-ready stable window for the mock-driven states (empty /
        // disabled / long-text): the mock fulfills instantly, so network-idle plus
        // two consistent LAYOUT snapshots prove the render has absorbed the mocked
        // data before sampling. For states that hold or fail requests by design
        // (loading holds every /api/ request; error/forbidden/500 break them) the
        // window is skipped — waiting would only burn its timeout, and the existing
        // transitional-poll below already guards the DOM shape. Bounded by
        // EDU_GATE_READY_TIMEOUT_MS; 0 disables entirely (legacy behavior).
        const readyWindowEligible = options.readyTimeoutMs > 0 && ["empty", "disabled", "long-text"].includes(state);
        if (readyWindowEligible) {
          readyWindow = await browser.waitForReady(() => browser.cdp.evaluate(LAYOUT_EXPRESSION));
        }
        for (let attempt = 0; attempt < 6; attempt += 1) {
          layout = await browser.cdp.evaluate(LAYOUT_EXPRESSION);
          if (!layout.transitional) break;
          await new Promise((resolve) => setTimeout(resolve, 100));
        }
        const screenshot = path.join(options.out, "g9-screenshots", safeStem(target.name), `${state}.jpg`);
        await browser.screenshot(screenshot);
        layout.screenshot = path.relative(PROJECT_ROOT, screenshot);
      } catch (error) {
        runtimeError = error.message;
      } finally {
        for (const requestId of held) {
          try { await browser.cdp.send("Fetch.failRequest", { requestId, errorReason: "Aborted" }); } catch {}
        }
        browser.cdp.off("Fetch.requestPaused", onPaused);
        try { await browser.cdp.send("Fetch.disable"); } catch {}
        await new Promise((resolve) => setTimeout(resolve, 50));
      }

      const requested = new URL(target.url);
      const actual = layout.url ? new URL(layout.url) : null;
      const routeExpected = intercepted === 0
        ? true
        : state === "token-expired"
        ? actual?.pathname.endsWith("/login-register.html")
        : actual?.pathname === requested.pathname;
      const diagnostics = [...browser.cdp.diagnostics];
      const exceptions = diagnostics.filter((entry) => entry.startsWith("EXC:"));
      const expectedNetworkNoise = ["loading", "error", "forbidden", "token-expired", "server-500"].includes(state);
      const naReason = options.na.has(target.name) ? options.naReasons.get(target.name) || "no reason recorded" : null;
      const checks = [
        makeCheck("state-intercepted", intercepted > 0 || Boolean(naReason), naReason
          ? `SKIP: structurally N/A for this page (${naReason}); ${intercepted} API requests observed.`
          : `${intercepted} API requests intercepted.`, naReason ? "skip" : "error"),
        makeCheck("state-route", routeExpected, actual ? `Rendered ${actual.pathname}; source ${requested.pathname}.` : "No rendered URL."),
        makeCheck("state-visible", !runtimeError && layout.bodyTextLength > 0, runtimeError || `Visible text length=${layout.bodyTextLength}.`),
        makeCheck("state-no-horizontal-overflow", !layout.horizontalOverflow, `horizontalOverflow=${layout.horizontalOverflow}.`),
        makeCheck("state-long-content-fit", layout.broken.length === 0, `${layout.broken.length} visible elements leak overflowing content.`),
        makeCheck("state-runtime-exceptions", exceptions.length === 0, `${exceptions.length} uncaught runtime exceptions; ${diagnostics.length} total console/log diagnostics.`),
        makeCheck("state-console-errors", diagnostics.length === 0, `${diagnostics.length} console/log diagnostics.`, expectedNetworkNoise ? "warning" : "error"),
      ];
      stateResults.push({ state, intercepted, layout, readyWindow, diagnostics, checks });
    }

    const checks = stateResults.flatMap((result) => result.checks.map((check) => ({ ...check, name: `${result.state}/${check.name}` })));
    pages.push({ name: target.name, url: target.url, scan_role: pageRole, scan_role_reason: roleReasonForPage(target.name) || undefined, states: stateResults, checks });
    console.log(`[G9] ${target.name}: ${checks.every((item) => item.pass || item.severity === "warning") ? "PASS" : "FAIL"}`);
  }
} finally {
  await browser.close();
}

const report = finalizeReport("G9 State Matrix Gate", pages, {
  chrome: browser.chromeVersion,
  states: STATES,
  mock_policy: "All loopback /api/ requests are intercepted. auth/me remains an identity success except in authorization and server-failure states; the identity follows the page scan role (scripts/gates/page-roles.json, default admin).",
  scan_identity: "per-page via scripts/gates/page-roles.json (default admin; role-guarded pages scan under EDU_GATE_STUDENT_TOKEN when set); no check relaxed",
  ready_window: "mock-driven states (empty/disabled/long-text) sample after network idle + two consistent DOM snapshots (EDU_GATE_READY_TIMEOUT_MS, default 5000ms cap); hold/fail states skip the window by design",
});
const files = writeGateReports("g9-state-matrix-gate", report, options.out);
printReport(report, files);
process.exitCode = report.status === "PASS" ? 0 : 1;
