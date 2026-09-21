import { createHash, randomBytes } from "node:crypto";
import { EventEmitter } from "node:events";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { createServer, createConnection } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

export const PROJECT_ROOT = path.resolve(HERE, "../..");
export const PUBLIC_DIR = path.join(PROJECT_ROOT, "edu-frontend", "public");
export const DEFAULT_BASE = "http://127.0.0.1:3322";
export const DEFAULT_OUT = path.join(PROJECT_ROOT, "test-reports", "gate-baseline");

const ROUTE_QUERY = new Map([
  ["admin-course-detail.html", "?id=1"],
  ["admin-question-detail.html", "?id=1"],
  ["community-post.html", "?post_id=96"],
  ["course-detail.html", "?id=1"],
]);

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function ensureDir(dir) {
  mkdirSync(dir, { recursive: true });
  return dir;
}

export function listHtmlPages() {
  return readdirSync(PUBLIC_DIR, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".html"))
    .map((entry) => entry.name)
    .sort((a, b) => a.localeCompare(b));
}

export function routeForPage(name) {
  return `/${name}${ROUTE_QUERY.get(name) || ""}`;
}

export function sourcePathForTarget(target) {
  const pathname = new URL(target.url).pathname;
  const name = decodeURIComponent(path.basename(pathname));
  const candidate = path.join(PUBLIC_DIR, name);
  return existsSync(candidate) ? candidate : null;
}

const NA_PAGES_FILE = path.join(HERE, "na-pages.json");

export function loadNaPages() {
  const file = readJson(NA_PAGES_FILE, null);
  const entries = Array.isArray(file?.pages) ? file.pages : [];
  const names = [];
  const reasons = new Map();
  for (const entry of entries) {
    const name = typeof entry === "string" ? entry : entry?.name;
    if (!name) continue;
    names.push(name);
    reasons.set(name, (typeof entry === "object" && entry?.reason) || "");
  }
  return { names, reasons };
}

export function parseCli(argv, { allowCheck = false, allowBaseline = false } = {}) {
  const options = {
    all: false,
    page: null,
    check: false,
    updateBaseline: false,
    naArgs: [],
    base: process.env.EDU_GATE_BASE || DEFAULT_BASE,
    out: process.env.EDU_GATE_OUT || DEFAULT_OUT,
    chrome: process.env.EDU_GATE_CHROME || null,
    settleMs: Number(process.env.EDU_GATE_SETTLE_MS || 900),
    help: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--all") options.all = true;
    else if (arg === "--page") options.page = argv[++index];
    else if (arg === "--base") options.base = argv[++index];
    else if (arg === "--out") options.out = argv[++index];
    else if (arg === "--chrome") options.chrome = argv[++index];
    else if (arg === "--settle-ms") options.settleMs = Number(argv[++index]);
    else if (arg === "--check" && allowCheck) options.check = true;
    else if (arg === "--update-baseline" && allowBaseline) options.updateBaseline = true;
    else if (arg === "--na") options.naArgs.push(...String(argv[++index]).split(",").filter(Boolean));
    else if (arg === "--help" || arg === "-h") options.help = true;
    else throw new Error(`Unknown argument: ${arg}`);
  }

  const na = loadNaPages();
  options.na = new Set([...na.names, ...options.naArgs]);
  options.naReasons = na.reasons;

  if (!options.help && options.all === Boolean(options.page)) {
    throw new Error("Choose exactly one target mode: --all or --page <url>.");
  }
  if (!Number.isFinite(options.settleMs) || options.settleMs < 0) {
    throw new Error("--settle-ms must be a non-negative number.");
  }

  options.base = options.base.replace(/\/$/, "");
  options.out = path.resolve(PROJECT_ROOT, options.out);
  return options;
}

export function resolveTargets(options) {
  if (options.all) {
    return listHtmlPages().map((name) => ({
      name,
      url: new URL(routeForPage(name), `${options.base}/`).href,
      sourcePath: path.join(PUBLIC_DIR, name),
    }));
  }

  const raw = options.page;
  const url = /^https?:\/\//i.test(raw)
    ? new URL(raw)
    : new URL(raw.startsWith("/") ? raw : `/${raw}`, `${options.base}/`);
  const name = decodeURIComponent(path.basename(url.pathname)) || "index.html";
  const sourcePath = path.join(PUBLIC_DIR, name);
  return [{ name, url: url.href, sourcePath: existsSync(sourcePath) ? sourcePath : null }];
}

