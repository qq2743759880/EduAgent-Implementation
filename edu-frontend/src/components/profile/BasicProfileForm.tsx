"use client";

import { useMemo } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, UserRound } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Form as FormProvider,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { http } from "@/lib/api-client";
import { useAuthStore, type UserInfo } from "@/lib/auth-client";
import { UpdateProfileSchema } from "@/lib/validators/profile-schemas";

const BasicSchema = UpdateProfileSchema.pick({ nickname: true, avatar: true }).strip();
type BasicInput = z.infer<typeof BasicSchema>;

/** PUT /api/users/me/profile 返回（拦截器已解包）：UserProfile 子集（edu-agent app/users/schemas.py） */
type PutProfileResp = { nickname?: string | null; avatar_url?: string | null };

export function BasicProfileForm() {
  const me: UserInfo | null = useAuthStore((s) => s.me);
  const queryClient = useQueryClient();

  const defaults: BasicInput = useMemo(
    () => ({
      nickname: me?.nickname || "",
      avatar: (me?.avatar as string | undefined) ?? "",
    }),
    [me],
  );

  const form = useForm<BasicInput>({
    resolver: zodResolver(BasicSchema),
    defaultValues: defaults,
    values: defaults,
    mode: "onTouched",
  });

  const mutation = useMutation({
    mutationKey: ["profile", "basic"],
    mutationFn: async (body: BasicInput) => {
      /* W-NEXT-FEBE-SCAN-002 断点根因修复：真实契约是 PUT /api/users/me/profile
       * （UserProfileUpdate 全 Optional，None=不改）；旧 PATCH /api/users/me 后端从未注册
       * （OpenAPI 实测 404 断点）。avatar 表单字段 → avatar_url 契约字段映射；空串=清空。 */
      const data = await http.put<PutProfileResp>("/api/users/me/profile", {
        nickname: body.nickname,
        avatar_url: body.avatar ?? null,
      });
      return { profile: (data ?? null) as PutProfileResp | null };
    },
    onSuccess: async (result) => {
      const { profile } = result;
      if (profile && (profile.nickname || profile.avatar_url)) {
        useAuthStore.getState().setAuth({
          token: useAuthStore.getState().token || "",
          tenantId: useAuthStore.getState().tenantId,
          me: {
            id: me?.id ?? "",
            nickname: profile.nickname ?? me?.nickname ?? "",
            email: me?.email || "",
            avatar: profile.avatar_url ?? me?.avatar ?? null,
            roles: me?.roles ?? [],
            tenantId: me?.tenantId ?? null,
          },
        });
      }
      await useAuthStore.getState().refreshMe().catch(() => undefined);
      await queryClient.invalidateQueries({ queryKey: ["auth"] });
      toast.success("已保存基本资料");
    },
  });

  const avatarWatch = useWatch({ control: form.control, name: "avatar" });
  const nicknameWatch = useWatch({ control: form.control, name: "nickname" });
  const avatarPreview = (avatarWatch as string) || me?.avatar || undefined;
  const initial = useMemo(() => {
    const n = ((nicknameWatch as string) || me?.nickname || "U").trim();
    return n.slice(0, 1).toUpperCase();
  }, [nicknameWatch, me?.nickname]);

  return (
    <FormProvider {...form}>
      <Card className="shadow-card border-border">
        <CardHeader>
          <CardTitle className="text-lg">基本资料</CardTitle>
          <CardDescription className="text-sm text-muted-foreground">
            修改昵称与头像，用于学习仪表盘、排行榜与徽章墙展示。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex flex-col sm:flex-row gap-6 items-start">
            <div className="flex flex-col items-center gap-2 shrink-0">
              <Avatar className="h-20 w-20 border-2 border-muted shadow-sm bg-muted">
                {avatarPreview ? <AvatarImage src={avatarPreview} alt={me?.nickname || "avatar"} /> : null}
                <AvatarFallback className="bg-gradient-to-br from-primary-deep to-primary text-primary-foreground text-xl font-semibold">
                  {initial || <UserRound className="h-6 w-6" />}
                </AvatarFallback>
              </Avatar>
              <p className="text-3xs text-muted-foreground max-w-[9rem] text-center leading-4">
                暂未开放上传；粘贴图片 URL 即可预览
              </p>
            </div>
            <form onSubmit={form.handleSubmit((v) => mutation.mutate(v))} className="flex-1 w-full space-y-5">
              <FormField
                control={form.control}
                name="nickname"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>昵称</FormLabel>
                    <FormControl>
                      <Input placeholder="2-32 字，中英文、数字均可" maxLength={32} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="avatar"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>头像 URL（可选）</FormLabel>
                    <FormControl>
                      <Input
                        type="url"
                        placeholder="https://.../avatar.png"
                        {...field}
                        value={(field.value as string) ?? ""}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="space-y-1">
                <Label className="text-muted-foreground">登录邮箱</Label>
                <Input value={me?.email || ""} disabled className="bg-muted/40" />
                <p className="text-xs text-muted-foreground pt-0.5">登录邮箱不可自行修改，如需变更请联系管理员。</p>
              </div>
            </form>
          </div>
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
            disabled={mutation.isPending || !form.formState.isDirty}
            className="bg-primary hover:bg-primary-strong text-primary-foreground"
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 保存中…
              </>
            ) : (
              "保存"
            )}
          </Button>
        </CardFooter>
      </Card>
    </FormProvider>
  );
}

export default BasicProfileForm;
