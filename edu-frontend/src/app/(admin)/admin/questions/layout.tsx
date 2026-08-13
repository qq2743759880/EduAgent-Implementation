import type { Metadata } from "next";

// a11y #9：管理端各页 title 随路由变化（客户端页面无法 export metadata，由路由级 layout 提供）
export const metadata: Metadata = {
  title: "题库管理 - EduAgent",
};

export default function QuestionsLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
