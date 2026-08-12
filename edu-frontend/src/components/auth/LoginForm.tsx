"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Form as FormProvider } from "@/components/ui/form";
import { useAuthStore } from "@/lib/auth-client";
import { ApiError } from "@/lib/api-client";
import { LoginSchema, type LoginInput } from "@/lib/validators/auth-schemas";

export function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const redirect = useMemo(() => {
    const r = search?.get("redirect")?.trim();
    return r && /^\/[A-Za-z0-9?=&/%\-_@+.~#]*$/.test(r) ? r : "/dashboard";
  }, [search]);

  const form = useForm<LoginInput>({
    resolver: zodResolver(LoginSchema),
    defaultValues: { identifier: "", password: "" },
    mode: "onTouched",
  });

  const [showPwd, setShowPwd] = useState(false);
  const prefilledEmail = search?.get("email")?.trim();
  const prefilledAccount = search?.get("username")?.trim();

  useEffect(() => {
    const fallback = (prefilledAccount || prefilledEmail || "").trim();
    if (fallback) {
      form.setValue("identifier", fallback, { shouldValidate: false });
    }
  }, [prefilledAccount, prefilledEmail, form]);

  const onSubmit = form.handleSubmit(async (data) => {
    try {
      await useAuthStore.getState().login(data);
      toast.success("登录成功", { description: "正在跳转学习仪表盘…" });
      router.replace(redirect);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        /*
          表单级横幅（root.server）场景：
          - 401：账号/密码错误 / 凭证无效
          - 403：账号被禁用（AUTH_USER_DISABLED）—— 用户需要在原地看到原因
          - message 命中凭证类关键字
          其余一律 toast.error 全局提示（500 / 网络错误等）
        */
        const credentialPattern = /credential|密码|邮箱|账号|用户不存在|identifier|禁用|已被停用|disabled/i;
        const shouldShowAsBanner =
          err.status === 401 || err.status === 403 || credentialPattern.test(err.message);
        if (shouldShowAsBanner) {
          form.setError("root.server", {
            type: "custom",
            message: err.message || (err.status === 403 ? "账号已被禁用，请联系管理员" : "账号/邮箱或密码错误"),
          });
          return;
        }
        toast.error(err.message || "登录失败");
        return;
      }
      toast.error(err instanceof Error ? err.message : "登录失败，请稍后重试");
    }
  });

  return (
    <FormProvider {...form}>
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <FormField
          control={form.control}
          name="identifier"
          render={({ field }) => (
            <FormItem>
              <FormLabel>账号 / 邮箱</FormLabel>
              <FormControl>
                <Input
                  autoComplete="username"
                  placeholder="输入账号，或邮箱（含 @）"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>密码</FormLabel>
              <FormControl>
                <div className="relative">
                  <Input
                    type={showPwd ? "text" : "password"}
                    autoComplete="current-password"
                    placeholder="6 位以上"
                    {...field}
                    className="pr-11"
                  />
                  <button
                    type="button"
                    aria-label={showPwd ? "隐藏密码" : "显示密码"}
                    tabIndex={-1}
                    className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600"
                    onClick={() => setShowPwd((v) => !v)}
                  >
                    {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {form.formState.errors.root?.server ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-600">
            {form.formState.errors.root.server.message}
          </div>
        ) : null}

        <div className="flex items-center justify-between pt-1">
          <Label className="text-xs text-slate-500 inline-flex items-center gap-2 select-none">
            <input
              type="checkbox"
              defaultChecked
              className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
            />
            记住我
          </Label>
          <span className="text-xs text-slate-500">
            忘记密码？请联系管理员
          </span>
        </div>

        <Button
          type="submit"
          className="w-full bg-gradient-to-br from-indigo-600 to-sky-600 hover:from-indigo-700 hover:to-sky-700 text-white shadow-md h-11"
          disabled={form.formState.isSubmitting}
        >
          {form.formState.isSubmitting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 登录中…
            </>
          ) : (
            "登录"
          )}
        </Button>
      </form>
    </FormProvider>
  );
}

export default LoginForm;