export function readJson(file, fallback = null) {
  if (!existsSync(file)) return fallback;
  return JSON.parse(readFileSync(file, "utf8"));
}

export function writeJson(file, value) {
  ensureDir(path.dirname(file));
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export function makeCheck(name, pass, detail, severity = "error") {
  return { name, pass: Boolean(pass), detail, severity };
}

// Auth pages render in a degraded state once EDU_GATE_TOKEN expires mid-run (observed:
// a long --all pass outlived the JWT TTL and coupons.html tab-reachable fell to 14/68
// with 54 phantom-unreachable elements). Fail fast instead of poisioning the report.
export function assertFreshGateToken() {
  const token = process.env.EDU_GATE_TOKEN || "";
  if (!token || !token.startsWith("eyJ")) return;
  try {
    const payload = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString("utf8"));
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      throw new Error(
        `GATE-TOKEN-EXPIRED: EDU_GATE_TOKEN expired at ${new Date(payload.exp * 1000).toISOString()}. ` +
        "Re-login (adm02test/Test@123456 → /api/auth/login on :9988) and re-export a fresh token; " +
        "an expired token silently degrades auth-guard pages and fakes red results."
      );
    }
  } catch (error) {
    if (error instanceof Error && error.message.startsWith("GATE-TOKEN-EXPIRED")) throw error;
    // Not a decodable JWT (opaque token) — nothing to check locally.
  }
}

// Dev-mode premise: route-stable / aria-freeze checks are only valid against a Next dev
// server. Under `next start` the auth-guard redirect chain differs (observed: /chat.html →
// /login-register.html → /, where / is the React root with an unrelated DOM), which once
// turned a G8 --all run fully red. Probed via a dev-only static asset (Turbopack dev answers
// 200; webpack-hmr does NOT — it 404s under Next 16 Turbopack).
export async function assertDevBase(options, targets = []) {
  assertFreshGateToken();
  const origins = [...new Set([options.base, ...targets.map((target) => new URL(target.url).origin)])];
  const notDev = [];
  for (const origin of origins) {
    const probe = `${origin}/_next/static/development/_devMiddlewareManifest.json`;
    let dev = false;
    try {
      dev = (await fetch(probe, { signal: AbortSignal.timeout(5000) })).ok;
    } catch {}
    if (!dev) notDev.push(origin);
  }
  if (notDev.length) {
    throw new Error(
      [
        `GATE-BASE-MODE: not a Next dev server: ${notDev.join(", ")} (dev-only asset /_next/static/development/_devMiddlewareManifest.json did not return 200).`,
        "route-stable / aria-freeze checks hold only in dev mode: under next start the auth-guard redirect chain differs.",
        "Start dev first (in edu-frontend/: node node_modules/next/dist/bin/next dev -p 3322) or point EDU_GATE_BASE at a dev instance.",
      ].join("\n")
    );
  }
}

export function finalizeReport(gate, pages, extra = {}) {
  const checks = pages.flatMap((page) => page.checks || []);
  const failed = checks.filter((item) => !item.pass && item.severity === "error").length;
  const warnings = checks.filter((item) => !item.pass && item.severity === "warning").length;
  const skipped = checks.filter((item) => item.severity === "skip").length;
  return {
    gate,
    generated_at: new Date().toISOString(),
    status: failed === 0 ? "PASS" : "FAIL",
    summary: { pages: pages.length, checks: checks.length, failed, warnings, skipped },
    ...extra,
    pages,
  };
}

