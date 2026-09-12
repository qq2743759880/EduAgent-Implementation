# task10 完工报告 —— me.html 个人中心接线（reshape-a）

> 执行：fe-html 接线独立 agent · 日期 2026-09-12 · 契约冻结 `contracts/reshape-a.json`（hash 30aeddbe）· GWT：资料/订单/券/收藏分页真实；收藏写路径 curl 补验。
> 改动文件：`edu-frontend/public/me.html`（仅此一个；后端/contracts/edu-api.js 零改动）。
> 提交：`fix(reshape)/task10: <hash 见 git log>`

## 一、交付概要（任务五项接线补全）

| # | 任务项 | 状态 |
|---|---|---|
| ① | 我的订单分页（GET /api/trade/orders，分页壳） | ✅ 新增区块：page/page_size 真实下发 + 状态筛选（6 态，router `_VALID_STATUSES` 实读对齐）+ 上一页/下一页 + 「共 N 笔 · 第 x/y 页」 |
| ② | 我的优惠券（unused） | ✅ 新增区块：`GET /api/coupons?status=unused` 服务端过滤 + 分页；面值按 coupon_type 语义展示（discount→x 折 / reduce→减 ¥x）；「去使用 → coupons.html」（券中心下单闭环已存在） |
| ③ | 我的收藏（GET /api/favorites → course-detail.html?id=） | ✅ 新增区块：卡片点击跳 `course-detail.html?id={series_id}`（course-detail.html L791 `pageId("id")` 取参，链路已通） |
| ④ | 资料编辑（PUT /api/users/me/profile） | ✅ 原已接线（pfForm + task121 弹窗，零改动）；本任务补 curl 往返实测（§二.4） |
| ⑤ | 无端点区块诚实占位 | ✅ 头像 = profile.avatar_url 真实渲染（Image onerror 回退 emoji 占位，不写死域名判断）；等级/积分 = gamification 真实（原有）；死链 /tickets 改诚实占位（工单页未上线，后端工单端点已有的说明文案） |

每区块三态齐全：加载中（t10-state 占位）/ 空态（真实空文案）/ 错误（错误详情 + 🔄 重试按钮）；未登录 → 区块内登录引导（`EAPI.buildLoginUrl("/me.html")`），不发起数据请求。

## 二、curl 实测证据（真实 HTTP，2026-09-12，学生 user000001）

### 2.1 订单分页壳
```
GET /api/trade/orders?page=1&page_size=5
 → {"code":0,"data":{"total":22,"page":1,"page_size":5,"items":[{order_no:"3-260906182637-eb4855",
    series_id:1002,series_title:"数值仿真进阶班·面授",order_amount:3999.0,discount_amount:3999.0,
    pay_amount:0.0,status:"pending",created_at:"2026-09-06T18:26:38",...},...]}}
GET /api/trade/orders?page=1&page_size=5&status=paid → {"total":1,"items":[{order_no:"1-260904101919-bf0fb5",status:"paid",pay_amount:2999.0}]}
GET /api/trade/orders?page=2&page_size=5 → total=22, page=2（jsdom 翻页测试同报文回放）
```
状态过滤语义经后端 `order/router.py _VALID_STATUSES` 实读核对：pending/paid/completed/cancelled/partial_refunded/refunded。

### 2.2 优惠券（unused）
```
GET /api/coupons?status=unused&page=1&page_size=4
 → {"code":0,"data":{"total":94,"items":[{coupon_id:51122,coupon_name:"平台折扣券02",coupon_type:"discount",
    face_value:0.8,min_spend:0.0,status:"unused",valid_to:"2026-09-16T16:10:52",...},...]}}
```
服务端 status 过滤生效（不带 status 时 total=102 → unused=94）。**注**：任务简报"69 张券"与当前库不符（数据持续演变），以实测 94 为准（漂移已登记 §五）。

