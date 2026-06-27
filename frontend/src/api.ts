import { studentAccessHeaders as studentAuthMergedHeaders } from "./studentAccessKey";

const apiRoot = () => import.meta.env.VITE_API_BASE ?? "";

export function buildApiUrl(
  path: string,
  query?: Record<string, string | boolean | number | undefined>,
): string {
  const rootTrim = apiRoot().replace(/\/+$/, "");
  let rel = path.startsWith("/") ? path : `/${path}`;
  /** If ``VITE_API_BASE`` уже заканчивается на ``/api``, а маршруты заданы как ``/api/platform/…``, без этого получится ``…/api/api/…`` (404). */
  if (rootTrim.endsWith("/api") && rel.startsWith("/api/")) {
    rel = rel.slice(4);
  }
  let url = `${rootTrim}${rel}`;
  if (!query) return url;
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined) sp.set(k, String(v));
  }
  const q = sp.toString();
  if (q) url += `?${q}`;
  return url;
}

function buildUrl(path: string, query?: Record<string, string | boolean | number | undefined>) {
  return buildApiUrl(path, query);
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(buildUrl(path));
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status} ${t}`);
  }
  return r.json() as Promise<T>;
}

/** Публичные эндпоины задачникa: Bearer студента и/или `X-Student-Access-Key`. */
export async function apiPublicWithStudent<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(buildUrl(path), {
    ...init,
    headers: { ...studentAuthMergedHeaders(), ...init?.headers },
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status} ${t}`);
  }
  return r.json() as Promise<T>;
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  query?: Record<string, string | boolean | number | undefined>,
): Promise<T> {
  const r = await fetch(buildUrl(path, query), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status} ${t}`);
  }
  return r.json() as Promise<T>;
}

/** POST на /api/public/ с заголовками студента (JWT и/или ключ). */
export async function apiPostPublicWithStudent<T>(
  path: string,
  body: unknown,
  query?: Record<string, string | boolean | number | undefined>,
): Promise<T> {
  const r = await fetch(buildUrl(path, query), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...studentAuthMergedHeaders() },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status} ${t}`);
  }
  return r.json() as Promise<T>;
}

/** Опрос Celery по job_id (ответ submit свободного текста). */
export async function apiPlatformJob(jobId: string): Promise<{
  job_id: string;
  status: string;
  result?: unknown;
  error?: string;
  meta?: { phase?: string; label?: string; logs?: string[] };
}> {
  const r = await fetch(buildUrl(`/api/platform/jobs/${encodeURIComponent(jobId)}`));
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status} ${t}`);
  }
  return r.json() as Promise<{
    job_id: string;
    status: string;
    result?: unknown;
    error?: string;
    meta?: { phase?: string; label?: string; logs?: string[] };
  }>;
}
