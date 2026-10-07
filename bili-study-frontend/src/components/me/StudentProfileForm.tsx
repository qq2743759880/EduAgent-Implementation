/**
 * 学员档案表单（task54 me）：读 GET /api/users/me/student-profile 回显，
 * 保存走 PUT /api/users/me/profile（UserProfile 表，可见字段仅 school_name → 学校）。
 * 契约⑤ 现状：student_profile 表无对外写入端点，identity/goal/education/grade/industry/position/years
 * 仅展示回显（设计签收字段），持久化缺口在 handoff 标注。保存成功 → sonner toast。
 */
"use client";
import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { getStudentProfile, updateProfile, type StudentProfileRow } from "@/lib/api/me";
import { ErrorState } from "@/components/ui/error-state";

const IDENTITY_OPTIONS = ["在校学生", "在职工作者", "自由职业者", "其他"];
const GOAL_OPTIONS = ["编程 / 技术发展", "升学备考", "职业转型", "兴趣拓展"];
const EDUCATION_OPTIONS = ["小学", "初中", "高中", "大专", "本科", "硕士及以上"];
const GRADE_OPTIONS = [
  "一年级",
  "二年级",
  "三年级",
  "四年级",
  "五年级",
  "六年级",
  "初中",
  "高中一年级",
  "高中二年级",
  "高中三年级",
  "已毕业",
];
const YEARS_OPTIONS = ["0 年", "1-3 年", "3-5 年", "5-10 年", "10 年以上"];

export function StudentProfileForm() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["me", "student-profile"] as const,
    queryFn: getStudentProfile,
    staleTime: 60_000,
  });

  if (isLoading && !data) return <ProfileFormSkeleton />;
  if (isError && !data) {
    return (
      <ErrorState
        title="档案加载失败"
        message="网络开小差了，请稍后重试。"
        retry={refetch}
        retryLabel="重试"
      />
    );
  }
  if (!data) return null;

  // 数据就绪后再挂载表单，用 data 惰性初始化各字段（避免 effect 内 setState，符合 RSC set-state-in-effect 红线）
  return <ProfileFormInner data={data as StudentProfileRow} />;
}

function ProfileFormInner({ data }: { data: StudentProfileRow }) {
  const yearsInit =
    typeof data.years_of_experience === "string" &&
    YEARS_OPTIONS.includes(data.years_of_experience)
      ? data.years_of_experience
      : YEARS_OPTIONS[1];

  const [identity, setIdentity] = useState(IDENTITY_OPTIONS[1]);
  const [goal, setGoal] = useState(GOAL_OPTIONS[0]);
  const [education, setEducation] = useState(EDUCATION_OPTIONS[4]);
  const [grade, setGrade] = useState(GRADE_OPTIONS[10]);
  const [school, setSchool] = useState(typeof data.school_name === "string" ? data.school_name : "");
  const [industry, setIndustry] = useState(typeof data.industry_name === "string" ? data.industry_name : "");
  const [position, setPosition] = useState(typeof data.job_role_name === "string" ? data.job_role_name : "");
  const [years, setYears] = useState(yearsInit);
  // learner_identity_id / learning_goal_id / education_level_id / grade_id 为 FK 数字，
  // 无 dim 映射端点无法还原展示名，保留设计默认项（契约缺口见 handoff）——不伪造回显。

  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: () => updateProfile({ school_name: school.trim() || undefined }),
    onSuccess: () => {
      toast.success("档案已保存");
      void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: () => toast.error("保存失败，请稍后重试"),
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl border-[3px] border-foreground bg-white p-5 shadow-[0_4px_0_rgba(31,31,31,0.14)]"
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="学习身份" required><Select value={identity} onChange={setIdentity} options={IDENTITY_OPTIONS} /></Field>
        <Field label="学习目标" required><Select value={goal} onChange={setGoal} options={GOAL_OPTIONS} /></Field>
        <Field label="最高学历"><Select value={education} onChange={setEducation} options={EDUCATION_OPTIONS} /></Field>
        <Field label="当前年级"><Select value={grade} onChange={setGrade} options={GRADE_OPTIONS} /></Field>
        <Field label="所在学校">
          <TextInput value={school} onChange={setSchool} placeholder="请输入学校名称" />
        </Field>
        <Field label="所在行业">
          <TextInput value={industry} onChange={setIndustry} placeholder="请输入所在行业" />
        </Field>
        <Field label="当前岗位">
          <TextInput value={position} onChange={setPosition} placeholder="请输入岗位" />
        </Field>
        <Field label="工作年限"><Select value={years} onChange={setYears} options={YEARS_OPTIONS} /></Field>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-end gap-3">
        <span className="text-xs font-semibold text-muted-foreground">
          学校等可写字段经 PUT /me/profile 保存；身份 / 目标 / 学历 / 年级等展示回显
        </span>
        <button
          type="submit"
          disabled={save.isPending}
          className="inline-flex items-center gap-2 rounded-xl border-[3px] border-foreground bg-candy-green px-5 py-2 text-sm font-extrabold text-white shadow-[0_3px_0_rgba(61,153,0,0.9)] transition-transform active:translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : null}
          {save.isPending ? "保存中…" : "保存档案"}
        </button>
      </div>
    </form>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-extrabold text-foreground">
        {label}
        {required ? <span className="text-destructive"> *</span> : null}
      </span>
      {children}
    </label>
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-10 rounded-xl border-[2px] border-foreground bg-white px-3 text-sm font-semibold text-foreground outline-none transition-shadow focus-visible:ring-3 focus-visible:ring-candy-purple"
    >
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="h-10 rounded-xl border-[2px] border-foreground bg-white px-3 text-sm font-semibold text-foreground outline-none transition-shadow placeholder:font-medium placeholder:text-muted-foreground focus-visible:ring-3 focus-visible:ring-candy-purple"
    />
  );
}

function ProfileFormSkeleton() {
  return (
    <div
      className="grid grid-cols-1 gap-4 rounded-2xl border-[3px] border-border bg-white p-5 sm:grid-cols-2"
      role="status"
      aria-label="正在加载学员档案…"
    >
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="space-y-1.5">
          <div className="h-3 w-16 animate-pulse rounded bg-candy-bg" />
          <div className="h-10 animate-pulse rounded-xl bg-candy-bg" />
        </div>
      ))}
    </div>
  );
}