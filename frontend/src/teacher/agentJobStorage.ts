/** Активная генерация черновиков — переживает обновление страницы. */

export type AgentDraftJobPersist = {
  jobId: string;
  startedAt: number;
};

function key(courseId: string): string {
  return `bstu-agent-draft-job:${courseId}`;
}

export function loadAgentDraftJob(courseId: string): AgentDraftJobPersist | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(key(courseId));
    if (!raw) return null;
    const v = JSON.parse(raw) as unknown;
    if (!v || typeof v !== "object") return null;
    const jobId = (v as AgentDraftJobPersist).jobId;
    const startedAt = (v as AgentDraftJobPersist).startedAt;
    if (typeof jobId !== "string" || !jobId.trim()) return null;
    if (typeof startedAt !== "number" || !Number.isFinite(startedAt)) return null;
    return { jobId: jobId.trim(), startedAt };
  } catch {
    return null;
  }
}

export function saveAgentDraftJob(courseId: string, data: AgentDraftJobPersist): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(key(courseId), JSON.stringify(data));
  } catch {
    /* quota / private mode */
  }
}

export function clearAgentDraftJob(courseId: string): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.removeItem(key(courseId));
  } catch {
    /* ignore */
  }
}