export function writeGateReports(gate, report, outDir) {
  ensureDir(outDir);
  const stem = gate.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const jsonPath = path.join(outDir, `${stem}.json`);
  const textPath = path.join(outDir, `${stem}.txt`);
  writeJson(jsonPath, report);

  const lines = [
    `${gate} ${report.status}`,
    `generated_at=${report.generated_at}`,
    `pages=${report.summary.pages} checks=${report.summary.checks} failed=${report.summary.failed} warnings=${report.summary.warnings}${Number.isFinite(report.summary.skipped) ? ` skipped=${report.summary.skipped}` : ""}`,
  ];
  for (const page of report.pages) {
    const pageFailed = (page.checks || []).filter((item) => !item.pass && item.severity === "error").length;
    lines.push("", `[${pageFailed ? "FAIL" : "PASS"}] ${page.name} ${page.url || ""}`.trim());
    for (const item of page.checks || []) {
      const label = item.pass ? item.severity === "skip" ? "SKIP" : "PASS" : item.severity === "warning" ? "WARN" : "FAIL";
      lines.push(`  [${label}] ${item.name}: ${item.detail}`);
    }
  }
  writeFileSync(textPath, `${lines.join("\n")}\n`, "utf8");
  return { jsonPath, textPath };
}

export function printReport(report, files) {
  console.log(`${report.gate}: ${report.status}`);
  console.log(`pages=${report.summary.pages} checks=${report.summary.checks} failed=${report.summary.failed} warnings=${report.summary.warnings}`);
  console.log(`json=${path.relative(PROJECT_ROOT, files.jsonPath)}`);
  console.log(`text=${path.relative(PROJECT_ROOT, files.textPath)}`);
}

export function safeStem(value) {
  return value.replace(/\.html$/i, "").replace(/[^a-z0-9_-]+/gi, "-");
}

export function findChrome(explicitPath = null) {
  const candidates = [
    explicitPath,
    "D:\\tool\\chrom\\Application\\chrome.exe",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) throw new Error("Chrome/Edge not found. Pass --chrome <absolute-path>.");
  return found;
}

async function freePort() {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

class TinyWebSocket extends EventEmitter {
  constructor(socket) {
    super();
    this.socket = socket;
    this.buffer = Buffer.alloc(0);
    this.fragments = [];
    socket.on("data", (chunk) => this.#consume(chunk));
    socket.on("error", (error) => this.emit("error", error));
    socket.on("close", () => this.emit("close"));
  }

  static async connect(urlString) {
    const url = new URL(urlString);
    if (url.protocol !== "ws:") throw new Error(`Only ws:// CDP endpoints are supported: ${urlString}`);
    const key = randomBytes(16).toString("base64");
    const expected = createHash("sha1")
      .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
      .digest("base64");

    return new Promise((resolve, reject) => {
      const socket = createConnection({ host: url.hostname, port: Number(url.port || 80) });
      let handshake = Buffer.alloc(0);
      const fail = (error) => {
        socket.destroy();
        reject(error);
      };
      socket.once("error", fail);
      socket.once("connect", () => {
        socket.write([
          `GET ${url.pathname}${url.search} HTTP/1.1`,
          `Host: ${url.host}`,
          "Upgrade: websocket",
          "Connection: Upgrade",
          `Sec-WebSocket-Key: ${key}`,
          "Sec-WebSocket-Version: 13",
          "\r\n",
        ].join("\r\n"));
      });
      const onData = (chunk) => {
        handshake = Buffer.concat([handshake, chunk]);
        const end = handshake.indexOf("\r\n\r\n");
        if (end < 0) return;
        socket.off("data", onData);
        socket.off("error", fail);
        const header = handshake.subarray(0, end).toString("utf8");
        const rest = handshake.subarray(end + 4);
        if (!/^HTTP\/1\.1 101\b/m.test(header)) return fail(new Error(`WebSocket upgrade failed: ${header.split("\r\n")[0]}`));
        const accept = header.match(/^Sec-WebSocket-Accept:\s*(.+)$/im)?.[1]?.trim();
        if (accept !== expected) return fail(new Error("WebSocket accept hash mismatch."));
        const ws = new TinyWebSocket(socket);
        if (rest.length) ws.#consume(rest);
        resolve(ws);
      };
      socket.on("data", onData);
    });
  }

  send(text) {
    const payload = Buffer.from(text, "utf8");
    const mask = randomBytes(4);
    let header;
    if (payload.length < 126) {
      header = Buffer.from([0x81, 0x80 | payload.length]);
    } else if (payload.length <= 0xffff) {
      header = Buffer.alloc(4);
      header[0] = 0x81;
      header[1] = 0x80 | 126;
      header.writeUInt16BE(payload.length, 2);
    } else {
      header = Buffer.alloc(10);
      header[0] = 0x81;
      header[1] = 0x80 | 127;
      header.writeBigUInt64BE(BigInt(payload.length), 2);
    }
    const masked = Buffer.allocUnsafe(payload.length);
    for (let index = 0; index < payload.length; index += 1) masked[index] = payload[index] ^ mask[index % 4];
    this.socket.write(Buffer.concat([header, mask, masked]));
  }

  close() {
    if (!this.socket.destroyed) this.socket.end(Buffer.from([0x88, 0x00]));
  }

  #consume(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (this.buffer.length >= 2) {
      const first = this.buffer[0];
      const second = this.buffer[1];
      const masked = Boolean(second & 0x80);
      let length = second & 0x7f;
      let offset = 2;
      if (length === 126) {
        if (this.buffer.length < 4) return;
        length = this.buffer.readUInt16BE(2);
        offset = 4;
      } else if (length === 127) {
        if (this.buffer.length < 10) return;
        const wide = this.buffer.readBigUInt64BE(2);
        if (wide > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error("CDP WebSocket frame is too large.");
        length = Number(wide);
        offset = 10;
      }
      const maskLength = masked ? 4 : 0;
      if (this.buffer.length < offset + maskLength + length) return;
      const mask = masked ? this.buffer.subarray(offset, offset + 4) : null;
      offset += maskLength;
      const payload = Buffer.from(this.buffer.subarray(offset, offset + length));
      this.buffer = this.buffer.subarray(offset + length);
      if (mask) for (let index = 0; index < payload.length; index += 1) payload[index] ^= mask[index % 4];

      const fin = Boolean(first & 0x80);
      const opcode = first & 0x0f;
      if (opcode === 0x8) {
        this.socket.end();
        return;
      }
      if (opcode === 0x9) {
        this.#sendControl(0x0a, payload);
        continue;
      }
      if (opcode === 0x1 || opcode === 0x0) {
        this.fragments.push(payload);
        if (fin) {
          const message = Buffer.concat(this.fragments).toString("utf8");
          this.fragments = [];
          this.emit("message", message);
        }
      }
    }
  }

  #sendControl(opcode, payload) {
    const mask = randomBytes(4);
    const header = Buffer.from([0x80 | opcode, 0x80 | payload.length]);
    const masked = Buffer.allocUnsafe(payload.length);
    for (let index = 0; index < payload.length; index += 1) masked[index] = payload[index] ^ mask[index % 4];
    this.socket.write(Buffer.concat([header, mask, masked]));
  }
}

