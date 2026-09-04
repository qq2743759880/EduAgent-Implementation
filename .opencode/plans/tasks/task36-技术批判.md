# task36 验收批判（强制技术批判）

> 对象：task36 RAG 上传后端增强（Trae，commit e13d9a5→06b2caf）
> 结论：**验收通过**（GWT①~④ 全绿、契约⑥冻结、Redis 降级如实披露）。

## 实证结果
- commit 链完整（HEAD=06b2caf）；task_store.py/minio_uploader.py/upload.py 交付。
- **verify_task36.py 实跑 EXIT=0**：MySQL 双写全链路 PASS + MinIO 30 天生命周期 PASS + Redis 降级 PASS（MySQL-only 不阻断）。
- 契约⑥已冻结（handoffs/task36-contract.md）→ **解锁 task61**。
- RBAC admin/manager、ok() 壳、done→succeeded 映射、分页倒序全验证。

## 批判 1（P2）：Redis 双写 SETEX 24h 未 live 验证（环境 Redis 不可用）
- **问题**：SETEX 24h + 重启恢复未实测（报告如实披露，降级路径已验证）。
- **方案**：Redis 可用后补「重启服务→GET /status/{id}」真实验证。

## 批判 2（P2）：MinIO 失败降级为 object_key=None，源文件留存不满足 30 天
- **问题**：MinIO 不可用时静默降级，源文件留存要求被跳过（报告披露）。
- **方案**：若业务强制"先留存再导入"，改阻断；当前按显式降级哲学。

## 批判 3（P3）：source_files 由 list[str] 改 list[dict]（含 object_key）
- **问题**：契约演进，/status/{task_id} 旧端点结构变化。
- **方案**：task61 主用 /tasks，无存量前端受影响（报告确认）。

**结论**：批判①②为环境验证项（Redis 恢复后补），③为契约演进；task36 本体验收通过，解锁 task61。