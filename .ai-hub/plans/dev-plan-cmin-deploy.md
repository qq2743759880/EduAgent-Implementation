# Feature: C 阶段最小部署包(本机同构一键拉起)

## 개요
让 EduAgent 在与本机同构的环境(Windows 主机+VM Docker)里"实际跑起来":一键 start/stop/status 脚本+生产配置模板+DEBUG=False 端到端验证+部署 README。范围红线:不动 Linux/容器化/公网 HTTPS/CI-CD/前端大改/数据库迁移/任何 API 契约。

## 需求前提挑战
| # | Premise | Confirm |
|---|---------|---------|
| P1 | 目标环境=本机同构(Windows+VM Docker),交付物=脚本+配置模板+文档,不迁移不容器化 | agree(2026-09-13 用户逐条确认) |
| P2 | DEBUG=False 全功能可用是硬验收;发现的 DEBUG 依赖项就地修复登记 | agree |
| P3 | 契约零变更;新增仅限部署配置项(非业务字段) | agree |
| P4 | 前端生产 build 纳入尝试;失败且修复>1 天→降级 dev 模式交付并登记 | agree |
| P5 | 密钥零入库(.env.example 占位+生成指引);快照/备份不进 git | agree |
| P6 | 验收口径=干净进程环境一条命令拉起+check-demo 8/8+核心页 CDP 抽验;不含公网/HTTPS/CI-CD | agree |

4 问结论:Q1 为什么现在 A 批双轴 DONE+B 批全绿,"实际跑起来"为用户当前最高优先;DEBUG=False 形态从未端到端验证(P1-8 门禁正好闭环);AGENTS.md 启动命令已实测过时 / Q2 现状方案 靠会话记忆手工启动+check-demo 只查不拉;成本=换机器即瘫 / Q3 窄楔子 四件交付=一键脚本+配置模板+DEBUG=False 验证+README;不做 Linux/容器化/HTTPS/CI-CD/前端大改/DB 迁移 / Q4 未来适配 脚本接口=compose 编排前身,.env.example=K8s Config 前身,README=runbook 第一章,零废弃

## 任务分解

> 契约冻结顺序:**零 API 契约变更(P3)**。唯一把关物=**部署配置项清单**(taskC0 产出,交用户过目后再定稿——沿用"接口清单用户逐条审"精神:配置项即部署契约)。
> 前端页面任务:**本批无新增页面**,HTML gate 不触发;若验证中确需新页面,按 gate 流程另行送审(P6' 同款纪律)。

### taskC0 生产配置模板+配置项清单
- **选型依据**:P2/P5;.env.example 对齐 config.py 全部 Settings 字段(现状自证);强密钥=secrets.token_hex 指引
- **GWT**:Given 干净 checkout;When 复制 .env.example→.env 并按指引生成密钥;Then ①后端 ENV_NAME=prod DEBUG=false 启动成功(P1-8 门禁过,无默认密钥告警)②**部署配置项清单**(键/默认值/必填性/影响面)产出交用户逐条审,审后定稿
- **前置**:无。**DoD**:清单用户签字+模板入库
### taskC1 一键脚本三件套(start/stop/status)
- **选型依据**:Node 脚本(与 check-demo 同栈、无 PowerShell 执行策略问题、可跨平台);复用 check-demo 作 status;scripts/deploy/ 目录
- **GWT**:Given 干净进程环境(全 kill);When `node deploy.mjs start`;Then Redis(docker)→后端(生产 env)→前端(按 C2 结论 build/start 或 dev)依序拉起,check-demo 8/8;`stop` 全端口清零;`status`=check-demo 原样
- **前置**:taskC0、taskC2(C2 定前端形态)
### taskC2 前端生产 build 尝试(P4)
- **选型依据**:P4;next build 风险已知(B3 agent:webpack 层未验)
- **GWT**:When next build;Then 成功→next start 接入 C1 脚本;失败→按修复成本判定,>1 天=降级 dev 模式交付+登记(窄楔子出口)
- **前置**:无(可与 C0 并行)
### taskC3 DEBUG=False 端到端验证(P2 硬验收)
- **GWT**:Given 生产配置(C0)+全栈拉起(C1);When 双账号登录→核心页 CDP 抽验(8 页)→无 token 全 401→50301 脱敏态;Then 全绿;**发现的 DEBUG 依赖项就地修复并登记**(预期候选:CORS origins/refresh 流程/X-Force 头仅 DEBUG 生效)
- **前置**:C0、C1
### taskC4 部署 README(runbook 第一章)
- **选型依据**:P1;文档结构=前置清单(VM/Redis/MySQL/密钥)→步骤→故障对照(引 check-demo 指引)→回滚
- **GWT**:Given 从未接触本项目的新人;When 照 README 从零操作;Then 到达与 C5 相同的验收态;每个 check-demo 红项都有对应章节
- **前置**:C3(反映最终形态)
### taskC5 最终验收:干净环境一条命令+批判收口
- **GWT**:Given 全 kill 的干净环境;When 一条命令;Then check-demo 8/8+8 核心页 CDP 零错+登录链路绿;强制技术批判(≥3 条竞品对标:对标同类自部署教育平台/一键部署工程)登记 tracker
- **前置**:C1-C4 全部

## 规划自审
### CEO 范围自审
- finding1:"实际跑起来"若被理解为公网上线则严重超范围。处置:P6 已锁口径=本机同构一键拉起;公网/HTTPS 归 C 阶段全量,交付物内显式声明边界。
- finding2:DEBUG=False 可能暴露成片依赖(此前从未跑过),修复量不可预估。处置:C3 预算=发现即修但设上限(>2 天工作量→停下上报,窄楔子纪律)。
### Eng 架构自审
- finding1:next build 若与 Turbopack 专属用法冲突,修复可能牵连业务代码。处置:C2 降级出口(>1 天即 dev 模式),不为构建 重构页面。
- finding2:start 脚本拉起 VM 内 Docker 服务不可脚本化(VM 电源在宿主 GUI)。处置:VM 相关仅输出指引+联动 check-demo 红项,不假装能拉起。confidence: medium-high(P1-8 门禁与 50301 已就位,未知数集中在 CORS/refresh 生产态)。
### Design 体验自审
- finding1:生产配置下前端若仍有默认密钥/DEBUG 横幅残留,观感即"假生产"。处置:C3 验收含"页面无 DEBUG 水印/无虚拟管理员入口"检查项。
- finding2:README 若只写成功路径,故障时新人即瘫。处置:C4 GWT 要求每个 check-demo 红项有对应章节。
