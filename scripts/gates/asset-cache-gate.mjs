import path from "node:path";
import {
  PROJECT_ROOT,
  createBrowser,
  finalizeReport,
  makeCheck,
  parseCli,
  printReport,
  resolveTargets,
  usage,
  writeGateReports,
} from "./_shared.mjs";

function isLoopback(urlString) {
  try {
    const url = new URL(urlString);
    return ["127.0.0.1", "localhost", "::1", "[::1]"].includes(url.hostname);
  } catch {
    return true;
  }
}

function isNetworkUrl(url) {
  return /^https?:\/\//i.test(url);
}

const PAGE_ASSET_EXPRESSION = `(() => ({
  url: location.href,
  title: document.title,
  themeLinks: [...document.querySelectorAll("link[rel~=stylesheet]")]
    .map((link) => link.href)
    .filter((href) => /(?:^|\\/)theme\\.css(?:\\?|$)/.test(href))
    .map((href) => ({ href, version: new URL(href).searchParams.get("v") })),
  bodyTextLength: (document.body?.innerText || "").trim().length,
  bodyFontFamily: getComputedStyle(document.body).fontFamily,
  visibleText: Boolean((document.body?.innerText || "").trim()),
}))()`;

let options;
try {
  options = parseCli(process.argv.slice(2));
} catch (error) {
  console.error(error.message);
  console.error(usage("asset-cache-gate.mjs"));
  process.exit(2);
}
if (options.help) {
  console.log(usage("asset-cache-gate.mjs"));
  process.exit(0);
}

const targets = resolveTargets(options);
const browser = await createBrowser(options);
const pages = [];

