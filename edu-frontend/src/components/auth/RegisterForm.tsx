"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import {
  RegisterSchema,
  type RegisterInput,
} from "@/lib/validators/auth-schemas";

export function RegisterForm() {
  const router = useRouter();

  const form = useForm<RegisterInput>({
    resolver: zodResolver(RegisterSchema),
    defaultValues: {
      username: "",
      nickname: "",
      email: "",
      password: "",
      confirmPassword: "",
    },
    mode: "onTouched",
  });

  const [showPwd, setShowPwd] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const passwordType = useMemo(() => (showPwd ? "text" : "password"), [showPwd]);
  const confirmType = useMemo(() => (showConfirm ? "text" : "password"), [showConfirm]);

  const onSubmit = form.handleSubmit(async (data) => {
    try {
      const resp = await useAuthStore.getState().register(data);
      const alreadyHasToken = Boolean(useAuthStore.getState().token);
      if (resp.ok === false && !alreadyHasToken) {
        toast.success("注册成功，请登录", { description: "即将跳转到登录页" });
        const dest = new URL("/login", typeof window === "undefined" ? "http://localhost" : window.location.origin);
        if (data.email) dest.searchParams.set("email", data.email);
        router.replace(dest.pathname + dest.search);
        return;
      }
      toast.success("注册成功", { description: alreadyHasToken ? "已自动登录，进入仪表盘" : "正在跳转登录" });
      if (alreadyHasToken) {
        router.replace("/dashboard");
      } else {
        const dest = new URL("/login", typeof window === "undefined" ? "http://localhost" : window.location.origin);
        if (data.email) dest.searchParams.set("email", data.email);
        router.replace(dest.pathname + dest.search);
      }
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        if (/邮箱|email|已经|exist|duplicate/i.test(err.message)) {
          const msg = /已注册|已经存在|exist|duplicate/i.test(err.message)
            ? `${err.message || "邮箱已被注册"}，请直接登录`
            : err.message || "邮箱已被注册";
          form.setError("email", { type: "custom", message: msg });
          return;
        }
        if (/昵称|nickname/i.test(err.message)) {
          form.setError("nickname", { type: "custom", message: err.message });
          return;
        }
        if (/账号|username|登录名|identifier/i.test(err.message)) {
          form.setError("username", { type: "custom", message: err.message || "该账号已被占用" });
          return;
        }
        toast.error(err.message || "注册失败");
        return;
      }
      toast.error(err instanceof Error ? err.message : "注册失败，请稍后重试");
    }
  });

  return (
    <FormProvider {...form}>
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <FormField
          control={form.control}
          name="username"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                账号（登录用）
              </FormLabel>
              <FormControl>
                <Input
                  autoComplete="username"
                  inputMode="text"
                  placeholder="3-20 位，字母开头，可含数字、下划线、短横线"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="nickname"
          render={({ field }) => (
            <FormItem>
              <FormLabel>昵称</FormLabel>
              <FormControl>
                <Input autoComplete="nickname" placeholder="2-32 字，中英文均可" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>邮箱</FormLabel>
              <FormControl>
                <Input
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
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
                    type={passwordType}
                    autoComplete="new-password"
                    placeholder="6 位以上，不含中文"
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
        <FormField
          control={form.control}
          name="confirmPassword"
          render={({ field }) => (
            <FormItem>
              <FormLabel>确认密码</FormLabel>
              <FormControl>
                <div className="relative">
                  <Input
                    type={confirmType}
                    autoComplete="new-password"
                    placeholder="再次输入密码"
                    {...field}
                    className="pr-11"
                  />
                  <button
                    type="button"
                    aria-label={showConfirm ? "隐藏密码" : "显示密码"}
                    tabIndex={-1}
                    className="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600"
                    onClick={() => setShowConfirm((v) => !v)}
                  >
                    {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <Button
          type="submit"
          className="w-full bg-gradient-to-br from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white shadow-md h-11 mt-2"
          disabled={form.formState.isSubmitting}
        >
          {form.formState.isSubmitting ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 创建账号中…
            </>
          ) : (
            "创建账号"
          )}
        </Button>

        <p className="text-[11px] leading-5 text-slate-500 pt-1">
          点击「创建账号」即代表你同意 EduAgent 的服务条款与隐私政策。账号仅用于存储个人学习进度与徽章。
        </p>
      </form>
    </FormProvider>
  );
}

export default RegisterForm;
