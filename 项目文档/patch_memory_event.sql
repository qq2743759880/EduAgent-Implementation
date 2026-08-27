-- ============================================================
-- task-M1 记忆事件溯源 + Dream 巩固（production-upgrade-plan P1/P3）
-- 说明：
--   - user_memory_event 为长时记忆「唯一事实源」（append-only 事件流）。
--     * 写=INSERT 新行；更新/删除=新行 + 旧行 valid_to 盖章（单条 UPDATE 仅用于版本盖章，不覆盖内容）。
--     * 每个 (entity_id) 恒有且仅有一条 valid_to IS NULL 的行 = 当前 HEAD（ChronoMem 语义）。
--     * event_type='delete' 的 HEAD 表示「该实体当前已删除」（检索显式排除）。
--   - 检索强制 WHERE valid_to IS NULL AND event_type <> 'delete'，保证绝不召回废弃版本（Ninad 审计）。
--   - user_id 直接关联 sys_user.id（不做外键，接口侧 RBAC + owner 校验，与 user_memory 约定一致）。
--   - trace_id 指向触发该事件的 LLM/工具调用链路（每条非 consolidate 事件必填，自证清白）。
--   - embedding/supports 为 JSON：向量快照（1024 维 JSON）+ 支持证据 [event_id]（对齐 CortexDB）。
--   - access_count/last_access_at 为近因遥测元数据（非记忆内容，允许 touch 更新）。
--   - user_memory_entity_seq 为 entity_id 分配器（独立自增，避免对事件表做自引用 UPDATE）。
-- ============================================================

CREATE TABLE IF NOT EXISTS user_memory_event (
    id            BIGINT          NOT NULL AUTO_INCREMENT    COMMENT '事件序号（自增主键，写序）',
    event_type    VARCHAR(32)     NOT NULL                  COMMENT 'create/update/delete/consolidate/rewind',
    entity_id     BIGINT          NOT NULL                  COMMENT '记忆实体 ID（跨版本同一 entity_id；向量主键=entity_id）',
    user_id       BIGINT          NOT NULL                  COMMENT '所属用户 ID，对应 sys_user.id',
    memory_type   VARCHAR(32)     NULL                      COMMENT '类型: preference/goal/profile/correction/fact',
    topic         VARCHAR(64)     NULL                      COMMENT 'topic 分组（用于索引聚合）',
    content       TEXT            NOT NULL                  COMMENT '本版本记忆正文（不可变，永不 UPDATE 覆盖）',
    embedding     JSON            NULL                      COMMENT '可选：向量快照（1024 维 JSON）',
    importance    INT             NULL                      COMMENT '重要性 1-5',
    score         FLOAT           NULL                      COMMENT '综合分（遗忘排序用）',
    access_count  INT             NOT NULL DEFAULT 0         COMMENT '召回次数（近因/热度加权，元数据）',
    last_access_at DATETIME       NULL                      COMMENT '最近一次被召回时间（recency_bonus 基准）',
    valid_from    DATETIME        NOT NULL                  COMMENT '本版本生效时间',
    valid_to      DATETIME        NULL                      COMMENT 'NULL=当前有效（HEAD）；盖章=废弃版本',
    trace_id      VARCHAR(64)     NULL                      COMMENT '触发该事件的 LLM/工具调用链路（审计溯源）',
    operator      VARCHAR(64)     NULL                      COMMENT 'user/admin/dream/system',
    supports      JSON            NULL                      COMMENT '[event_id] 支持证据（consolidate 引用被合并原事件）',
    created_at    DATETIME        NOT NULL                  COMMENT '事件落库时间',
    INDEX idx_event_user     (user_id, entity_id, valid_to),
    INDEX idx_event_trace    (trace_id),
    INDEX idx_event_entity  (entity_id, valid_to),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='长时记忆事件溯源表（append-only 事实源）';

CREATE TABLE IF NOT EXISTS user_memory_entity_seq (
    id BIGINT NOT NULL AUTO_INCREMENT,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='entity_id 分配器（独立自增，避免事件表自引用）';
