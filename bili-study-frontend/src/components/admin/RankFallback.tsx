/**
 * RankFallback — 管理端仪表盘：热门课程榜契约缺口占位卡（task55）
 * - 契约缺口（禁 MOCK）：订单数/营收/热门课程榜 无管理端全局聚合端点
 *   （trade/order|payment|refund 均为用户本人视角 CurrentUser）
 * - 在聚合端点就绪前不伪造数据，以占位卡呈现「待后端 task70~91 聚合端点」。
 * - 与 HTML 效果图 admin-dashboard.html 的【热门课程榜(契约缺口占位)】区块一致。
 */
"use client";

import { Trophy } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export function RankFallback() {
  return (
    <Card className="bg-white">
      <CardContent className="flex items-center gap-3 py-4">
        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-candy-orange/10 text-candy-orange">
          <Trophy className="h-4 w-4" />
        </span>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-foreground">热门课程榜</div>
          <p className="mt-0.5 text-sm-table text-muted-foreground">
            依赖管理端全局交易聚合端点。后端当前仅提供用户本人视角的交易接口，无 admin 全局聚合端点，
            本区块在端点就绪前不伪造数据。
          </p>
          <span className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-candy-orange/10 px-2.5 py-0.5 text-3xs font-medium text-candy-orange">
            ⏳ 待后端 task70~91 提供 GET /api/admin/trade/overview
          </span>
        </div>
      </CardContent>
    </Card>
  );
}