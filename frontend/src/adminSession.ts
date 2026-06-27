/** JWT платформенного администратора (отдельно от преподавателя и студента). */
const ADMIN_JWT_KEY = "bstu_platform_admin_jwt";

export function getAdminAccessToken(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(ADMIN_JWT_KEY)?.trim() ?? "";
}

export function setAdminAccessToken(token: string): void {
  if (typeof localStorage === "undefined") return;
  const v = token.trim();
  if (!v) localStorage.removeItem(ADMIN_JWT_KEY);
  else localStorage.setItem(ADMIN_JWT_KEY, v);
}

export function clearAdminSession(): void {
  setAdminAccessToken("");
}

export function adminBearerHeaders(): HeadersInit {
  const t = getAdminAccessToken().trim();
  return t ? { Authorization: `Bearer ${t}` } : {};
}
