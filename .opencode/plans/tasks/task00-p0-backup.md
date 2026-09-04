# task00: P0 全量备份与快照（mysqldump + Milvus/Neo4j）

> **类型**：ops ｜**执行工具**：Trae ｜**阶段**：P0 ｜**并行组**：W1 ｜**工作量**：M
> **前置**：无 ｜**后置（联调节点）**：task01（安全网，全阶段可用回滚点）

## 1. 选型依据
- tech-source-audit.md §七（回滚安全网：P0 备份是全部重构的可回滚前提）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 编写备份脚本（mysqldump + 快照导出） |
| 验证 | sd-tester | 恢复演练验证 |
| 审查 | review-screener-1 | 正确性审查（备份清单完整性） |
| 工具 | RunCommand+mysql CLI | 确认库表清单与行计数 |
| 提交 | commit skill | 每 task 一个 commit |

## 3. 执行方式（Trae 手动调度，无 Workflow API）

Trae Code 无 opencode 专属的 `Workflow()` API，按 `D:\.ai-hub\workflows\dev-standard.mjs` 的 8 阶段**手动调度**（效果等价）：
```
1. 开发阶段   -> 调 sd-dev + be-architect + be-validator（读任务文档 + tech-source-audit）
2. 测试阶段   -> 调 sd-tester（+ sd-challenger 对抗）；数据库校验用 RunCommand 跑 mysql CLI / Python 脚本（无 mysql MCP）
3. 修正阶段   -> 据测试报告回 sd-dev 修复
4. 审查阶段   -> 调 review-screener-1/2/3 -> review-moderator -> review-judge（SARIF）
5. 提交阶段   -> git commit（message 含 task 编号）
```

mysql MCP 未在 Trae 环境注册（当前 MCP 仅 integrated_code_mode / integrated_goal）：
- 数据库校验改用 **RunCommand + mysql CLI / Python 脚本**（先例：scripts/verify_schema.py、scripts/verify_task07_counts.py）
- 或手动在 设置->MCP 按 `D:\.ai-hub\mcp\index.json` 模板添加 mysql


## 4. 实现规划要点
- mysqldump：`--routines --triggers --single-transaction --default-character-set=utf8mb4` 全库（105 表现状）
- Milvus `edu_knowledge` 健康报告 + `pf_bagu_kb` schema 定义导出（保留 loader.py ensure_collection_exists 的 id/chunk_id/content/content_type/source_file/dense_vec 1024/sparse_vec/tenant_id/visibility 字段定义）
- Neo4j 计数快照（基线 4981 条 / 1330 节点 6194 关系）
- 备份清单 + SHA256 校验和；恢复演练在独立测试实例真实执行

## 5. 验收标准（Given/When/Then 全文）
- Given 生产 MySQL/Milvus/Neo4j 均可用，When 执行备份脚本，Then 生成全库 dump（含 66 表 + 存量自建表）、`pf_bagu_kb` 与 `edu_knowledge` 集合 schema 定义文件、Neo4j 计数快照均落盘且校验和通过
- Given 备份文件已生成，When 在独立测试实例执行恢复演练，Then 恢复成功且关键表行计数与源库一致，恢复演练报告记录耗时
- Given 后续任意阶段失败，When 执行回滚，Then 可依据备份清单在任一前置阶段恢复
- Given admin 账号行存在，When 执行行级备份（SELECT admin 行），Then 备份文件含 admin/manager 账号与角色关联（供 task08 恢复）

## 6. 交接与记忆
- 完成 → 更新 `D:\.ai-hub\memory\project-handoff.md` task00=DONE → `powershell -File D:\.ai-hub\sync.ps1`
- 交付物：备份文件 + 恢复演练报告 + SHA256 清单
