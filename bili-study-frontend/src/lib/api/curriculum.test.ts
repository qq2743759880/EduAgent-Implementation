import { describe, expect, it } from "vitest";

import { normalizeMindMap } from "./curriculum";

describe("normalizeMindMap（思维导图契约归一化）", () => {
  const raw = {
    title: "英语音标入门",
    subject_code: "english",
    categories: [
      { name: "系列课程" },
      { name: "模块" },
      { name: "知识点" },
      { name: "题目标签" },
    ],
    nodes: [
      {
        id: "SER-EN-PHON",
        label: "CourseSeries",
        name: "英语音标入门",
        subject_code: "english",
        category: 0,
        value: 52,
        status: "NOT_STARTED",
        mastery_ratio: 0.0,
        x: null,
        y: null,
      },
      {
        id: "KP-EN-VOWEL-SINGLE",
        label: "KnowledgePoint",
        name: "单元音",
        category: 2,
        value: 22,
        status: "MASTERED",
        mastery_ratio: 0.85,
      },
      {
        id: "KP-EN-VOWEL-DOUBLE",
        label: "KnowledgePoint",
        name: "双元音",
        category: 2,
        value: 22,
        status: "IN_PROGRESS",
        mastery_ratio: 0.5,
      },
    ],
    links: [
      {
        source: "SER-EN-PHON",
        target: "KP-EN-VOWEL-SINGLE",
        rel_type: "CONTAINS",
        line_style: { color: "#5B8FF9", type: "solid", width: 1.2 },
      },
      {
        source: "KP-EN-VOWEL-SINGLE",
        target: "KP-EN-VOWEL-DOUBLE",
        rel_type: "PREREQUISITE",
        line_style: { color: "#F6BD16", type: "solid", width: 2.0 },
      },
    ],
    stats: { node_count: 3, edge_count: 2 },
    legend: ["CONTAINS (包含)", "PREREQUISITE (先修)"],
  };

  it("links 的 rel_type → relation、line_style → lineStyle", () => {
    const r = normalizeMindMap(raw);
    expect(r.links).toHaveLength(2);
    expect(r.links[0].relation).toBe("CONTAINS");
    expect(r.links[1].relation).toBe("PREREQUISITE");
    expect(r.links[0].lineStyle).toEqual({ color: "#5B8FF9", type: "solid", width: 1.2 });
    expect(r.links[1].lineStyle?.color).toBe("#F6BD16");
  });

  it("nodes.status 大写枚举 → 小写", () => {
    const r = normalizeMindMap(raw);
    expect(r.nodes[0].status).toBe("not_started");
    expect(r.nodes[1].status).toBe("mastered");
    expect(r.nodes[2].status).toBe("learning");
  });

  it("nodes.mastery_ratio → masteryRatio，保留数值", () => {
    const r = normalizeMindMap(raw);
    expect(r.nodes[1].masteryRatio).toBe(0.85);
  });

  it("未知 status 不报错（undefined）", () => {
    const r = normalizeMindMap({
      ...raw,
      nodes: [{ id: "x", name: "y", status: "SOME_UNKNOWN" }],
    });
    expect(r.nodes[0].status).toBeUndefined();
  });

  it("空 nodes/links/categories 防御", () => {
    const r = normalizeMindMap({});
    expect(r.nodes).toEqual([]);
    expect(r.links).toEqual([]);
    expect(r.categories).toEqual([]);
  });
});
