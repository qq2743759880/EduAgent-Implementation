-- ============================================================
-- task-T1 工具调用闭环：扩展 mcp_tool_call_log.status 枚举
-- ------------------------------------------------------------
-- 新增两个状态（对齐 production-upgrade-plan.md P6 / Codex auto-review）：
--   REJECTION_LIMIT : 同会话内连续被拒达上限（TOOL_CONSECUTIVE_REJECTIONS=3）
--                     后中断该回合工具循环（AC3）
--   MANUAL_GUIDE    : 所有可用工具均失败/熔断后，输出结构化人工操作指南并停止（AC1/AC2）
--
-- 说明：MySQL ENUM 为追加式 ALTER；旧值 SUCCESS/ERROR/TIMEOUT/SKIPPED 保持不变，
--       既有 task33 审计逻辑不受影响。请在发布前于目标库执行一次。
-- ============================================================

ALTER TABLE `mcp_tool_call_log`
  MODIFY COLUMN `status`
    ENUM('SUCCESS','ERROR','TIMEOUT','SKIPPED','REJECTION_LIMIT','MANUAL_GUIDE')
    COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'SUCCESS'
    COMMENT '调用状态：SUCCESS/ERROR/TIMEOUT/SKIPPED/REJECTION_LIMIT（拒绝熔断）/MANUAL_GUIDE（人工指南）';

-- 校验（可选）：确认枚举已包含新值
-- SHOW COLUMNS FROM `mcp_tool_call_log` LIKE 'status';
