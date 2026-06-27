/** Локальное хранение диалогов студенческого чата ИИ (без сервера). */

const STORAGE_KEY = "bstu_student_chats_v2";

export type StoredStudentChatRole = "user" | "assistant";

export type StoredStudentChatMessage = {
  role: StoredStudentChatRole;
  content: string;
};

export type StudentChatSession = {
  id: string;
  courseId: string;
  messages: StoredStudentChatMessage[];
  updatedAt: number;
};

export type StudentChatBundle = {
  version: 2;
  sessions: StudentChatSession[];
  lastActiveByCourse: Partial<Record<string, string>>;
  systemPrompt: string;
};

const emptyBundle = (): StudentChatBundle => ({
  version: 2,
  sessions: [],
  lastActiveByCourse: {},
  systemPrompt: "",
});

export function loadStudentChatBundle(): StudentChatBundle {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyBundle();
    const j = JSON.parse(raw) as Partial<StudentChatBundle>;
    if (j.version !== 2 || !Array.isArray(j.sessions)) return emptyBundle();
    return {
      version: 2,
      sessions: j.sessions
        .filter((s): s is StudentChatSession => typeof s?.id === "string" && typeof s?.courseId === "string")
        .map((s) => ({
          id: s.id,
          courseId: s.courseId,
          messages: Array.isArray(s.messages)
            ? s.messages.filter(
                (m): m is StoredStudentChatMessage =>
                  m &&
                  (m.role === "user" || m.role === "assistant") &&
                  typeof m.content === "string",
              )
            : [],
          updatedAt: typeof s.updatedAt === "number" ? s.updatedAt : Date.now(),
        })),
      lastActiveByCourse:
        typeof j.lastActiveByCourse === "object" && j.lastActiveByCourse !== null
          ? { ...j.lastActiveByCourse }
          : {},
      systemPrompt: typeof j.systemPrompt === "string" ? j.systemPrompt : "",
    };
  } catch {
    return emptyBundle();
  }
}

export function saveStudentChatBundle(bundle: StudentChatBundle): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(bundle));
  } catch {
    /* quota */
  }
}

export function newStudentChatSession(courseId: string): StudentChatSession {
  return {
    id: crypto.randomUUID(),
    courseId,
    messages: [],
    updatedAt: Date.now(),
  };
}

function sessionsForCourse(sessions: StudentChatSession[], courseId: string): StudentChatSession[] {
  return sessions.filter((s) => s.courseId === courseId).sort((a, b) => b.updatedAt - a.updatedAt);
}

export function resolveStudentActiveSession(
  sessions: StudentChatSession[],
  courseId: string,
  lastActiveByCourse: Partial<Record<string, string>>,
): { activeId: string; sessions: StudentChatSession[] } {
  const list = sessionsForCourse(sessions, courseId);
  const hinted = lastActiveByCourse[courseId];
  const byHint = hinted ? list.find((s) => s.id === hinted) : undefined;
  if (byHint) return { activeId: byHint.id, sessions };
  if (list.length) return { activeId: list[0].id, sessions };
  const nu = newStudentChatSession(courseId);
  return { activeId: nu.id, sessions: [...sessions, nu] };
}

export function studentSessionTitle(s: StudentChatSession): string {
  const first = s.messages.find((m) => m.role === "user" && m.content.trim());
  if (first) {
    const t = first.content.trim().replace(/\s+/g, " ");
    return t.length > 48 ? `${t.slice(0, 45)}…` : t;
  }
  return "Новый диалог";
}
