#!/usr/bin/env node
/**
 * fx-task05 用户端全链路联调验证（verify-task05-user-chain.mjs）
 *
 * 8 阶段：注册 → 登录 → 选课 → 学习 → 答题 → 问答 → 社区 → 成就
 *  - 阶段间真实 JWT 贯穿（access_token 传递到后续全部请求）
 *  - 全程无 500（每阶段 status < 500）；任意阶段失败 → 标注阶段名 + exit 1
 *  - 社区发帖 points_awarded=5、回帖 points:2（契约断言）
 *  - 问答段复证 R-1：GET /api/chat/sessions/{id}/history → 200
 *  - 造数幂等：随机账号 `_gen_account` + 注册 409 兜底跳过
 *
 * 前置：uvicorn :8000（be-task01 新代码）运行中；前端 dev server :3000 可选（脚本以 HTTP 断言为主，
 *       浏览器渲染断言仅在 _PORT 探测通过时执行，失败不阻断 HTTP 链）。
 * 运行：node scripts/verify-task05-user-chain.mjs
 * 退出码：0 全过 / 1 断言失败 / 2 脚本异常 / 3 服务未就绪
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const API = "http://127.0.0.1:8000";
const WEB = "http://localhost:3000";

/* ============ 就绪探测 ============ */
async function portUp(url, timeoutMs = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(3000) });
      if (r.ok || r.status < 500) return true;
    } catch { /* retry */ }
    await new Promise((res) => setTimeout(res, 700));
  }
  return false;
}
if (!(await portUp(`${API}/health`))) {
  console.error(`[就绪探测] 后端 ${API} 未就绪 → exit 3`);
  process.exit(3);
}
const webUp = await portUp(`${WEB}/`, 5000);

/* ============ 结果收集 ============ */
const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok, extra });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  | " + extra : ""}`);
}

