/**
 * BankImportDialog — 题目批量导入（task58，contract④，四步导入）
 *  0 上传/编辑：拖拽 .json 或粘贴 JSON 数组（items 元素 = ImportItemInput）
 *  1 校验/预览：POST import-preview（逐行校验不落库）→ 有效/无效计数 + 失败行定位
 *  2 导入进度：POST import-execute（幂等，重复 question_code 跳过）→ 进度推进
 *  3 结果报告：imported/skipped/failed + 逐条语义色 messages + 无效行回翻定位
 *  契约对齐：无独立进度端点，import-execute 同步返回全量结果；进度为前端过渡动画。
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileCheck2, FileUp, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Stepper, type StepperStep } from "@/components/ui/stepper";
import { Progress } from "@/components/ui/progress";
import { Uploader, type UploadItem } from "@/components/ui/uploader";
import { FieldRow, LoadingState, ErrorState } from "@/components/admin/controls";
import { cn } from "@/lib/utils";
import {
  importExecute,
  importPreview,
  resolveTypeId,
  listQuestionTypes,
  type ImportItemInput,
  type ImportPreviewResult,
  type ImportExecuteResult,
  type QuestionTypeOption,
} from "@/lib/api/admin/question-bank";

export interface BankImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bankId: number;
  bankName: string;
  onImported?: (result: ImportExecuteResult) => void;
}

/** 🎯 适配样例：4 行（1 有效单选择 + 1 重复编码应跳过 + 2 非法应失败），方便打靶 */
export const BANK_IMPORT_SAMPLE = `[
  { "question_code": "Q-IMPORT-001", "question_type_id": 1, "stem": "1 + 1 = ?", "options_json": [{ "label": "A", "content": "1" }, { "label": "B", "content": "2" }], "answer_text": "B", "analysis_text": "1+1=2" },
  { "question_code": "Q-IMPORT-002", "question_type_id": "fill_blank", "stem": "Python 单行注释符号是 ____", "answer_text": "#", "analysis_text": "使用 # 注释" },
  { "question_code": "Q-IMPORT-001", "question_type_id": 1, "stem": "重复编码（应跳过 skipped）", "answer_text": "A" },
  { "question_code": "", "question_type_id": 3, "stem": "缺少题目编码（应失败 failed）", "answer_text": "对" }
]`;

const STEP_TITLES = ["上传/编辑", "校验/预览", "导入进度", "结果报告"];

function parseSample(raw: string, types: QuestionTypeOption[]): {
  items: ImportItemInput[];
  error: string | null;
} {
  let arr: unknown;
  try {
    arr = JSON.parse(raw);
  } catch {
    return { items: [], error: "JSON 解析失败，请检查格式" };
  }
  if (!Array.isArray(arr)) {
    return { items: [], error: "上传内容必须是 JSON 数组（items 元素）" };
  }
  const items: ImportItemInput[] = [];
  for (const row of arr) {
    if (!row || typeof row !== "object") continue;
    const r = row as Record<string, unknown>;
    let typeId: number | null = null;
    const rawType = r.question_type_id;
    if (typeof rawType === "number") typeId = rawType;
    else if (typeof rawType === "string") typeId = resolveTypeId(rawType, types);
    items.push({
      question_code: typeof r.question_code === "string" ? r.question_code : "",
      question_type_id: typeId,
      stem: typeof r.stem === "string" ? r.stem : "",
      answer_text: typeof r.answer_text === "string" ? r.answer_text : "",
      analysis_text: typeof r.analysis_text === "string" ? r.analysis_text : undefined,
      options_json: Array.isArray(r.options_json)
        ? (r.options_json as Array<{ label: string; content: string }>)
        : undefined,
    });
  }
  return { items, error: null };
}

