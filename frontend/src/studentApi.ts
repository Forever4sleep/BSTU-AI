import { buildApiUrl } from "./api";
import { clearStudentSession, getStudentAccessToken, setStudentSession } from "./studentAccessKey";
import { unifiedSessionLogin } from "./unifiedAuthApi";

export type StudentMe = {
  id: string;
  username: string;
  full_name: string;
  study_group_id: string | null;
  study_group_title: string | null;
  /** Есть сохранённый файл — грузится отдельно с ``GET /api/public/me/avatar`` (Bearer). */
  has_avatar: boolean;
};

export type StudentCourseRow = {
  /** UUID курса; если бэкенд старый — может отсутствовать (тогда для чата передаём slug). */
  id?: string;
  slug: string;
  title: string;
  /** ФИО преподавателя (fallback — отображаемое имя). */
  instructor_name?: string;
  visibility_mode: string;
  chat_assistant_enabled?: boolean;
  via_catalog?: boolean;
  via_group_policy?: boolean;
};

/** Резерв: тот же сценарий, что общий вход, но ошибка если логин не студенческий (см. ``POST /api/public/session/login``). */
export async function studentLogin(username: string, password: string): Promise<void> {
  const out = await unifiedSessionLogin(username, password);
  if (out.role !== "student") {
    throw new Error(`По этим данным вы не студент (роль «${out.role}» — используйте общую страницу входа).`);
  }
  const tok = out.access_token.trim();
  const key = (out.student_access_key ?? "").trim();
  if (!tok) throw new Error("Пустой токен доступа.");
  setStudentSession(tok, key);
}

export async function fetchStudentMe(): Promise<StudentMe> {
  const t = getStudentAccessToken().trim();
  if (!t) throw new Error("Не выполнен вход.");
  const r = await fetch(buildApiUrl("/api/public/me"), { headers: { Authorization: `Bearer ${t}` } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  const raw = (await r.json()) as Partial<StudentMe>;
  return { ...(raw as StudentMe), has_avatar: Boolean(raw.has_avatar) };
}

export async function changeStudentPassword(body: {
  current_password: string;
  new_password: string;
}): Promise<void> {
  const t = getStudentAccessToken().trim();
  if (!t) throw new Error("Не выполнен вход.");
  const r = await fetch(buildApiUrl("/api/public/me/password"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}` },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text();
    try {
      const j = JSON.parse(text) as { detail?: string | { msg?: string }[] };
      const d = j.detail;
      if (typeof d === "string" && d.trim()) throw new Error(d);
      if (Array.isArray(d) && d[0]?.msg) throw new Error(d[0].msg);
    } catch (parseErr) {
      if (parseErr instanceof Error && parseErr.message && !parseErr.message.startsWith("Unexpected")) {
        throw parseErr;
      }
    }
    if (r.status === 401 || text.includes("Неверный текущий пароль")) {
      throw new Error("Неверный текущий пароль.");
    }
    if (r.status === 400 && text.includes("совпадает")) {
      throw new Error("Новый пароль должен отличаться от текущего.");
    }
    throw new Error(`${r.status} ${text}`);
  }
}

export async function patchStudentProfile(body: { full_name: string }): Promise<StudentMe> {
  const t = getStudentAccessToken().trim();
  if (!t) throw new Error("Не выполнен вход студента.");
  const r = await fetch(buildApiUrl("/api/public/me"), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${t}` },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  const raw = (await r.json()) as Partial<StudentMe>;
  return { ...(raw as StudentMe), has_avatar: Boolean(raw.has_avatar) };
}

export async function uploadStudentAvatar(file: File): Promise<StudentMe> {
  const t = getStudentAccessToken().trim();
  if (!t) throw new Error("Не выполнен вход студента.");
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(buildApiUrl("/api/public/me/avatar"), {
    method: "POST",
    headers: { Authorization: `Bearer ${t}` },
    body: fd,
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  const raw = (await r.json()) as Partial<StudentMe>;
  return { ...(raw as StudentMe), has_avatar: Boolean(raw.has_avatar) };
}

export async function deleteStudentAvatar(): Promise<StudentMe> {
  const t = getStudentAccessToken().trim();
  if (!t) throw new Error("Не выполнен вход студента.");
  const r = await fetch(buildApiUrl("/api/public/me/avatar"), {
    method: "DELETE",
    headers: { Authorization: `Bearer ${t}` },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  const raw = (await r.json()) as Partial<StudentMe>;
  return { ...(raw as StudentMe), has_avatar: Boolean(raw.has_avatar) };
}

export async function fetchStudentMyCourses(): Promise<{ courses: StudentCourseRow[] }> {
  const t = getStudentAccessToken().trim();
  if (!t) throw new Error("Не выполнен вход студента.");
  const r = await fetch(buildApiUrl("/api/public/my/courses"), { headers: { Authorization: `Bearer ${t}` } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<{ courses: StudentCourseRow[] }>;
}

export type StudentStatsPayload = {
  totals: { submissions: number; courses_touched: number };
  by_kind: { kind: string; attempts: number; avg_score_ratio: number }[];
  by_course: { slug: string; title: string; attempts: number; avg_score_ratio: number }[];
  weak_skill_kind: string | null;
  hints_ru: string[];
};

export async function fetchStudentStats(): Promise<StudentStatsPayload> {
  const t = getStudentAccessToken().trim();
  if (!t) throw new Error("Не выполнен вход студента.");
  const r = await fetch(buildApiUrl("/api/public/my/stats"), { headers: { Authorization: `Bearer ${t}` } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<StudentStatsPayload>;
}

export type StudentProgressAttempt = {
  id: string;
  problem_id: string;
  title: string;
  course_slug: string;
  kind: string;
  score: number | null;
  max_score: number;
  passed: boolean;
  scoring_reason: string | null;
  created_at: string | null;
};

export type StudentProgressSolved = {
  problem_id: string;
  title: string;
  course_slug: string;
  kind: string;
  max_score: number;
  difficulty?: number | null;
  solved_at: string | null;
  elo_after: number;
  best_score: number;
};

export type StudentProgressPayload = {
  elo_rating: number;
  attempts: StudentProgressAttempt[];
  solved: StudentProgressSolved[];
};

export async function fetchStudentProgress(): Promise<StudentProgressPayload> {
  const t = getStudentAccessToken().trim();
  if (!t) throw new Error("Не выполнен вход студента.");
  const r = await fetch(buildApiUrl("/api/public/my/progress"), { headers: { Authorization: `Bearer ${t}` } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<StudentProgressPayload>;
}

export type ExamProspectPayload = {
  note: string;
  courses: { slug: string; title: string; exam_pass_probability: number | null; forecast_stub: string }[];
};

export async function fetchStudentExamProspect(): Promise<ExamProspectPayload> {
  const t = getStudentAccessToken().trim();
  if (!t) throw new Error("Не выполнен вход студента.");
  const r = await fetch(buildApiUrl("/api/public/my/exam-prospect"), { headers: { Authorization: `Bearer ${t}` } });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<ExamProspectPayload>;
}

export function logoutStudent(): void {
  clearStudentSession();
}
