import { buildApiUrl } from "./api";
import type { UnifiedLoginRole } from "./cabinetPath";

export type UnifiedSessionLoginResponse = {
  role: UnifiedLoginRole;
  access_token: string;
  token_type?: string;
  student_access_key?: string | null;
};

export async function unifiedSessionLogin(
  username: string,
  password: string,
): Promise<UnifiedSessionLoginResponse> {
  const r = await fetch(buildApiUrl("/api/public/session/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: username.trim().toLowerCase(), password }),
  });
  const text = await r.text();
  if (!r.ok) throw new Error(`${r.status} ${text}`);
  return JSON.parse(text) as UnifiedSessionLoginResponse;
}
