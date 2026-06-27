const LS_KEY = "bstu_platform_student_access_key";
const LS_JWT = "bstu_student_access_jwt";

export function getStoredStudentAccessKey(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(LS_KEY)?.trim() ?? "";
}

export function setStoredStudentAccessKey(value: string): void {
  if (typeof localStorage === "undefined") return;
  const v = value.trim();
  if (!v) localStorage.removeItem(LS_KEY);
  else localStorage.setItem(LS_KEY, v);
}

/** JWT после POST /api/public/auth/login (audience студента). */
export function getStudentAccessToken(): string {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(LS_JWT)?.trim() ?? "";
}

export function setStudentAccessToken(value: string): void {
  if (typeof localStorage === "undefined") return;
  const v = value.trim();
  if (!v) localStorage.removeItem(LS_JWT);
  else localStorage.setItem(LS_JWT, v);
}

export function setStudentSession(accessToken: string, accessKey: string): void {
  setStudentAccessToken(accessToken);
  setStoredStudentAccessKey(accessKey);
}

export function clearStudentSession(): void {
  setStoredStudentAccessKey("");
  setStudentAccessToken("");
}

export function studentAccessHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  const jwt = getStudentAccessToken();
  const k = getStoredStudentAccessKey();
  if (jwt) {
    h.Authorization = `Bearer ${jwt}`;
  }
  if (k) {
    h["X-Student-Access-Key"] = k;
  }
  return h;
}