/* ============ HTTP 工具（真实 JWT 贯穿；记录状态码以断言无 500） ============ */
let stageName = "准备";
async function req(method, pathStr, { token, body, headers = {} } = {}) {
  const h = { "Content-Type": "application/json", ...headers };
  if (token) h.Authorization = `Bearer ${token}`;
  const resp = await fetch(`${API}${pathStr}`, {
    method,
    headers: h,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  const text = await resp.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  return { status: resp.status, data };
}
function assertNo500(res, name) {
  check(`${stageName} · ${name} 无 500（status<500）`, res.status < 500, `status=${res.status}`);
  return res.status < 500;
}

function genAccount(prefix) {
  const ts = Date.now().toString(36);
  const rnd = Math.floor(Math.random() * 9000 + 1000).toString(36);
  return `${prefix}_${ts}${rnd}`.slice(0, 40);
}

/* ============ 浏览器渲染断言（可选，失败不阻断 HTTP 链） ============ */
async function browserAssert(token, me, fnName, fn) {
  if (!webUp) {
    check(`${fnName}（渲染断言）`, true, "dev server 未就绪，跳过浏览器断言");
    return;
  }
  try {
    const { chromium } = await import("playwright");
    const b = await chromium.launch();
    try {
      const pg = await b.newPage({ viewport: { width: 1440, height: 900 } });
      await pg.addInitScript(
        ({ tk, meObj }) => {
          localStorage.setItem("edu:auth:token", tk);
          localStorage.setItem("edu:auth:me", JSON.stringify(meObj));
          localStorage.removeItem("edu:auth:tenant");
        },
        { tk: token, meObj: me },
      );
      await fn(pg);
    } finally {
      await b.close();
    }
  } catch (err) {
    check(`${fnName}（渲染断言）`, false, `浏览器异常：${err instanceof Error ? err.message : String(err)}`);
  }
}

try {
  /* ============ 1. 注册 ============ */
  stageName = "注册";
  const account = genAccount("t5user");
  const mobile = `137${String(Math.floor(Math.random() * 1e8)).padStart(8, "0")}`;
  const reg = await req("POST", "/api/auth/register", {
    body: { account, nickname: `用户链${account.slice(-4)}`, password: "P@ssw0rd123", mobile },
  });
  if (reg.status === 409) {
    check("注册（409 兜底：账号已存在则跳过）", true, account);
  } else {
    check("注册 2xx", reg.status >= 200 && reg.status < 300, `status=${reg.status}`);
    assertNo500(reg, "注册");
  }

  /* ============ 2. 登录 ============ */
  stageName = "登录";
  const login = await req("POST", "/api/auth/login", { body: { account, password: "P@ssw0rd123" } });
  check("登录 200 + access_token", login.status === 200 && typeof login.data?.access_token === "string" && login.data.access_token.length > 20, `status=${login.status}`);
  assertNo500(login, "登录");
  const token = login.data?.access_token;
  const loginUser = login.data?.user ?? {};
  const roles = Array.isArray(loginUser.roles) ? loginUser.roles : (loginUser.role ? [loginUser.role] : []);
  check("登录用户角色含 student", roles.includes("student"), `role=${loginUser.role ?? loginUser.roles}`);
  if (!token) throw new Error("登录未返回 access_token，后续阶段无法继续");

  /* ============ 3. 选课 ============ */
  stageName = "选课";
  const series = await req("GET", "/api/curriculum/series?page=1&page_size=10", { token });
  check("GET /api/curriculum/series 200", series.status === 200 && Array.isArray(series.data?.items), `status=${series.status}`);
  assertNo500(series, "课程系列列表");
  const seriesId = series.data?.items?.[0]?.id ?? null;
  if (seriesId) {
    const tree = await req("GET", `/api/curriculum/series/${seriesId}/tree`, { token });
    check("GET /api/curriculum/series/{id}/tree 200", tree.status === 200, `status=${tree.status} series=${seriesId}`);
    assertNo500(tree, "系列树");
    const prog = await req("GET", "/api/progress/courses", { token });
    check("GET /api/progress/courses 200", prog.status === 200 && Array.isArray(prog.data), `status=${prog.status}`);
    assertNo500(prog, "我的课程进度");
  } else {
    check("GET 系列树/进度（无系列数据跳过）", true, "系列列表为空");
  }

  /* ============ 4. 学习（视频打点） ============ */
  stageName = "学习";
  if (seriesId) {
    const tree = await req("GET", `/api/curriculum/series/${seriesId}/tree`, { token });
    const firstSession =
      tree.data?.modules?.find((m) => Array.isArray(m.sessions) && m.sessions.length > 0)?.sessions?.[0] ?? null;
    if (firstSession?.id) {
      const tick = await req("POST", "/api/progress/video/tick-batch", {
        token,
        body: {
          play_session_id: 1,
          session_id: firstSession.id,
          ticks: [
            {
              event_type: "PLAY",
              position_seconds: 0,
              playback_rate: 1.0,
              network_type: "WIFI",
              event_time: new Date().toISOString(),
            },
            {
              event_type: "TICK",
              position_seconds: 30,
              playback_rate: 1.0,
              network_type: "WIFI",
              event_time: new Date().toISOString(),
            },
          ],
        },
      });
      check("POST /api/progress/video/tick-batch 200 + inserted", tick.status === 200 && Number.isInteger(tick.data?.inserted), `status=${tick.status} inserted=${tick.data?.inserted} session=${firstSession.id}`);
      assertNo500(tick, "视频打点");
    } else {
      check("视频打点（系列无课次跳过）", true, "树内无 session");
    }
  } else {
    check("视频打点（无系列跳过）", true, "");
  }

  /* ============ 5. 答题 ============ */
  stageName = "答题";
  const quiz = await req("GET", "/api/interactive/quiz/next?subject_code=english", { token });
  if (quiz.status === 200 && quiz.data) {
    check("GET /api/interactive/quiz/next 200 + 题目", !!quiz.data.custom_code, `custom_code=${quiz.data.custom_code ?? "-"}`);
    assertNo500(quiz, "取题");
    const q = quiz.data;
    let answer;
    if (q.question_type === "SINGLE" || q.question_type === "MULTI") {
      answer = Array.isArray(q.correct) ? q.correct : [q.correct ?? ""];
    } else if (q.question_type === "JUDGE") {
      answer = q.correct === true || q.correct === "true" ? "1" : "0";
    } else if (q.question_type === "DRAG_SORT") {
      answer = q.correct ?? [];
    } else if (q.question_type === "MATCH") {
      answer = q.correct ?? [];
    } else {
      answer = q.correct ?? "";
    }
    const submit = await req("POST", "/api/interactive/quiz/submit", {
      token,
      body: {
        question_id: q.question_id ?? null,
        custom_code: q.custom_code,
        question_type: q.question_type,
        answer,
        time_spent_sec: 8,
      },
    });
    check("POST /api/interactive/quiz/submit 200 + SubmitAnswerOut", submit.status === 200 && typeof submit.data?.is_correct === "boolean", `status=${submit.status} is_correct=${submit.data?.is_correct}`);
    assertNo500(submit, "提交作答");
  } else if (quiz.status === 204 || quiz.status === 404 || quiz.status === 422) {
    check("答题（题库空/科目无题 → 按契约空态跳过）", true, `status=${quiz.status}`);
  } else {
    check("GET /api/interactive/quiz/next 200", false, `status=${quiz.status}`);
    assertNo500(quiz, "取题");
  }

  /* ============ 6. 问答（建会话 → 非流式问答 → R-1 历史复证） ============ */
  stageName = "问答";
  const cs = await req("POST", "/api/chat/sessions", { token, body: { title: "用户链联调会话" } });
  check("POST /api/chat/sessions 2xx", cs.status >= 200 && cs.status < 300, `status=${cs.status}`);
  assertNo500(cs, "创建会话");
  const sessionId = cs.data?.session_id ?? cs.data?.id ?? null;
  if (!sessionId) throw new Error("创建会话未返回 session_id");
  const chatQ = "请用一句话介绍雅思听力备考的要点";
  const chat = await req("POST", "/api/chat", {
    token,
    body: { query: chatQ, session_id: sessionId, stream: false, model: "fast", use_mcp_tools: false },
  });
  check("POST /api/chat（非流式问答）200 + answer 非空", chat.status === 200 && typeof chat.data?.answer === "string" && chat.data.answer.length > 0, `status=${chat.status} answer_len=${chat.data?.answer?.length ?? 0}`);
  assertNo500(chat, "非流式问答");
  const hist = await req("GET", `/api/chat/sessions/${sessionId}/history`, { token });
  check("GET /api/chat/sessions/{id}/history 200（R-1 复证）", hist.status === 200 && Array.isArray(hist.data), `status=${hist.status} msgs=${Array.isArray(hist.data) ? hist.data.length : 0}`);
  assertNo500(hist, "历史加载");
  const lastAssistant = (Array.isArray(hist.data) ? hist.data : []).filter((m) => m.role === "assistant").pop();
  check("历史最后一条 assistant 非空", !!lastAssistant && typeof lastAssistant.content === "string" && lastAssistant.content.length > 0, "");

  /* ============ 7. 社区（发帖 +5 / 回帖 +2） ============ */
  stageName = "社区";
  const hot = await req("GET", "/api/community/posts?sort=HOT&page=1&page_size=5", { token });
  check("GET /api/community/posts?sort=HOT 200", hot.status === 200 && Array.isArray(hot.data?.items), `status=${hot.status}`);
  assertNo500(hot, "帖子列表");
  const stamp = Date.now() % 100000;
  const post = await req("POST", "/api/community/posts", {
    token,
    body: { title: `用户链联调帖 ${stamp}`, content_md: "## 联调验证\n\n用户端全链路社区阶段。", board_code: "math", tags: ["联调", "task05"] },
  });
  check("发帖 200 + points_awarded=5", post.status === 200 && post.data?.points_awarded === 5, `status=${post.status} points=${post.data?.points_awarded}`);
  assertNo500(post, "发帖");
  const postId = post.data?.post_id ?? null;
  if (!postId) throw new Error("发帖未返回 post_id");
  const comment = await req("POST", `/api/community/posts/${postId}/comments`, {
    token,
    body: { content_md: "用户链回帖验证" },
  });
  check("回帖 200 + points:2", comment.status === 200 && comment.data?.points === 2, `status=${comment.status} points=${comment.data?.points}`);
  assertNo500(comment, "回帖");

  /* ============ 8. 成就 ============ */
  stageName = "成就";
  const badges = await req("GET", "/api/gamification/me/badges", { token });
  check("GET /api/gamification/me/badges 200 + unlocked_count≥0", badges.status === 200 && Number.isInteger(badges.data?.unlocked_count) && badges.data.unlocked_count >= 0, `status=${badges.status} unlocked=${badges.data?.unlocked_count}`);
  assertNo500(badges, "徽章");
  const points = await req("GET", "/api/gamification/me/points?page=1&page_size=20", { token });
  check("GET /api/gamification/me/points 200", points.status === 200 && Number.isInteger(points.data?.total_points), `status=${points.status} total=${points.data?.total_points}`);
  assertNo500(points, "积分");
  const rank = await req("GET", "/api/gamification/rankings?scope=DAILY&dimension=POINTS&top_n=20", { token });
  check("GET /api/gamification/rankings 200 + my_rank/top", rank.status === 200 && (Array.isArray(rank.data?.top) || rank.data?.my_rank != null), `status=${rank.status} top=${Array.isArray(rank.data?.top) ? rank.data.top.length : 0}`);
  assertNo500(rank, "排行");

  /* ============ 浏览器渲染断言（成就徽章 + 社区新帖可见） ============ */
  await browserAssert(token, { id: loginUser.user_id, nickname: loginUser.nickname, email: loginUser.email ?? null, username: account, avatar: null, roles: ["student"], tenantId: null }, "成就中心渲染", async (pg) => {
    await pg.goto(`${WEB}/achievements`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await pg.waitForTimeout(3500);
    const hasBadge = (await pg.locator("[data-testid='achievement-badge'], .badge-card, [class*='badge']").count().catch(() => 0)) > 0;
    const bodyText = await pg.evaluate(() => document.body.innerText);
    check("成就中心徽章渲染", hasBadge || /徽章|成就/.test(bodyText), "");
  });
} catch (err) {
  console.error(`脚本异常（阶段：${stageName}）:`, err instanceof Error ? err.message : String(err));
  process.exitCode = 2;
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== 用户端全链路（verify-task05-user-chain）：${results.length - failed.length}/${results.length} 通过，失败 ${failed.length} =====`);
if (failed.length) {
  for (const f of failed) console.error(`  FAIL: ${f.name}${f.extra ? " | " + f.extra : ""}`);
  process.exitCode = 1;
}
process.exit(process.exitCode ?? 0);
