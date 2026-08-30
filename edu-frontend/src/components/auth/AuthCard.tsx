"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** 登录/注册通用外框：居中布局 + Logo + 标题 + 底部切换链接 */
export function AuthCard({
  title,
  subtitle,
  footerHint,
  footerLinkLabel,
  footerLinkHref,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  footerHint: string;
  footerLinkLabel: string;
  footerLinkHref: "/login" | "/register" | (string & {});
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "min-h-[calc(100vh-4rem)] w-full flex items-center justify-center px-4 py-10",
        "bg-gradient-to-br from-primary-soft via-white to-secondary",
        className,
      )}
    >
      <Card className="w-full max-w-md shadow-card border-border bg-card/90 backdrop-blur">
        <CardHeader className="space-y-2 text-center pb-2">
          <div className="mx-auto inline-flex items-center gap-2 rounded-2xl bg-gradient-to-br from-primary to-primary-deep px-4 py-2 shadow-sm">
            <span className="h-6 w-6 rounded-lg bg-white/15 border border-white/20" />
            <span className="text-white font-semibold tracking-wide">EduAgent</span>
          </div>
          <CardTitle className="text-2xl font-bold text-foreground pt-2">{title}</CardTitle>
          {subtitle ? (
            <CardDescription className="text-sm text-muted-foreground">{subtitle}</CardDescription>
          ) : null}
        </CardHeader>
        <CardContent className="pt-4">{children}</CardContent>
        <CardFooter className="pt-0 pb-6 flex items-center justify-center gap-1 text-sm text-muted-foreground">
          <span>{footerHint}</span>
          <Link
            href={footerLinkHref}
            className="font-medium text-primary hover:text-primary-strong underline-offset-4 hover:underline"
          >
            {footerLinkLabel}
          </Link>
        </CardFooter>
      </Card>
    </div>
  );
}

export default AuthCard;
