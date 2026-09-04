# task98: 生产可复用数据库验收体系（verify.py 统一框架）

> **类型**：infra ｜**执行工具**：Trae ｜**阶段**：基础设施（紧随 task05/task07 修复后）｜**并行组**：W1 ｜**工作量**：L
> **前置**：task05（verify_schema.py 基座）+ task07 修复（精确断言/5 维度质量脚本）+ `db-acceptance-principles.md`（6 点原则）
> **后置**：生产环境所有数据库迭代（建表/改表/注册功能/发布）的验收入口
> **性质**：**可复用基础设施，非 per-task 一次性脚本**——用户注册、增添功能、修改表结构时均沿用

## 1. 选型依据
- `db-acceptance-principles.md`（用户 6 点验收原则 P1~P6）
- tech-source-audit.md §一（edu.sql 权威机制化）
- 对标：dbt tests / Great Expectations（数据质量五维度：完整性/唯一性/有效性/一致性/时序性）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | verify.py 统一入口 + 三子命令 |
| 验证 | sd-tester + RunCommand+mysql CLI | 5 维度断言 + 动态期望值 |
| 审查 | review-screener-1 | CI gate 配置审查 |
| 提交 | commit skill | — |

## 3. 交付物
```
scripts/verify.py 统一入口（可复用，替代 per-task 一次性脚本）
├── schema   → 结构校验（66 表 DDL vs information_schema，0 差异）  [继承 task05 verify_schema.py]
├── counts   → 计数断言（精确 ==，期望值动态计算自权威源）         [继承 task07 修复后脚本]
├── quality  → 5 维度质量（完整性/唯一性/有效性/一致性/时序性）     [继承 task07 修复后脚本]
└── all      → 全量（CI 门禁入口，任一失败 exit 1 禁止合并）
+ .schema-acceptance.yaml（容差阈值/枚举字典/白名单，文档定义标准 P1）
+ .github/workflows/db-acceptance.yml（CI gate：DDL 变更/发布触发）
+ docs/db-acceptance-guide.md（生产使用手册：改表流程/注册功能验收/发布门禁）
```

## 4. 实现规划要点（严格按 6 点原则）
- **P1 先文档后脚本**：`.schema-acceptance.yaml` 定义标准（容差/枚举/白名单），脚本只读配置实现
- **P2 精确断言**：`==` 或 `abs(delta)<=TOL`，TOL 从 yaml 读（默认 0），禁止 `>=`
- **P3 动态计算**：机构数 `SELECT COUNT(*) FROM org_institution`、模板数从 seeds/生成配置读、枚举字典从 DB DISTINCT+权威源比对；禁硬编码魔数
- **P4 CI 门禁**：GitHub Actions `verify.py all`，非零退出拒绝合并；DDL 变更自动触发
- **P5 五维度**：每维度 ≥1 断言（完整性=外键+引用必达；唯一性=唯一键+逻辑重复；有效性=值域/金额/日期；一致性=跨表守恒如 order=SUM(items)/payment=order；时序性=created_at<=updated_at/start<=end）
- **P6 口径漂移**：标准变更→先改 yaml+文档→再改脚本→变更日志（版本/日期/理由/实证）→报告显式声明

## 5. 验收标准（Given/When/Then）
- Given 生产环境任何建表/改表，When 运行 `verify.py schema`，Then 0 差异且 exit 0，失败则 CI 拒绝合并（P4）
- Given 用户注册/新功能上线（数据变更），When 运行 `verify.py all`，Then 计数精确== + 5 维度质量全绿（P2/P5）
- Given 机构数从 6 变 7（新增租户），When 运行 `verify.py counts`，Then 期望值自动重算（P3，无硬编码）
- Given 口径变更，When 修改标准，Then 文档/yaml 先行 + 变更日志记录（P1/P6），脚本同步

## 6. 交接与记忆
- 完成 → 看板 task98=DONE → sync.ps1
- 交付物：verify.py + .schema-acceptance.yaml + CI workflow + 使用手册
- **生产复用**：后续所有数据库任务（task11~14 改表、用户功能新增）直接用 `verify.py all` 作验收，不再写一次性脚本