### 2.3 收藏（读路径 + 点击跳转）
```
GET /api/favorites?page=1&page_size=4
 → {"code":0,"data":{"total":3,"items":[{favorite_id:30072,target_type:"series",series_id:1005,
    series_title:"交互设计项目班·直播",cover_url:"https://cdn.example.com/...",created_at:"2026-09-06T17:15:52"},...]}}
```
点击跳转链路：收藏卡 → `course-detail.html?id={series_id}`；course-detail.html L791 用 `EAPI.pageId("id")` 取参（task102 既有实证），链路闭合。

### 2.4 资料编辑 PUT 往返实测（改昵称→复原）
```
PUT /api/users/me/profile {"nickname":"task10_probe"}
 → {"code":0,"data":{nickname:"task10_probe",updated_at:"2026-09-12T10:59:36",...}}   ← 真实写库
GET /api/users/me/profile → nickname:"task10_probe"                                    ← 持久化验证
PUT /api/users/me/profile {"nickname":"小柚子同学"}（UTF-8 文件体）
 → {"code":0} → GET 复读 nickname:"小柚子同学"                                          ← 已复原
```
（首修 PUT 中文 body 直传 Git Bash 编码损坏报 40000 "error parsing the body"——改用 UTF-8 文件 `--data-binary` 后成功；纯测试手法问题，非契约缺口。）

### 2.5 头像
`GET /api/users/me/profile → avatar_url:"https://…（演示外链）"`：页面用 `new Image()` 真实加载，`onload` 渲染背景图 / `onerror` 保持 emoji 占位——不预判域名，资源可达与否诚实呈现。

## 三、资产消费证据（真实库数据）

| 资产 | 值 | 来源 |
|---|---|---|
| 订单 | 22 笔（pending 为主，paid 1 笔 1-260904101919-bf0fb5） | GET /api/trade/orders |
| 券 | unused 94 张（51122 平台折扣券02 8折 等） | GET /api/coupons?status=unused |
| 收藏 | 3 条（30072→series 1005 等） | GET /api/favorites |
| 档案 | 昵称往返 task10_probe→小柚子同学，updated_at 变更 | PUT/GET /api/users/me/profile |
| 统计 | learning-summary（6664s/2 班次）+ gamification（1280 分/Lv.10） | 页面既有区块，零改动随页生效 |

## 四、机验输出

```
node --check（7 个内联 script 全量）        → errors=0
grep -c "alert(" me.html                    → 0
grep -c "cdn\.example" me.html              → 0
grep -i "mock" me.html                      → 仅头部注释"均真实 API（无 MOCK）"反义引用
grep "\.match(" me.html                     → 仅 task121 既有学科偏好格式解析（用户输入格式校验，非 URL 取参；本任务新增代码零 match）
jsdom 运行时冒烟（真实捕获 API 报文回放，22/22 PASS）:
  A 登录态: 订单总数 22/页码 1/5/订单号与状态徽标渲染/券 94 张/券名折扣渲染/收藏 3 条→course-detail?id=1005 链接/
    翻页发 page=2 真实请求/状态筛选发 status=paid 且结果共 1 笔/死链 /orders、/tickets 清零/工单诚实占位 ✓
  B 未登录: 三区块登录引导 + 全程零数据请求 ✓
  C 收藏空态: "暂无收藏" 诚实空态 ✓
（jsdom 网络层以真实捕获报文回放，页面逻辑全真；Playwright 未使用）
```

**冒烟测试抓到并修复的真实缺陷**：首版订单行引用未定义的 `OD_STATUS`（`ReferenceError` → 区块落入错误态）——jsdom 冒烟 A2 失败暴露，补定义后 22/22。此缺陷 node --check 无法发现（运行时引用），证明运行时冒烟必要。

## 五、缺口上报清单 / 数据漂移登记

