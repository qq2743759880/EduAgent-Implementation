/**
 * MessageComposer — AI 问答输入区（task50 核心，candy-playful frozen）
 * 对齐 chat.html 效果图 composer：
 *  - hint 行：📎 上下文徽标（?context=session:{id}）+ 排队提示 pill（首包前 10s「AI 正在思考…」）
 *  - degrade banner：done.data.degraded_reason 降级答案提示（琥珀 dashed，不吞错）
 *  - input-row：白卡 + border-foreground 粗描边 + 3D 阴影；Textarea 自动增高（44~120px）
 *  - 发送（糖果绿 ➤）/ 停止（糖果红 ■）切换；Enter 发送 / Shift+Enter 换行 / 中文输入法组合不误发
 */
"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface MessageComposerHandle {
  /** 焦点到输入框（新建会话 / 恢复后调用） */
  focusInput: () => void;
}

export interface DegradeInfo {
  /** 降级标题，如「排队人数较多，已为你降级回答」 */
  title: string;
  /** 降级正文，契约⑬ done.data.degraded_reason */
  detail: string;
}

export interface MessageComposerProps {
  /** 发送回调（提交后由组件自行清空输入） */
  onSend: (text: string) => void;
  /** 停止生成回调（流式中点击 ■） */
  onStop: () => void;
  /** 是否正在流式生成（决定发送/停止按钮切换） */
  streaming: boolean;
  /** 锁定输入（如历史加载失败/未登录） */
  disabled?: boolean;
  /** 上下文徽标文案（可为空不渲染） */
  contextTag?: string | null;
  /** 排队提示（首包前，服务端排队/检索中） */
  queueing?: boolean;
  /** 降级 banner（流完成时 done.data.degraded_reason 透出），null 不渲染 */
  degrade?: DegradeInfo | null;
  placeholder?: string;
  className?: string;
}

const MAX_H = 120;
const MIN_H = 44;

export const MessageComposer = React.forwardRef<MessageComposerHandle, MessageComposerProps>(
  function MessageComposer(
    {
      onSend,
      onStop,
      streaming,
      disabled = false,
      contextTag = null,
      queueing = false,
      degrade = null,
      placeholder = "输入你的问题…（Enter 发送 / Shift+Enter 换行）",
      className,
    },
    ref,
  ) {
    const taRef = React.useRef<HTMLTextAreaElement>(null);
    const [value, setValue] = React.useState("");

    React.useImperativeHandle(ref, () => ({
      focusInput: () => taRef.current?.focus(),
    }));

    const autoResize = React.useCallback(() => {
      const ta = taRef.current;
      if (!ta) return;
      ta.style.height = "auto";
      ta.style.height = `${Math.min(MAX_H, Math.max(MIN_H, ta.scrollHeight))}px`;
    }, []);

    const handleSubmit = React.useCallback(
      (raw: string) => {
        if (disabled || streaming) return;
        const text = raw.trim();
        if (!text) return;
        onSend(text);
        setValue("");
        requestAnimationFrame(autoResize);
      },
      [disabled, streaming, onSend, autoResize],
    );

    const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key !== "Enter" || e.shiftKey) return;
      const native = e.nativeEvent as unknown as { isComposing?: boolean };
      if (native.isComposing) return; // 中文输入法选字回车不误发
      e.preventDefault();
      handleSubmit(value);
    };

    const canSend = value.trim().length > 0 && !disabled && !streaming;
    const fieldDisabled = disabled && !streaming; // streaming 时仍可打字，但发送按钮被占位为停止

    return (
      <div className={cn("", className)}>
        {/* hint 行：上下文徽标 + 排队提示 */}
        {(contextTag || queueing) ? (
          <div className="mb-2 flex flex-wrap items-center gap-2" data-slot="chat-hint">
            {contextTag ? (
              <span
                data-slot="chat-context-tag"
                className="inline-flex items-center gap-1 rounded-full border-2 border-candy-purple/30 bg-candy-purple-soft px-2.5 py-0.5 text-3xs font-bold text-candy-purple"
              >
                📎 {contextTag}
              </span>
            ) : null}
            {queueing ? (
              <span
                role="status"
                aria-live="polite"
                className="inline-flex items-center gap-1.5 rounded-full border-2 border-candy-green/40 bg-candy-green-soft px-2.5 py-0.5 text-3xs font-bold text-candy-green"
              >
                <span
                  aria-hidden="true"
                  className="size-3.5 rounded-full border-2 border-candy-green/40 border-t-candy-green animate-spin"
                />
                AI 正在思考…
              </span>
            ) : null}
          </div>
        ) : null}

        {/* 降级 banner（done.data.degraded_reason） */}
        {degrade ? (
          <div
            data-slot="chat-degrade"
            role="status"
            className="mb-2 flex items-start gap-2 rounded-xl border-2 border-dashed border-candy-orange/50 bg-candy-orange-soft px-3 py-2 text-3xs leading-5 text-candy-orange"
          >
            <span aria-hidden="true" className="mt-px shrink-0 text-md">⚠️</span>
            <span>
              <b className="font-black">{degrade.title}</b>
              {degrade.detail ? <span className="ml-1">{degrade.detail}</span> : null}
            </span>
          </div>
        ) : null}

        {/* 输入卡片 */}
        <div
          data-slot="chat-composer"
          className="flex items-end gap-2.5 rounded-2xl border-[3px] border-foreground bg-background p-2.5 shadow-[0_5px_0_color-mix(in_oklch,var(--foreground),transparent_82%)]"
        >
          <textarea
            ref={taRef}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              autoResize();
            }}
            onKeyDown={onKeyDown}
            rows={1}
            disabled={fieldDisabled}
            placeholder={disabled ? "历史加载失败，无法发送" : placeholder}
            aria-label="提问输入框"
            className="max-h-[120px] min-h-11 flex-1 resize-none border-0 bg-transparent py-1 pl-1 pr-1 text-sm leading-6 text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
          />
          {streaming ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="停止生成"
              className="flex size-[52px] shrink-0 items-center justify-center rounded-2xl border-[3px] border-foreground bg-candy-red text-lg font-black text-white shadow-[0_4px_0_color-mix(in_oklch,var(--candy-red),black_35%)] transition-transform enabled:active:translate-y-[2px] enabled:active:shadow-none hover:bg-[color-mix(in_oklch,var(--candy-red),black_8%)]"
            >
              ■
            </button>
          ) : (
            <button
              type="button"
              onClick={() => handleSubmit(value)}
              disabled={!canSend}
              aria-label="发送"
              className="flex size-[52px] shrink-0 items-center justify-center rounded-2xl border-[3px] border-foreground bg-candy-green text-lg font-black text-white shadow-[0_4px_0_color-mix(in_oklch,var(--candy-green),black_30%)] transition-all hover:bg-[color-mix(in_oklch,var(--candy-green),black_8%)] enabled:active:translate-y-[2px] enabled:active:shadow-none disabled:pointer-events-none disabled:opacity-40"
            >
              ➤
            </button>
          )}
        </div>
      </div>
    );
  },
);