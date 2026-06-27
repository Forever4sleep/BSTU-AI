import { clearAdminSession, getAdminAccessToken } from "./adminSession";
import { clearStudentSession, getStudentAccessToken } from "./studentAccessKey";
import { TEACHER_STORAGE_KEY } from "./teacher/authStorage";

export type UnifiedLoginRole = "platform_admin" | "instructor" | "student";

/** Куда вести авторизованного пользователя со шапки «Профиль». */
export function cabinetHomeHref(): string {
  if (getAdminAccessToken().trim()) return "/admin";
  if (typeof localStorage !== "undefined") {
    const ins = localStorage.getItem(TEACHER_STORAGE_KEY)?.trim();
    if (ins) return "/teacher";
  }
  if (getStudentAccessToken().trim()) return "/student/cabinet";
  return "/login";
}

/** Куда перейти после успешного единого входа (учитывает state.from с защищённой страницы). */
export function cabinetPathAfterUnifiedLogin(role: UnifiedLoginRole, fromState?: unknown): string {
  const fallback =
    role === "platform_admin" ? "/admin" : role === "instructor" ? "/teacher" : "/student/cabinet";
  if (typeof fromState !== "string" || !fromState.startsWith("/") || fromState.startsWith("//")) {
    return fallback;
  }
  if (role === "platform_admin" && fromState.startsWith("/admin")) return fromState;
  if (role === "instructor" && fromState.startsWith("/teacher")) return fromState;
  if (
    role === "student" &&
    (fromState.startsWith("/student") || fromState.startsWith("/c/"))
  ) {
    return fromState;
  }
  return fallback;
}

/** Сброс сохранённых ролей в браузере (в том числе React-состояния преподавателя через clearTeacherContext). */
export function purgeAllCabinetSessions(clearTeacherContext: () => void): void {
  clearTeacherContext();
  clearAdminSession();
  clearStudentSession();
}