- **D1 简报数据漂移（记录，非缺口）**：任务简报"20 笔订单/69 张券/班次 7884"与当前库实测（22 笔订单/94 张 unused 券/班次 1、2）不符——库数据持续演变，全部以 curl 实测为准。
- **D2 收藏写路径补验（GWT 项）**：冻结契约 `GET /api/favorites` 为读端点；收藏**写路径**不在契约内（community 域有 POST /posts/{id}/favorite 为帖子收藏，系列收藏无 POST/DELETE 端点）。页面侧本任务按契约只做读+跳转（收藏动作在 course-detail 页，属 task04 范围）。如实登记：**系列收藏的增删写端点在冻结契约中不存在**——若演示需要"收藏/取消收藏"交互，需后端补端点走变更单。
- **D3 订单操作入口（范围外，不臆造）**：契约另有 POST /api/trade/order/{order_no}/cancel、支付链路等端点，但 task10 GWT 仅要求订单分页展示；未添加取消/支付按钮（避免超范围接线），任务简报 J6 去支付跳转由功能入口文案如实说明。
- **D4 售后工单页**：无 tickets 静态页/端点接线落点 → 功能入口改诚实占位（"工单页暂未上线（后端工单端点已有，页面待接）"），不留死链。

## 六、批判承接核对段

| 承接项 | 核对结果 |
|---|---|
| AGENTS.md 教训 1-10 | 逐条过：无 next 入口改动（纯静态页）；无 Playwright（jsdom 真报文回放）；pageId/无 match 新增（既有 task121 match 为用户输入格式解析，非查参）；无 alert；不改 edu-api.js（buildLoginUrl 复用）；实测契约优先（发现简报订单/券数量漂移以 curl 为准）；admin 守卫不适用（学生页，adminEntry 沿用）；无全局 $ 污染（IIFE 局部 var/函数） |
| task17（清单外不翻车）承接 | me.html 原死链 /orders、/tickets 正属"死按钮改诚实占位"范畴：/orders → 页内真实订单锚点 #sec-orders；/tickets → 诚实占位 |
| A 批全局 DoD（fe-html 只修不增） | 未新增功能页；页内三区块为 task10 GWT 明确要求的接线补全；样式复用糖果 token + 新增 t10-* 最小列表样式（视觉对齐 .form-card 卡片族） |
| 契约冻结 30aeddbe 只修不增 | 仅消费冻结端点（trade/orders、coupons、favorites、users/me/profile 均在冻结清单）；零新增端点 |

## 七、三视角自检

- **Eng 架构**：三区块各自 IIFE 隔离、失败互不影响（Promise.catch 各自兜底 + 重试闭包）；分页状态机简单可控（page/pages 双按钮禁用边界）；金额/日期展示走 Number/String 规整，`esc()` 全量转义防注入；冒烟测试以真实捕获报文回放（fixtures 落盘可复跑 `node C:\tmp_lcheck\smoke_me.js`，或按 §二 curl 重采）。
- **Design 体验**：复用 .section/.s-title/.nav-item 既有骨架；t10 卡片对齐 form-card 视觉（2px 边框 + 圆角 + tabular-nums）；状态徽标语义配色（pending 橙/paid 绿/cancelled 蓝/refund 紫）；三态齐全；空态文案给下一步动作引导（券中心/课程中心）。
- **CEO 范围**：严格五项接线（订单分页/券 unused/收藏跳转/资料编辑实测/占位诚实），未越界做支付/取消/收藏写等未冻结交互；发现的数据漂移与契约缺口（D1/D2）如实上报不掩盖；演示口径=真实数据 + 诚实空态，零 MOCK。

## 八、遗留

- D2 系列收藏写端点（POST/DELETE /api/favorites）不在冻结契约——需演示"收藏动作"时走契约变更单。
- 订单行内 items/payments 为空数组（列表壳不嵌详情）；如需"订单详情（含支付记录）"展示，GET /api/trade/order/{order_no} 已在契约，建议后续任务接线。
