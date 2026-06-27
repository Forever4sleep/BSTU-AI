/** Локальное хранение диалогов преподавательского чата (без сервера). */

const STORAGE_KEY = "bstu_teacher_chats_v2";

export type StoredChatRole = "user" | "assistant";

export type StoredChatMessage = {
  role: StoredChatRole;
  content: string;
};

export type TeacherChatSession = {
  id: string;
  courseId: string;
  messages: StoredChatMessage[];
  updatedAt: number;
};

export type TeacherChatBundle = {
  version: 2;
  sessions: TeacherChatSession[];
  /** По выбранному курсу помним последний открытый диалог */
  lastActiveByCourse: Partial<Record<string, string>>;
  systemPrompt: string;
};

const emptyBundle = (): TeacherChatBundle => ({
  version: 2,
  sessions: [],
  lastActiveByCourse: {},
  systemPrompt: "",
});

export function loadTeacherChatBundle(): TeacherChatBundle {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyBundle();
    const j = JSON.parse(raw) as Partial<TeacherChatBundle>;
    if (j.version !== 2 || !Array.isArray(j.sessions)) return emptyBundle();
    return {
      version: 2,
      sessions: j.sessions
        .filter((s): s is TeacherChatSession => typeof s?.id === "string" && typeof s?.courseId === "string")
        .map((s) => ({
          id: s.id,
          courseId: s.courseId,
          messages: Array.isArray(s.messages)
            ? s.messages.filter(
                (m): m is StoredChatMessage =>
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

export function saveTeacherChatBundle(bundle: TeacherChatBundle): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(bundle));
  } catch {
    /* quota / private mode */
  }
}

export function newSession(courseId: string): TeacherChatSession {
  return {
    id: crypto.randomUUID(),
    courseId,
    messages: [],
    updatedAt: Date.now(),
  };
}

function sessionsForCourse(sessions: TeacherChatSession[], courseId: string): TeacherChatSession[] {
  return sessions.filter((s) => s.courseId === courseId).sort((a, b) => b.updatedAt - a.updatedAt);
}

/** Активный id для курса: подсказка из lastActive, иначе самый свежий; при отсутствии — новая сессия. */
export function resolveActiveSession(
  sessions: TeacherChatSession[],
  courseId: string,
  lastActiveByCourse: Partial<Record<string, string>>,
): { activeId: string; sessions: TeacherChatSession[] } {
  const list = sessionsForCourse(sessions, courseId);
  const hinted = lastActiveByCourse[courseId];
  const byHint = hinted ? list.find((s) => s.id === hinted) : undefined;
  if (byHint) return { activeId: byHint.id, sessions };
  if (list.length) return { activeId: list[0].id, sessions };
  const nu = newSession(courseId);
  return { activeId: nu.id, sessions: [...sessions, nu] };
}

export function sessionTitle(s: TeacherChatSession): string {
  const first = s.messages.find((m) => m.role === "user" && m.content.trim());
  if (first) {
    const t = first.content.trim().replace(/\s+/g, " ");
    return t.length > 48 ? `${t.slice(0, 45)}…` : t;
  }
  return "Новый диалог";
}