try {
  await browser.setViewport(1280, 900);
  await browser.setReducedMotion(true);
  for (const target of targets) {
    const requests = new Map();
    const responses = [];
    const failures = [];
    const onRequest = (event) => requests.set(event.requestId, { url: event.request.url, type: event.type });
    const onResponse = (event) => responses.push({ requestId: event.requestId, url: event.response.url, status: event.response.status, type: event.type, mimeType: event.response.mimeType });
    const onFailure = (event) => failures.push({ requestId: event.requestId, ...requests.get(event.requestId), errorText: event.errorText, blockedReason: event.blockedReason });
    browser.cdp.on("Network.requestWillBeSent", onRequest);
    browser.cdp.on("Network.responseReceived", onResponse);
    browser.cdp.on("Network.loadingFailed", onFailure);

    let pageInfo = { url: "", themeLinks: [], visibleText: false, bodyFontFamily: "" };
    let runtimeError = null;
    let blockedFonts = 0;
    const blockedFontUrls = [];
    const onPaused = async (event) => {
      blockedFonts += 1;
      blockedFontUrls.push(event.request.url);
      try { await browser.cdp.send("Fetch.failRequest", { requestId: event.requestId, errorReason: "Failed" }); } catch {}
    };
    try {
      await browser.cdp.send("Fetch.enable", { patterns: [{ urlPattern: "*.woff2*", requestStage: "Request" }] });
      browser.cdp.on("Fetch.requestPaused", onPaused);
      await browser.cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
      await browser.navigate(target.url, options.settleMs);
      pageInfo = await browser.cdp.evaluate(PAGE_ASSET_EXPRESSION);
    } catch (error) {
      runtimeError = error.message;
    } finally {
      browser.cdp.off("Fetch.requestPaused", onPaused);
      try { await browser.cdp.send("Fetch.disable"); } catch {}
    }

    browser.cdp.off("Network.requestWillBeSent", onRequest);
    browser.cdp.off("Network.responseReceived", onResponse);
    browser.cdp.off("Network.loadingFailed", onFailure);

    const allRequests = [...requests.values()];
    const external = allRequests.filter((request) => isNetworkUrl(request.url) && !isLoopback(request.url));
    const resourceTypes = new Set(["Document", "Stylesheet", "Script", "Image", "Font", "Media"]);
    const local404 = responses.filter((response) => isLoopback(response.url) && resourceTypes.has(response.type) && response.status >= 400);
    const blockedSet = new Set(blockedFontUrls);
    const localFailures = failures.filter((failure) => failure.url && !blockedSet.has(failure.url) && isLoopback(failure.url) && resourceTypes.has(failure.type));
    const fontSourceErrors = [];
    for (const url of new Set(blockedFontUrls.filter(isLoopback))) {
      try {
        const response = await fetch(url);
        if (!response.ok) fontSourceErrors.push({ url, status: response.status });
      } catch (error) {
        fontSourceErrors.push({ url, error: error.message });
      }
    }
    const fallback = pageInfo;
    let expectedFontErrors = blockedFonts;
    const diagnostics = browser.cdp.diagnostics.filter((entry) => {
      if (expectedFontErrors > 0 && entry === "LOG: Failed to load resource: net::ERR_FAILED") {
        expectedFontErrors -= 1;
        return false;
      }
      return true;
    });

    const requested = new URL(target.url);
    const actual = pageInfo.url ? new URL(pageInfo.url) : null;
    const themeValid = pageInfo.themeLinks.length === 1 && Boolean(pageInfo.themeLinks[0].version);
    const checks = [
      makeCheck("runtime-inspection", !runtimeError, runtimeError || `${allRequests.length} requests observed.`),
      makeCheck("route-stable", actual?.pathname === requested.pathname, actual ? `Expected ${requested.pathname}, rendered ${actual.pathname}.` : "No rendered URL."),
      makeCheck("zero-external-requests", external.length === 0, `${external.length} external requests observed.`),
      makeCheck("theme-version-present", themeValid, `${pageInfo.themeLinks.length} theme.css links; version=${pageInfo.themeLinks[0]?.version || "missing"}.`),
      makeCheck("local-assets-ok", local404.length === 0 && localFailures.length === 0 && fontSourceErrors.length === 0, `${local404.length} local HTTP errors, ${localFailures.length} loading failures, and ${fontSourceErrors.length} unavailable blocked-font sources.`),
      makeCheck("font-fallback-visible", fallback.visibleText && Boolean(fallback.bodyFontFamily), `${blockedFonts} woff2 requests blocked; visible text=${fallback.visibleText}; fallback=${fallback.bodyFontFamily || "missing"}.`),
      makeCheck("console-errors", diagnostics.length === 0, `${diagnostics.length} runtime or console diagnostics (reported for G5 follow-up; non-blocking in G8).`, "warning"),
    ];
    pages.push({
      name: target.name,
      url: target.url,
      pageInfo,
      requestCount: allRequests.length,
      external,
      local404,
      localFailures,
      fontSourceErrors,
      blockedFonts,
      fallback,
      diagnostics,
      checks,
    });
    console.log(`[G8] ${target.name}: ${checks.every((item) => item.pass || item.severity === "warning") ? "PASS" : "FAIL"}`);
  }
} finally {
  await browser.close();
}

const versions = pages.flatMap((page) => page.pageInfo.themeLinks || []).map((link) => link.version).filter(Boolean);
const uniqueVersions = [...new Set(versions)];
const versionConsistent = versions.length === pages.length && uniqueVersions.length === 1;
for (const page of pages) {
  page.checks.push(makeCheck("site-theme-version", versionConsistent, `${versions.length}/${pages.length} pages versioned; versions=${uniqueVersions.join(",") || "none"}.`));
}

const report = finalizeReport("G8 Asset and Cache Gate", pages, {
  chrome: browser.chromeVersion,
  themeVersions: uniqueVersions,
  versionConsistent,
  network_policy: "Loopback frontend/API traffic is allowed; every non-loopback HTTP(S) request fails the gate.",
});
const files = writeGateReports("g8-asset-cache-gate", report, options.out);
printReport(report, files);
process.exitCode = report.status === "PASS" ? 0 : 1;
