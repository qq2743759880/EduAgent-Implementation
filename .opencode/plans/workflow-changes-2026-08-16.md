# EduAgent 开发工作流完善记录

> 日期：2026-08-16
> 依据：`.opencode/plans/` 5 份文档（README/dev-plan/tech-arch/frontend-spec/edu-data-refactor）

## 关键决策

### 架构决策

1. **模块化单体（不拆微服务）**
   - 理由：团队规模/流量不支持微服务运维成本（注册中心/RPC/分布式事务）
   - 采纳分层思想：router→service→repository→infra 四层
   - 按域切目录（domains/）为未来拆分留缝

2. **响应壳统一 `{code, message, data}`**
   - 成功：`{code: 0, message: "ok", data: <任意>}`
   - 失败：`{code: <字符串>, message: <用户可读>, data: null}`
   - 兼容：detail 字段仅在 DEBUG 下返回

3. **Repository 层数据访问归口**
   - 基类 CrudMixin：table/pk/soft_delete 三个字段即可派生完整 CRUD
   - 软删约定：yn=1 过滤，DELETE 改为 UPDATE yn=0
   - keyset 分页替代 OFFSET 深度分页

4. **核心框架层 app/core/**
   - resp.py：统一响应壳
   - cache.py：Redis 缓存三防（穿透/击穿/雪崩）
   - lock.py：SETNX+Lua 分布式锁
   - breaker.py：Polaris 三态熔断器
   - trace.py：ContextVar 链路追踪
   - crud_mixin.py：Repository 基类

5. **中间件不做泛化，横切关注点分类落地**
   - HTTP 层：RateLimit/SecurityHeaders/RequestLogging/Auth（中间件）
   - 框架层：cache/lock/breaker（库，业务显式调用）
   - 原因：缓存读写是业务语义，装饰器/显式封装比"猜每个请求该不该缓存"可靠

### 数据架构决策

6. **edu.sql 66 表为唯一权威**
   - 三套课程体系（curriculum_*/series_*）统一为 series 体系
   - 三套题库（admin_question_bank/admin_question/question）统一为 question 体系
   - 前端 snake_case，删除全部别名兜底

7. **AI Agent 升级为 LangGraph orchestrator-worker**
   - 当前：单 agent 循环（decision→retrieve/tool→generate，≤3 轮）
   - 目标：route→plan→fan-out(并行子代理)→merge→reflect→answer
   - 补 Redis checkpointer（durable execution）
   - 三层记忆 + compaction + effort scaling

## 新建文件清单

| 文件 | 用途 |
|------|------|
| `app/core/__init__.py` | 框架层包说明 |
| `app/core/resp.py` | 统一响应壳 |
| `app/core/cache.py` | Redis 缓存三防 |
| `app/core/lock.py` | 分布式锁 |
| `app/core/breaker.py` | 熔断器 |
| `app/core/trace.py` | 链路追踪 |
| `app/core/crud_mixin.py` | Repository 基类 |

## 待执行任务（来自 dev-plan.md）

按优先级排列的下一步任务：

1. **P0 备份**（task00）：mysqldump + Milvus/Neo4j 快照
2. **P1 数据库重构**（task01~05）：66 表 DDL 重建 + 13 旧表删除 + sys_user 改造
3. **P2 数据重灌**（task06~08）：full 档生成 + 计数校验 + admin 恢复
4. **P3 后端底座**（task09~15）：core/ + middleware/ + 课程域 + 题库域 + 响应壳适配
5. **AI/RAG 升级**（task24~32）：LangGraph 重构 + 记忆 + RAG reranker + contextualize

## 回滚策略

- 数据库：P0 备份（task00）可在任一步骤前恢复
- 代码：git 分支回退，每 task 独立提交
- Milvus：重建前保留集合 schema 定义与 Neo4j 计数快照