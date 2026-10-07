/**
 * /me 个人中心（task54）：头像头卡 + 数据概览 4 StatCard + 功能入口 7 行 + 学员档案表单。
 * 板块顺序按 HTML 签收：个人资料 → 数据概览 → 功能入口 → 学员档案。
 */
import type { LucideIcon } from "lucide-react";
import { BarChart3, Compass, PenLine } from "lucide-react";
import { ProtectedRoute } from "@/lib/protected-route";
import { MeHeader } from "@/components/me/MeHeader";
import { StatCards } from "@/components/me/StatCards";
import { MeNavList } from "@/components/me/MeNavList";
import { StudentProfileForm } from "@/components/me/StudentProfileForm";

export default function MePage() {
  return (
    <ProtectedRoute>
      <MePageInner />
    </ProtectedRoute>
  );
}

export function MePageInner() {
  return (
    <div className="bg-candy-bg">
      <main className="mx-auto w-full max-w-5xl space-y-6 px-4 py-6 md:px-6">
        {/* 1. 个人资料 */}
        <MeHeader />

        {/* 2. 数据概览 */}
        <section aria-labelledby="stats-sec">
          <SectionTitle
            Icon={BarChart3}
            tone="bg-candy-blue"
            title="数据概览"
            subtitle="学习时长 / 完成课次 来自 learning-summary · 积分 / 等级 来自 gamification"
            id="stats-sec"
          />
          <div className="mt-3">
            <StatCards />
          </div>
        </section>

        {/* 3. 功能入口 */}
        <section aria-labelledby="nav-sec">
          <SectionTitle
            Icon={Compass}
            tone="bg-candy-purple"
            title="功能入口"
            subtitle="我的订单 / 优惠券 / 收藏 / 班次 / 退款 / 工单 / 错题本（J20）"
            id="nav-sec"
          />
          <div className="mt-3">
            <MeNavList labelledby="nav-sec" />
          </div>
        </section>

        {/* 4. 学员档案 */}
        <section aria-labelledby="profile-sec">
          <SectionTitle
            Icon={PenLine}
            tone="bg-candy-green"
            title="学员档案"
            subtitle="身份 / 目标 / 学历 / 年级 / 学校 / 行业 / 岗位 / 工作年限"
            id="profile-sec"
          />
          <div className="mt-3">
            <StudentProfileForm />
          </div>
        </section>
      </main>
    </div>
  );
}

function SectionTitle({
  Icon,
  tone,
  title,
  subtitle,
  id,
}: {
  Icon: LucideIcon;
  tone: string;
  title: string;
  subtitle?: string;
  id?: string;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2.5">
      <span
        className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl border-[3px] border-foreground text-white shadow-[0_3px_0_color-mix(in_oklch,var(--foreground),transparent_82%)] ${tone}`}
        aria-hidden="true"
      >
        <Icon className="h-5 w-5" />
      </span>
      <div className="min-w-0">
        <h2 id={id} className="text-base font-black text-foreground">
          {title}
        </h2>
        {subtitle ? <p className="text-xs font-semibold text-muted-foreground">{subtitle}</p> : null}
      </div>
    </div>
  );
}
