/**
 * task01 E2E 契约验证脚本（临时）：验证前端 TS 类型字段与后端实际响应一致
 * 流程：登录 → 发帖(+5) → 详情 → 点赞 → 回帖(+2) → 积分确认 → 排行确认
 * 运行：node scripts/verify-task01-contract.mjs
 */
const BASE = "http://127.0.0.1:8000";

async function req(method, path, { token, body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const resp = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(`${method} ${path} -> ${resp.status}: ${JSON.stringify(data)}`);
  return data;
}

const results = [];
function check(name, cond, extra = "") {
  results.push({ name, ok: !!cond, extra });
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  | " + extra : ""}`);
}

const login = await req("POST", "/api/auth/login", {
  body: { account: "task01test", password: "Test@123456" },
});
const token = login.access_token;
check("登录拿到 token", typeof token === "string" && token.length > 20);

/* 1. 帖子列表字段对齐（post_id/summary 而非 id/content_preview） */
const list = await req("GET", "/api/community/posts?sort=HOT&page=1&page_size=5", { token });
check(
  "列表结构 {total,page,page_size,items,mine_total_posts}",
  typeof list.total === "number" && Array.isArray(list.items) && typeof list.mine_total_posts === "number",
);
const sample = list.items[0];
if (sample) {
  check(
    "PostSummary 字段（post_id/summary/mine_react_like）",
    typeof sample.post_id === "number" && typeof sample.summary === "string" &&
      typeof sample.mine_react_like === "boolean" && typeof sample.board_code === "string" &&
      Array.isArray(sample.tags),
  );
}

/* 2. 发帖（契约字段 content_md）→ 应返回 points_awarded=5 */
const stamp = Date.now() % 100000;
const created = await req("POST", "/api/community/posts", {
  token,
  body: {
    title: `契约验证帖 ${stamp}`,
    content_md: "## 测试正文\n\n这是 **task01** 契约验证内容。",
    board_code: "math",
    tags: ["验证", "task01"],
  },
});
check("发帖返回 {post_id, points_awarded, badge_unlocked}", typeof created.post_id === "number");
check("发帖即 +5 分", created.points_awarded === 5, `points_awarded=${created.points_awarded}`);

/* 3. 详情字段（PostDetail 含 content_md） */
const detail = await req("GET", `/api/community/posts/${created.post_id}`, { token });
check(
  "详情含 content_md + PostListItem 字段",
  typeof detail.content_md === "string" && typeof detail.like_count === "number" &&
    typeof detail.mine_react_like === "boolean" && typeof detail.is_pinned === "boolean",
);

/* 4. 点赞软切换（ReactToggleResp：active/total_count） */
const like1 = await req("POST", `/api/community/posts/${created.post_id}/like`, { token });
check("点赞响应 {active:true,total_count:1}", like1.active === true && like1.total_count === 1);
const like2 = await req("POST", `/api/community/posts/${created.post_id}/like`, { token });
check("再点取消 {active:false,total_count:0}", like2.active === false && like2.total_count === 0);
const fav = await req("POST", `/api/community/posts/${created.post_id}/favorite`, { token });
check("收藏 {active:true,total_count:1}", fav.active === true && fav.total_count === 1);

/* 5. 回帖 → {comment_id, points:2} */
const comment = await req("POST", `/api/community/posts/${created.post_id}/comments`, {
  token,
  body: { content_md: "沙发，验证回帖！" },
});
check("回帖返回 {comment_id, points:2}", typeof comment.comment_id === "number" && comment.points === 2);

/* 6. 评论列表字段 */
const comments = await req("GET", `/api/community/posts/${created.post_id}/comments?page=1&page_size=20`, { token });
check(
  "CommentItem 字段（comment_id/mine_liked）",
  Array.isArray(comments.items) && typeof comments.items[0]?.comment_id === "number" &&
    typeof comments.items[0]?.mine_liked === "boolean",
);

/* 7. 积分确认：发帖 +5 + 回帖 +2 = 7 */
const points = await req("GET", "/api/gamification/me/points?page=1&page_size=20", { token });
check(
  "PointsResp 字段（total_points/recent_logs/level_progress_pct）",
  typeof points.total_points === "number" && Array.isArray(points.recent_logs) &&
    typeof points.level_progress_pct === "number",
  `total_points=${points.total_points}`,
);
check("积分 = 7（发帖5+回帖2）", points.total_points === 7, `实际 ${points.total_points}`);
check("最近流水第一条是发帖", points.recent_logs[0]?.point_type === "POST_CREATE");

/* 8. 徽章字段 */
const badges = await req("GET", "/api/gamification/me/badges", { token });
check(
  "BadgeListResp 字段（unlocked_count/next_milestone/progress_pct）",
  typeof badges.total === "number" && typeof badges.unlocked_count === "number" &&
    typeof badges.next_milestone === "string" && Array.isArray(badges.items) &&
    typeof badges.items[0]?.progress_pct === "number",
  `unlocked=${badges.unlocked_count}/${badges.total}`,
);

/* 9. 排行榜字段（top 而非 items，user_name 而非 nickname，is_myself 而非 is_mine） */
const rank = await req("GET", "/api/gamification/rankings?scope=DAILY&dimension=POINTS&top_n=20", { token });
check(
  "RankingResp 字段（top/my_rank/is_myself）",
  Array.isArray(rank.top) && typeof rank.top[0]?.rank_no === "number" &&
    typeof rank.top[0]?.is_myself === "boolean" && (rank.my_rank === null || typeof rank.my_rank?.rank_no === "number"),
  `top=${rank.top.length}`,
);
check("排名维度枚举合法", ["DAILY", "WEEKLY", "MONTHLY", "ALL_TIME"].includes(rank.scope));

/* 10. 分版过滤：board_code=math 只返回 math */
const mathList = await req("GET", "/api/community/posts?board_code=math&page=1&page_size=20", { token });
check(
  "board_code 过滤生效",
  mathList.items.every((p) => p.board_code === "math"),
  `math 帖数=${mathList.total}`,
);

/* 11. 非法 board_code → 422（页面应显示错误态而非假数据） */
let rejected = false;
try {
  await req("GET", "/api/community/posts?board_code=hacker", { token });
} catch {
  rejected = true;
}
check("非法 board_code 返回 422（前端错误态兜住）", rejected);

console.log("\n==== 汇总 ====");
const failed = results.filter((r) => !r.ok);
console.log(`共 ${results.length} 项，通过 ${results.length - failed.length}，失败 ${failed.length}`);
if (failed.length) process.exitCode = 1;
