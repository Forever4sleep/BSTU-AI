import { adminBearerHeaders } from "./adminSession";
import { buildApiUrl } from "./api";

import type { StudyGroupOut } from "./teacher/types";

/** Список групп; при 404 на ``/admin/study-groups`` пробует ``/admin/groups``. */
export async function adminListStudyGroups(): Promise<StudyGroupOut[]> {
  try {
    return await adminGetJson<StudyGroupOut[]>("/api/platform/admin/study-groups");
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/^404\b/.test(msg)) {
      return await adminGetJson<StudyGroupOut[]>("/api/platform/admin/groups");
    }
    throw e;
  }
}

export async function adminPostStudyGroup(title: string): Promise<StudyGroupOut> {
  try {
    return await adminPostJson<StudyGroupOut>("/api/platform/admin/study-groups", { title });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/^404\b/.test(msg)) {
      return await adminPostJson<StudyGroupOut>("/api/platform/admin/groups", { title });
    }
    throw e;
  }
}

export async function adminDeleteStudyGroup(groupId: string): Promise<void> {
  const idEnc = encodeURIComponent(groupId);
  try {
    await adminDelete(`/api/platform/admin/study-groups/${idEnc}`);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/^404\b/.test(msg)) {
      await adminDelete(`/api/platform/admin/groups/${idEnc}`);
      return;
    }
    throw e;
  }
}

export async function adminGetJson<T>(path: string): Promise<T> {
  const r = await fetch(buildApiUrl(path), { headers: adminBearerHeaders() });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function adminPostJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "POST",
    headers: { ...adminBearerHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function adminPatchJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "PATCH",
    headers: { ...adminBearerHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function adminDelete(path: string): Promise<void> {
  const r = await fetch(buildApiUrl(path), {
    method: "DELETE",
    headers: adminBearerHeaders(),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
}

export async function adminCreateInstructor(body: {
  display_name: string;
  username: string;
  password: string;
}): Promise<{ id: string; display_name: string; username: string }> {
  const r = await fetch(buildApiUrl("/api/platform/admin/instructors"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...adminBearerHeaders(),
    },
    body: JSON.stringify({
      display_name: body.display_name,
      username: body.username.trim().toLowerCase(),
      password: body.password,
    }),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<{ id: string; display_name: string; username: string }>;
}

export type InstructorBootstrapResponse = {
  id: string;
  display_name: string;
  api_key?: string | null;
  username?: string | null;
  access_token?: string | null;
};

export async function platformBootstrap(
  bootstrapSecret: string,
  displayName: string,
  username?: string | null,
  password?: string | null,
): Promise<InstructorBootstrapResponse> {
  const body: Record<string, string> = { display_name: displayName };
  const u = username?.trim();
  const p = password ?? "";
  if (u || p) {
    if (!u || !p) throw new Error("Укажите и логин, и пароль для bootstrap.");
    body.username = u.toLowerCase();
    body.password = p;
  }
  const r = await fetch(buildApiUrl("/api/platform/instructors/bootstrap"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Platform-Bootstrap-Secret": bootstrapSecret,
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<InstructorBootstrapResponse>;
}

export async function platformLogin(
  username: string,
  password: string,
): Promise<{ access_token: string; token_type: string }> {
  const r = await fetch(buildApiUrl("/api/platform/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: username.trim().toLowerCase(), password }),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<{ access_token: string; token_type: string }>;
}

export async function platformGetJson<T>(path: string, bearer: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    headers: { Authorization: `Bearer ${bearer}` },
    signal,
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function platformPostJson<T>(path: string, bearer: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${bearer}`,
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function platformPatchJson<T>(path: string, bearer: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${bearer}`,
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function platformPutJson<T>(path: string, bearer: string, body: unknown): Promise<T> {
  const r = await fetch(buildApiUrl(path), {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${bearer}`,
    },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export async function platformDelete(path: string, bearer: string): Promise<void> {
  const r = await fetch(buildApiUrl(path), {
    method: "DELETE",
    headers: { Authorization: `Bearer ${bearer}` },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
}

export async function platformUpload(
  path: string,
  bearer: string,
  formData: FormData,
): Promise<{ job_id: string; document_catalog_id: string }> {
  const r = await fetch(buildApiUrl(path), {
    method: "POST",
    headers: { Authorization: `Bearer ${bearer}` },
    body: formData,
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<{ job_id: string; document_catalog_id: string }>;
}

export async function platformDownloadBlob(path: string, bearer: string): Promise<Blob> {
  const r = await fetch(buildApiUrl(path), {
    headers: { Authorization: `Bearer ${bearer}` },
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.blob();
}

export async function platformJobStatus(jobId: string): Promise<{
  job_id: string;
  status: string;
  result?: unknown;
  error?: string;
  /** Celery PROGRESS meta или подпись для STARTED — см. GET /api/platform/jobs/{id} */
  meta?: { phase?: string; label?: string; logs?: string[] };
}> {
  const r = await fetch(buildApiUrl(`/api/platform/jobs/${encodeURIComponent(jobId)}`));
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json() as Promise<{
    job_id: string;
    status: string;
    result?: unknown;
    error?: string;
    meta?: { phase?: string; label?: string; logs?: string[] };
  }>;
}
