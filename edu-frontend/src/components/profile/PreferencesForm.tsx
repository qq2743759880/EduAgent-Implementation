"use client";

import { useEffect, useMemo } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Target } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  Form as FormProvider,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { SubjectMultiSelect } from "@/components/profile/SubjectMultiSelect";
import { api } from "@/lib/api-client";
import { useAuthStore, type UserInfo } from "@/lib/auth-client";
import { UpdateProfileSchema, type SubjectKey } from "@/lib/validators/profile-schemas";

const PrefsSchema = UpdateProfileSchema.pick({
  learningGoal: true,
  subjectPreferences: true,
}).strip();

/**
 * zod 的 .default([]) 让「输入」与「输出」类型不同：
 *   input  → subjectPreferences 可省略
 *   output → subjectPreferences 必填（默认 []）
 * useForm 必须显式区分这两个泛型，否则 zodResolver 的类型无法对齐。
 */
type PrefsInput = z.input<typeof PrefsSchema>;
type PrefsOutput = z.output<typeof PrefsSchema>;

const MAX_GOAL = 500;

type PatchResp = { ok?: boolean; updated?: unknown } | Record<string, unknown>;

function unwrapPatchOk(raw: unknown): PatchResp | null {
  if (raw && typeof raw === "object") {
    const obj = raw as { data?: unknown } | PatchResp;
    if ("data" in obj && obj.data && typeof obj.data === "object") {
      return obj.data as PatchResp;
    }
    return obj as PatchResp;
  }
  return null;
}

export function PreferencesForm() {
  const queryClient = useQueryClient();
  const me = useAuthStore((s) => s.me);

  const defaults: PrefsInput = useMemo<PrefsInput>(() => {
    const anyMe = me as (UserInfoLike | null) | undefined;
    return {
      learningGoal: (anyMe?.learningGoal as string) ?? "",
      subjectPreferences: (Array.isArray(anyMe?.subjectPreferences)
        ? (anyMe!.subjectPreferences as SubjectKey[])
        : []) ?? [],
    };
  }, [me]);

  const form = useForm<PrefsInput, unknown, PrefsOutput>({
    resolver: zodResolver(PrefsSchema),
    defaultValues: defaults,
    values: defaults,
    mode: "onTouched",
  });

  /* me 首次加载后同步到表单（避免默认空，编辑体验更自然） */
  useEffect(() => {
    if (!me) return;
    form.reset(defaults, { keepDirtyValues: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.id]);

  const mutation = useMutation({
    mutationKey: ["profile", "preferences"],
    mutationFn: async (body: PrefsInput) => {
      const patchBody = {
        learningGoal: body.learningGoal || "",
        subjectPreferences: body.subjectPreferences || [],
      };
      const resp = await api.patch("/api/users/me", patchBody);
      return { ok: unwrapPatchOk(resp.data) };
    },
    onSuccess: async () => {
      await useAuthStore.getState().refreshMe().catch(() => undefined);
      await queryClient.invalidateQueries({ queryKey: ["profile", "auth"] });
      toast.success("偏好设置已保存");
    },
  });

  const goal = useWatch({ control: form.control, name: "learningGoal" });
  const subjects = useWatch({ control: form.control, name: "subjectPreferences" });
  const goalLen = ((goal as string) || "").length;
  const overLimit = goalLen > MAX_GOAL;
  const subjectCount = Array.isArray(subjects) ? subjects.length : 0;

  return (
    <FormProvider {...form}>
      <Card className="shadow-card border-border">
        <CardHeader>
          <CardTitle className="text-lg">偏好设置</CardTitle>
          <CardDescription className="text-sm text-muted-foreground">
            设置你的学习目标与感兴趣的学科，AI 将据此推荐更贴合的学习路径与练习。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-8">
          <FormField
            control={form.control}
            name="subjectPreferences"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="flex items-center gap-1.5">
                  <Target className="h-4 w-4 text-primary" />
                  学科偏好 <span className="font-normal text-muted-foreground text-xs ml-1">（可多选，至少 0 个）</span>
                </FormLabel>
                <FormControl>
                  <SubjectMultiSelect
                    value={field.value as SubjectKey[]}
                    onChange={field.onChange}
                    onBlur={field.onBlur}
                    disabled={mutation.isPending}
                  />
                </FormControl>
                <p className="text-xs text-muted-foreground -mt-1">
                  已选 {subjectCount} 个。当前学科覆盖：英语 · 编程 · 数学 · 语文 · 物理
                </p>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="learningGoal"
            render={({ field }) => (
              <FormItem>
                <FormLabel>学习目标（可选）</FormLabel>
                <FormControl>
                  <Textarea
                    placeholder="例如：3 个月内把高考英语词汇过一轮，每天坚持 30 分钟背单词 + 1 篇阅读理解。"
                    maxLength={MAX_GOAL + 120}
                    rows={5}
                    className="resize-y leading-7"
                    {...field}
                    value={(field.value as string) ?? ""}
                  />
                </FormControl>
                <div className="flex items-center justify-between">
                  <FormMessage />
                  <span
                    className={
                      "text-xs tabular-nums " +
                      (overLimit ? "text-destructive font-semibold" : "text-muted-foreground")
                    }
                  >
                    {goalLen} / {MAX_GOAL}
                  </span>
                </div>
              </FormItem>
            )}
          />
        </CardContent>
        <CardFooter className="justify-end gap-2 border-t border-border bg-muted/40 rounded-b-xl px-6 py-4">
          <Button
            type="button"
            variant="ghost"
            disabled={mutation.isPending}
            onClick={() => form.reset(defaults)}
          >
            撤销修改
          </Button>
          <Button
            type="button"
            onClick={() => form.handleSubmit((v) => mutation.mutate(v))()}
            disabled={mutation.isPending || !form.formState.isDirty || overLimit}
            className="bg-primary hover:bg-primary-strong text-primary-foreground"
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 保存中…
              </>
            ) : (
              "保存偏好"
            )}
          </Button>
        </CardFooter>
      </Card>
    </FormProvider>
  );
}

type UserInfoLike = {
  learningGoal?: unknown;
  subjectPreferences?: unknown;
};

export default PreferencesForm;
