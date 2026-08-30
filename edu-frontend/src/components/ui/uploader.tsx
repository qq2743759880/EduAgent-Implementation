"use client"

import * as React from "react"

import { cn } from "@/lib/utils"
import { CloudUploadIcon, FileIcon, XIcon, LoaderCircleIcon, CircleAlertIcon } from "lucide-react"
import { Button } from "@/components/ui/button"

export type UploadItemStatus = "idle" | "uploading" | "done" | "error";

export type UploadItem = {
  id?: string;
  name: string;
  size: number;
  status?: UploadItemStatus;
  percent?: number;
  error?: React.ReactNode;
};

export type RejectedItem = {
  file: File;
  reason: "size" | "count";
};

/**
 * 上传器：拖拽 + 点击 + 校验（accept / maxSize / maxFiles） + 受控进度列表。
 *  - onFiles：校验通过的文件（调用方上传并推进 value 内 percent）
 *  - onReject：被拒绝的文件及原因（不吞错，展示拒绝原因）
 *  - value：受控上传项列表（含进度/错误），渲染明细
 */
function Uploader({
  accept,
  multiple = false,
  maxSize,
  maxFiles,
  value = [],
  onFiles,
  onReject,
  onRemove,
  disabled = false,
  label = "点击选择或拖拽文件到此处",
  hint,
  acceptHelp,
  className,
  inputClassName,
}: {
  accept?: string;
  multiple?: boolean;
  maxSize?: number; // bytes
  maxFiles?: number;
  value?: UploadItem[];
  onFiles?: (files: File[]) => void;
  onReject?: (rejected: RejectedItem[]) => void;
  onRemove?: (item: UploadItem, index: number) => void;
  disabled?: boolean;
  label?: React.ReactNode;
  hint?: React.ReactNode;
  acceptHelp?: React.ReactNode;
  className?: string;
  inputClassName?: string;
}) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);
  const id = React.useId();
  const fileInputId = `${id}-uploader`;

  const handleFiles = React.useCallback(
    (fileList: FileList | null) => {
      if (!fileList) return;
      const picked = Array.from(fileList);
      const accepted: File[] = [];
      const rejected: RejectedItem[] = [];

      const withinCount = maxFiles != null ? picked.length <= maxFiles : true;
      if (!withinCount) {
        for (const f of picked) rejected.push({ file: f, reason: "count" });
      } else {
        for (const f of picked) {
          if (maxSize != null && f.size > maxSize) {
            rejected.push({ file: f, reason: "size" });
          } else {
            accepted.push(f);
          }
        }
      }

      if (accepted.length > 0) onFiles?.(accepted);
      if (rejected.length > 0) onReject?.(rejected);
    },
    [maxSize, maxFiles, onFiles, onReject]
  );

  return (
    <div className={cn("flex w-full flex-col gap-2", className)} data-slot="uploader">
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled || undefined}
        aria-label={typeof label === "string" ? label : "上传文件"}
        onKeyDown={(e) => {
          if (disabled) return;
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onClick={() => {
          if (!disabled) inputRef.current?.click();
        }}
        onDragOver={(e) => {
          if (disabled) return;
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          if (disabled) return;
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer?.files ?? null);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border px-6 py-8 text-center outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
          dragging && "border-primary bg-primary/5",
          disabled && "pointer-events-none opacity-50",
          inputClassName
        )}
      >
        <CloudUploadIcon className="size-8 text-muted-foreground" aria-hidden="true" />
        <div className="text-sm text-foreground">{label}</div>
        {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
        {acceptHelp ? <div className="text-xs text-muted-foreground">{acceptHelp}</div> : null}
      </div>
      <input
        id={fileInputId}
        ref={inputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
        className="sr-only"
      />
      {value.length > 0 ? (
        <ul className="flex flex-col gap-1.5" aria-label="已选择文件">
          {value.map((item, i) => {
            const status = item.status ?? "idle";
            const sizeLabel =
              item.size > 0 && item.size < 1048576
                ? `${(item.size / 1024).toFixed(1)} KB`
                : item.size > 0
                  ? `${(item.size / 1048576).toFixed(1)} MB`
                  : "";
            return (
              <li
                key={item.id ?? i}
                data-status={status}
                className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5 text-xs"
              >
                <FileIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate">{item.name}</span>
                {sizeLabel ? <span className="text-muted-foreground">{sizeLabel}</span> : null}
                {status === "uploading" ? (
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <LoaderCircleIcon className="size-3.5 animate-spin" aria-hidden="true" />
                    <span aria-live="polite">{item.percent ?? 0}%</span>
                  </span>
                ) : status === "done" ? (
                  <span className="text-success">已就绪</span>
                ) : status === "error" ? (
                  <span className="flex items-center gap-1 text-destructive">
                    <CircleAlertIcon className="size-3.5" aria-hidden="true" />
                    {item.error ?? "上传失败"}
                  </span>
                ) : null}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`移除 ${item.name}`}
                  onClick={() => onRemove?.(item, i)}
                  className="text-muted-foreground"
                >
                  <XIcon className="size-3.5" />
                </Button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  )
}

export { Uploader }