export function BankImportDialog({ open, onOpenChange, bankId, bankName, onImported }: BankImportDialogProps) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [raw, setRaw] = useState("");
  const [parsed, setParsed] = useState<ImportItemInput[] | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ImportPreviewResult | null>(null);
  const [result, setResult] = useState<ImportExecuteResult | null>(null);
  const [progress, setProgress] = useState(0);
  const [fileItems, setFileItems] = useState<UploadItem[]>([]);
  const doneRef = useRef(false);
  const [types, setTypes] = useState<QuestionTypeOption[]>([]);

  const previewMutation = useMutation({
    mutationFn: (items: ImportItemInput[]) => importPreview(bankId, items),
    onSuccess: (resp) => {
      setPreview(resp);
      setStep(1);
    },
  });

  const executeMutation = useMutation({
    mutationFn: (items: ImportItemInput[]) => importExecute(bankId, items),
    onSuccess: (resp) => {
      setResult(resp);
      setProgress(100);
      toast.success(`导入完成：成功 ${resp.imported} / 跳过 ${resp.skipped} / 失败 ${resp.failed}`);
      queryClient.invalidateQueries({ queryKey: ["admin", "question-banks"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "bank-questions"] });
      onImported?.(resp);
      doneRef.current = true;
    },
  });

  // 加载题型维表（供题型名称→id 归一）
  useEffect(() => {
    if (!open) return;
    let alive = true;
    listQuestionTypes()
      .then((t) => alive && setTypes(t))
      .catch(() => alive && setTypes([]));
    return () => {
      alive = false;
    };
  }, [open]);

  // 导入进度过渡动画：执行中递增至 90%，成功后由 onSuccess 置 100 并切到结果步
  useEffect(() => {
    if (!executeMutation.isPending && doneRef.current) return;
    if (!executeMutation.isPending) return;
    const timer = window.setInterval(() => {
      setProgress((p) => (p < 90 ? Math.min(90, p + 5) : p));
    }, 120);
    return () => window.clearInterval(timer);
  }, [executeMutation.isPending]);

  // 执行成功后停留约 600ms 展示 100% 再进入结果报告
  useEffect(() => {
    if (!executeMutation.isSuccess || !result) return;
    const t = window.setTimeout(() => setStep(3), 600);
    return () => window.clearTimeout(t);
  }, [executeMutation.isSuccess, result]);

  useEffect(() => {
    if (executeMutation.isSuccess) doneRef.current = true;
  }, [executeMutation.isSuccess]);

  // 关闭时复位
  function handleOpenChange(next: boolean) {
    if (!next) {
      setStep(0);
      setRaw("");
      setParsed(null);
      setParseError(null);
      setPreview(null);
      setResult(null);
      setProgress(0);
      setFileItems([]);
      doneRef.current = false;
    }
    onOpenChange(next);
  }

  // 步0 → 步1：解析 + 预览校验
  function goPreview() {
    const { items, error } = parseSample(raw, types);
    if (error) {
      setParseError(error);
      return;
    }
    if (items.length === 0) {
      setParseError("未解析到任何题目行");
      return;
    }
    setParseError(null);
    setParsed(items);
    setStep(1);
    previewMutation.mutate(items);
  }

  // 步1 → 步2：确认执行导入
  function goExecute() {
    if (!parsed) return;
    setStep(2);
    setProgress(8);
    executeMutation.mutate(parsed);
  }

  const steps: StepperStep[] = STEP_TITLES.map((title, i) => ({
    title,
    status: i < step ? "done" : i === step ? "current" : "todo",
  }));

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-xl max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileUp className="h-4 w-4 text-primary-soft-foreground" /> 批量导入题目
          </DialogTitle>
        </DialogHeader>

        <div className="rounded-xl border border-primary-border bg-primary-soft px-3 py-2 text-sm">
          目标题库：<span className="font-medium text-foreground">{bankName}</span>
          <span className="ml-1 text-muted-foreground">（bank_id = {bankId}）</span>
        </div>

        <Stepper steps={steps} />

        {step === 0 && (
          <div className="space-y-3">
            <Uploader
              accept=".json,application/json"
              multiple={false}
              maxSize={2 * 1024 * 1024}
              value={fileItems}
              onFiles={(files) => {
                const f = files[0];
                if (!f) return;
                setFileItems([{ name: f.name, size: f.size, status: "idle" }]);
                void f.text().then((text) => {
                  setRaw(text);
                  setFileItems([{ name: f.name, size: f.size, status: "done" }]);
                });
              }}
              onRemove={() => {
                setFileItems([]);
                setRaw("");
              }}
              label="拖拽 .json 题单到此处，或粘贴下方 JSON"
              hint="单文件 ≤ 2MB；元素字段对齐导入契约（question_code / question_type_id / stem / answer_text / analysis_text / options_json）"
            />
            <FieldRow id="bank-import-json" label="题目 JSON 数组" error={parseError ?? undefined}>
              <Textarea
                value={raw}
                onChange={(e) => {
                  setRaw(e.target.value);
                  if (parseError) setParseError(null);
                  if (fileItems.length) setFileItems([]);
                }}
                placeholder='[{"question_code":"Q-001","question_type_id":1,"stem":"...","answer_text":"B"}]'
                rows={8}
                className="font-mono text-xs"
              />
            </FieldRow>
            <Button type="button" variant="outline" size="sm" onClick={() => setRaw(BANK_IMPORT_SAMPLE)}>
              填充样例（含重复 + 非法各 1 条）
            </Button>
          </div>
        )}

        {step === 1 && (
          <div className="space-y-3">
            {previewMutation.isPending ? (
              <LoadingState label="逐行校验中…" />
            ) : previewMutation.isError ? (
              <ErrorState message={previewMutation.error instanceof Error ? previewMutation.error.message : "预览校验失败"} />
            ) : preview ? (
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span className="inline-flex items-center gap-1 text-foreground">
                    共 <b>{preview.total_rows}</b> 行
                  </span>
                  <span className="inline-flex items-center gap-1 text-success-foreground">
                    <CheckCircle2 className="h-4 w-4" /> 有效 {preview.valid_rows}
                  </span>
                  <span className="inline-flex items-center gap-1 text-warning-foreground">
                    <AlertTriangle className="h-4 w-4" /> 无效 {preview.invalid_rows}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">{preview.message}</p>

                {preview.invalid_rows > 0 && (
                  <div className="space-y-2">
                    <p className="text-sm font-medium text-foreground">无效行明细（可按行号定位修正后重试）</p>
                    <ul className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-border bg-muted/30 p-2 text-xs">
                      {preview.rows
                        .filter((r) => !r.valid)
                        .map((r) => (
                          <li key={r.row_index} className="flex items-start gap-2 text-muted-foreground">
                            <code className="shrink-0 font-mono text-warning-foreground">行 {r.row_index + 1}</code>
                            <span>{r.question_code ? <span className="font-mono">{r.question_code} · </span> : null}{r.errors.join("；")}</span>
                          </li>
                        ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>正在写入题库（幂等：重复 question_code 跳过）…</span>
              <span className="font-medium text-foreground">{progress}%</span>
            </div>
            <Progress value={progress} />
            {executeMutation.isError && (
              <ErrorState
                message={executeMutation.error instanceof Error ? executeMutation.error.message : "导入执行失败"}
                onRetry={() => goExecute()}
              />
            )}
          </div>
        )}

        {step === 3 && result && (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="inline-flex items-center gap-1 text-foreground">
                共 <b>{result.total}</b> 条
              </span>
              <span className="inline-flex items-center gap-1 text-success-foreground">
                <CheckCircle2 className="h-4 w-4" /> 导入 {result.imported}
              </span>
              <span className="inline-flex items-center gap-1 text-warning-foreground">
                <FileCheck2 className="h-4 w-4" /> 跳过 {result.skipped}
              </span>
              <span className="inline-flex items-center gap-1 text-destructive-foreground">
                <XCircle className="h-4 w-4" /> 失败 {result.failed}
              </span>
            </div>

            {result.messages.length > 0 && (
              <ul className="max-h-36 space-y-1 overflow-y-auto rounded-lg border border-border bg-muted/30 p-2 text-xs font-mono">
                {result.messages.map((m, i) => (
                  <li key={i} className={cn(messageToneCls(m))} title={m}>{m}</li>
                ))}
              </ul>
            )}

            {preview && preview.invalid_rows > 0 && (
              <div className="rounded-lg border border-border bg-muted/30 p-2">
                <p className="mb-1 text-xs text-muted-foreground">无效行定位（未入库，可按行号回翻原题单修正）</p>
                <ul className="max-h-28 space-y-0.5 overflow-y-auto text-xs">
                  {preview.rows
                    .filter((r) => !r.valid)
                    .map((r) => (
                      <li key={r.row_index} className="flex items-start gap-2 text-muted-foreground">
                        <code className="shrink-0 text-warning-foreground">行 {r.row_index + 1}</code>
                        <span>{r.errors.join("；")}</span>
                      </li>
                    ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {step === 0 && (
            <>
              <Button variant="outline" onClick={() => handleOpenChange(false)}>取消</Button>
              <Button onClick={goPreview} disabled={!raw.trim()}>
                下一步：校验预览
              </Button>
            </>
          )}
          {step === 1 && (
            <>
              <Button variant="outline" onClick={() => setStep(0)}>上一步</Button>
              <Button onClick={goExecute} disabled={previewMutation.isPending || !preview || preview.total_rows === 0}>
                确认导入 {preview ? `（${preview.valid_rows} 条有效）` : ""}
              </Button>
            </>
          )}
          {step === 2 && (
            <Button variant="outline" disabled={executeMutation.isPending}>导入中…</Button>
          )}
          {step === 3 && (
            <Button onClick={() => handleOpenChange(false)}>完成</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** messages 逐条语义色：skip/幂等跳过 → warning；fail/失败 → destructive；其余中性 */
function messageToneCls(m: string): string {
  if (m.includes("skip") || m.includes("跳过") || m.includes("重复")) return "text-warning-foreground";
  if (m.includes("fail") || m.includes("失败")) return "text-destructive-foreground";
  return "text-muted-foreground";
}