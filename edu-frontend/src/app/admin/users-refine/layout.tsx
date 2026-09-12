import type { Metadata } from "next";

// 路由级 title（与 (admin)/admin/users/layout.tsx 同约定）
export const metadata: Metadata = {
  title: "用户管理 Refine 版 - EduAgent",
};

export default function UsersRefineLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
