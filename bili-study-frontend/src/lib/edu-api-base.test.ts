import { readFileSync } from "node:fs";
import path from "node:path";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

const source = readFileSync(path.resolve(process.cwd(), "public/edu-api.js"), "utf8");

function resolvedBase(url: string, override?: string): string {
  const dom = new JSDOM("<!doctype html>", { url, runScripts: "outside-only" });
  try {
    if (override) (dom.window as unknown as { EDU_API_BASE: string }).EDU_API_BASE = override;
    dom.window.eval(source);
    return (dom.window as unknown as { EAPI: { BASE: string } }).EAPI.BASE;
  } finally {
    dom.window.close();
  }
}

describe("static edu-api API base selection", () => {
  it("Docker build routes static pages through the same origin even on a custom loopback port", () => {
    const deployed = source.replace('const DEPLOY_API_BASE = "__EDU_API_BASE__";', 'const DEPLOY_API_BASE = "";');
    const dom = new JSDOM("<!doctype html>", { url: "http://127.0.0.1:13322/", runScripts: "outside-only" });
    try {
      dom.window.eval(deployed);
      expect((dom.window as unknown as { EAPI: { BASE: string } }).EAPI.BASE).toBe("");
    } finally {
      dom.window.close();
    }
  });
  it("uses explicit deployment override first", () => {
    expect(resolvedBase("https://edu.example.com/", "https://api.example.net/v1/"))
      .toBe("https://api.example.net/v1");
  });

  it("uses same-origin for hosted pages without an override", () => {
    expect(resolvedBase("https://edu.example.com/course/"))
      .toBe("https://edu.example.com");
  });

  it.each(["http://localhost:3322", "http://127.0.0.1:3322", "http://dev.localhost:3000"])(
    "routes loopback development origin %s to its local API port",
    (url) => {
      const host = new URL(url).hostname;
      expect(resolvedBase(url)).toBe(`http://${host}:9988`);
    },
  );
});
