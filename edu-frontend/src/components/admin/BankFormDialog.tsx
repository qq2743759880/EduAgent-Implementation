/**
 * BankFormDialog — 题库新建/编辑（task58，contract④）
 *  - create：POST /api/admin/questions/banks（institution_id + bank_code + bank_name 必填）
 *  - edit：PATCH /api/admin/questions/banks/{id}（仅提交 Update 允许字段；bank_code 唯一机构内约束）
 *  - 唯一约束冲突（40921 bank_code 重复）→ 行内错误提示，不回退全链路 toast
 *  - 写操作 useMutation + onError 分支（40921 行内 / 其余全局 toast，R-7）
 */
"use client";

import { useId, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderPlus, PencilLine } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FieldRow } from "@/components/admin/controls";
import { createBank, updateBank, toAdminApiError, type QuestionBank } from "@/lib/api/admin/question-bank";

export interface BankFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 传 bank 为编辑模式，否则新建 */
  bank?: QuestionBank | null;
  onSaved?: (bankId: number) => void;
}

export function BankFormDialog({ open, onOpenChange, bank, onSaved }: BankFormDialogProps) {
  const uuid = useId();
  const queryClient = useQueryClient();
  const editing = Boolean(bank);

  const [form, setForm] = useState({
    institution_id: bank ? String(bank.institution_id) : "",
    bank_code: bank?.bank_code ?? "",
    bank_name: bank?.bank_name ?? "",
    description: bank?.description ?? "",
  });
  const [serverError, setServerError] = useState<string | null>(null);

  function patch(key: keyof typeof form, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
    if (serverError) setServerError(null);
  }

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = {
        institution_id: Number(form.institution_id),
        bank_code: form.bank_code.trim(),
        bank_name: form.bank_name.trim(),
        description: form.description.trim() || undefined,
      };
      return editing && bank ? updateBank(bank.id, payload) : createBank(payload);
    },
    onSuccess: (resp) => {
      toast.success(editing ? "题库已更新" : "题库已创建");
      queryClient.invalidateQueries({ queryKey: ["admin", "question-banks"] });
      const id = "id" in resp ? resp.id : 0;
      handleOpenChange(false);
      onSaved?.(id || (bank?.id ?? 0));
    },
    onError: (err) => {
      const apiErr = toAdminApiError(err);
      // 40921 = bank_code 唯一冲突 → 行内错误；其余走全局 MutationCache toast
      if (apiErr?.code === 40921) {
        setServerError("题库编码已存在（同机构下必须唯一，40921）");
      }
    },
  });

  function handleOpenChange(next: boolean) {
    if (!next) {
      setServerError(null);
    }
    onOpenChange(next);
  }

  const canSubmit =
    form.institution_id !== "" &&
    Number(form.institution_id) > 0 &&
    form.bank_code.trim() !== "" &&
    form.bank_name.trim() !== "";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {editing ? <PencilLine className="h-4 w-4 text-primary-soft-foreground" /> : <FolderPlus className="h-4 w-4 text-primary-soft-foreground" />}
            {editing ? "编辑题库" : "新建题库"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <FieldRow id={`${uuid}-institution`} label="机构 ID" required hint="多校区题库归属当前机构">
              <Input
                type="number"
                min={1}
                value={form.institution_id}
                onChange={(e) => patch("institution_id", e.target.value)}
                placeholder="如：1"
              />
            </FieldRow>
            <FieldRow id={`${uuid}-code`} label="题库编码" required error={serverError ?? undefined} hint="同机构内唯一，如 MATH-101">
              <Input
                value={form.bank_code}
                onChange={(e) => patch("bank_code", e.target.value)}
                placeholder="如：PY-001"
              />
            </FieldRow>
          </div>
          <FieldRow id={`${uuid}-name`} label="题库名称" required>
            <Input
              value={form.bank_name}
              onChange={(e) => patch("bank_name", e.target.value)}
              placeholder="如：Python 基础编程题库"
            />
          </FieldRow>
          <FieldRow id={`${uuid}-desc`} label="题库描述（可选）">
            <Textarea
              value={form.description}
              onChange={(e) => patch("description", e.target.value)}
              rows={2}
              placeholder="简述题库覆盖的知识点范围"
            />
          </FieldRow>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>取消</Button>
          <Button onClick={() => mutation.mutate()} disabled={!canSubmit || mutation.isPending}>
            {mutation.isPending ? "保存中…" : editing ? "保存修改" : "创建题库"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}