class CdpSession extends EventEmitter {
  constructor(ws) {
    super();
    this.ws = ws;
    this.nextId = 0;
    this.pending = new Map();
    this.diagnostics = [];
    ws.on("message", (text) => this.#onMessage(text));
    ws.on("error", (error) => this.#rejectAll(error));
    ws.on("close", () => this.#rejectAll(new Error("CDP WebSocket closed.")));
  }

  send(method, params = {}, timeoutMs = 15000) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP timeout: ${method}`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer, method });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text || "Runtime.evaluate failed");
    }
    return result.result?.value;
  }

  waitFor(method, timeoutMs = 12000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.off(method, onEvent);
        reject(new Error(`CDP event timeout: ${method}`));
      }, timeoutMs);
      const onEvent = (params) => {
        clearTimeout(timer);
        resolve(params);
      };
      this.once(method, onEvent);
    });
  }

  clearDiagnostics() {
    this.diagnostics.length = 0;
  }

  close() {
    this.ws.close();
  }

  #onMessage(text) {
    const message = JSON.parse(text);
    if (message.id && this.pending.has(message.id)) {
      const pending = this.pending.get(message.id);
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) pending.reject(new Error(`${pending.method}: ${message.error.message}`));
      else pending.resolve(message.result || {});
      return;
    }
    if (!message.method) return;
    if (message.method === "Runtime.exceptionThrown") {
      const detail = message.params.exceptionDetails;
      this.diagnostics.push(`EXC: ${(detail.exception?.description || detail.text || "").slice(0, 500)}`);
    }
    if (message.method === "Log.entryAdded" && message.params.entry.level === "error") {
      this.diagnostics.push(`LOG: ${(message.params.entry.text || "").slice(0, 500)}`);
    }
    if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
      const detail = message.params.args.map((arg) => arg.value ?? arg.description ?? "").join(" ");
      this.diagnostics.push(`CONSOLE: ${detail.slice(0, 500)}`);
    }
    this.emit(message.method, message.params);
  }

  #rejectAll(error) {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(error);
    }
    this.pending.clear();
  }
}

export async function createBrowser(options = {}) {
  const chrome = findChrome(options.chrome);
  const port = await freePort();
  const profile = mkdtempSync(path.join(tmpdir(), "edu-theme-gate-"));
  const proc = spawn(chrome, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    "--headless=new",
    "--window-size=1440,900",
    "--force-device-scale-factor=1",
    "--hide-scrollbars=false",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-sync",
    "--metrics-recording-only",
    "--no-default-browser-check",
    "--no-first-run",
    "about:blank",
  ], { stdio: "ignore", windowsHide: true });

  let version = null;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (proc.exitCode !== null) throw new Error(`Chrome exited early with code ${proc.exitCode}.`);
    try {
      version = await fetch(`http://127.0.0.1:${port}/json/version`).then((response) => response.json());
      break;
    } catch {
      await sleep(250);
    }
  }
  if (!version) throw new Error("Chrome remote debugging port did not become ready.");

  const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then((response) => response.json());
  const page = targets.find((target) => target.type === "page");
  if (!page) throw new Error("Chrome did not expose a page target.");
  const ws = await TinyWebSocket.connect(page.webSocketDebuggerUrl);
  const cdp = new CdpSession(ws);

  await Promise.all([
    cdp.send("Page.enable"),
    cdp.send("Runtime.enable"),
    cdp.send("Log.enable"),
    cdp.send("Network.enable"),
  ]);

  const token = process.env.EDU_GATE_TOKEN || "";
  const refresh = process.env.EDU_GATE_REFRESH_TOKEN || "";
  if (token) {
    await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `try { localStorage.setItem("edu:auth:token", ${JSON.stringify(token)}); localStorage.setItem("edu:auth:refresh", ${JSON.stringify(refresh)}); } catch {}`,
    });
  }

  return {
    cdp,
    chromeVersion: version.Browser || "unknown",
    async setViewport(width, height = 900) {
      await cdp.send("Emulation.setDeviceMetricsOverride", {
        width,
        height,
        deviceScaleFactor: 1,
        mobile: width <= 768,
        screenWidth: width,
        screenHeight: height,
      });
    },
    async setReducedMotion(enabled = true) {
      await cdp.send("Emulation.setEmulatedMedia", {
        features: enabled ? [{ name: "prefers-reduced-motion", value: "reduce" }] : [],
      });
    },
    async navigate(url, settleMs = options.settleMs ?? 900) {
      cdp.clearDiagnostics();
      const loaded = cdp.waitFor("Page.loadEventFired", 15000).catch(() => null);
      const response = await cdp.send("Page.navigate", { url });
      await loaded;
      await sleep(settleMs);
      return response;
    },
    async screenshot(file, { quality = 52 } = {}) {
      ensureDir(path.dirname(file));
      const result = await cdp.send("Page.captureScreenshot", {
        format: "jpeg",
        quality,
        fromSurface: true,
        captureBeyondViewport: false,
      }, 30000);
      writeFileSync(file, Buffer.from(result.data, "base64"));
      return file;
    },
    async close() {
      cdp.close();
      if (proc.exitCode === null) proc.kill();
      await sleep(150);
      const resolvedProfile = path.resolve(profile);
      const safePrefix = `${path.resolve(tmpdir())}${path.sep}edu-theme-gate-`;
      if (resolvedProfile.startsWith(safePrefix)) {
        try { rmSync(resolvedProfile, { recursive: true, force: true }); } catch {}
      }
    },
  };
}

export function usage(script, extras = "") {
  return [
    `Usage: node scripts/gates/${script} --page <url> [--out <dir>]`,
    `       node scripts/gates/${script} --all [--out <dir>]`,
    `       [--na <page-name>...] marks pages whose excluded check is structurally N/A (recorded as SKIP; file default: scripts/gates/na-pages.json)`,
    extras,
    "Environment: EDU_GATE_BASE, EDU_GATE_CHROME, EDU_GATE_TOKEN, EDU_GATE_REFRESH_TOKEN, EDU_GATE_SETTLE_MS",
  ].filter(Boolean).join("\n");
}
