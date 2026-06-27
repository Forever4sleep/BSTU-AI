import { FormEvent, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { Link } from "react-router-dom";

import { platformGetJson } from "../platformApi";
import type { ChatMessage } from "./chatApi";
import { streamChatCompletion } from "./chatApi";
import { ChatMarkdown } from "./ChatMarkdown";
import { useTeacherAuth } from "./TeacherAuthContext";
import {
  loadTeacherChatBundle,
  newSession,
  resolveActiveSession,
  saveTeacherChatBundle,
  sessionTitle,
  type TeacherChatSession,
} from "./teacherChatStorage";
import type { CourseOut } from "./types";

const DEFAULT_SYSTEM =
  "Ты полезный ассистент для преподавателя технического вуза. Отвечай по-русски, кратко и по делу.";

function IconMenu() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
    </svg>
  );
}

function IconPlus() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}

function IconStop() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

function IconSend() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" stroke="none" />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path
        d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Полноэкранный чат с RAG по курсу — вёрстка в духе Open WebUI. */
export function TeacherChatPage() {
  const { apiKey } = useTeacherAuth();
  const [courses, setCourses] = useState<CourseOut[]>([]);
  const [coursesErr, setCoursesErr] = useState<string | null>(null);
  const [railOpen, setRailOpen] = useState(false);

  const [bundle, setBundle] = useState(loadTeacherChatBundle);
  const [system, setSystem] = useState(() => loadTeacherChatBundle().systemPrompt.trim() || DEFAULT_SYSTEM);

  const [courseId, setCourseIdState] = useState("");
  const [activeId, setActiveId] = useState("");

  const [sysOpen, setSysOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const listEndRef = useRef<HTMLDivElement | null>(null);
  const streamTargetIdRef = useRef<string | null>(null);
  const messagesScrollRef = useRef<HTMLDivElement | null>(null);

  const activeSession = useMemo(() => bundle.sessions.find((s) => s.id === activeId), [bundle.sessions, activeId]);
  const displayMessages = activeSession?.messages ?? [];

  const sidebarSessions = useMemo(
    () =>
      bundle.sessions.filter((s) => s.courseId === courseId).sort((a, b) => b.updatedAt - a.updatedAt),
    [bundle.sessions, courseId],
  );

  useEffect(() => {
    const ac = new AbortController();
    if (!apiKey) {
      setCourses([]);
      return;
    }
    void (async () => {
      try {
        setCoursesErr(null);
        const list = await platformGetJson<CourseOut[]>("/api/platform/courses", apiKey, ac.signal);
        setCourses(list);
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          setCoursesErr(e instanceof Error ? e.message : String(e));
        }
      }
    })();
    return () => ac.abort();
  }, [apiKey]);

  useEffect(() => {
    if (!courses.length) {
      setCourseIdState("");
      setActiveId("");
      return;
    }
    const nextCid = courseId && courses.some((c) => c.id === courseId) ? courseId : courses[0].id;
    const { activeId: aid, sessions: nextSessions } = resolveActiveSession(
      bundle.sessions,
      nextCid,
      bundle.lastActiveByCourse,
    );
    if (nextCid !== courseId) setCourseIdState(nextCid);
    if (nextSessions !== bundle.sessions) {
      setBundle((b) => ({ ...b, sessions: nextSessions }));
    }
    setActiveId((cur) => (cur === aid ? cur : aid));
  }, [courses, courseId, bundle.sessions, bundle.lastActiveByCourse]);

  useEffect(() => {
    if (!courseId || !activeId) return;
    const exists = bundle.sessions.some((s) => s.id === activeId);
    if (exists) return;
    const { activeId: aid, sessions: nextSessions } = resolveActiveSession(
      bundle.sessions,
      courseId,
      bundle.lastActiveByCourse,
    );
    setBundle((b) => (nextSessions !== b.sessions ? { ...b, sessions: nextSessions } : b));
    setActiveId(aid);
  }, [bundle.sessions, bundle.lastActiveByCourse, courseId, activeId]);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [displayMessages, busy]);

  useEffect(() => {
    saveTeacherChatBundle({ ...bundle, systemPrompt: system });
  }, [bundle, system]);

  function pickSession(id: string) {
    setActiveSessionId(id);
    setRailOpen(false);
  }

  function setCourseId(next: string) {
    setCourseIdState(next);
    const { activeId: aid, sessions: nextSessions } = resolveActiveSession(
      bundle.sessions,
      next,
      bundle.lastActiveByCourse,
    );
    if (nextSessions !== bundle.sessions) {
      setBundle((b) => ({ ...b, sessions: nextSessions }));
    }
    setActiveId(aid);
  }

  function setActiveSessionId(id: string) {
    setActiveId(id);
    if (!courseId) return;
    setBundle((b) => ({
      ...b,
      lastActiveByCourse: { ...b.lastActiveByCourse, [courseId]: id },
    }));
  }

  function createNewChat() {
    if (!courseId) return;
    const ns = newSession(courseId);
    setBundle((b) => ({
      ...b,
      sessions: [ns, ...b.sessions],
      lastActiveByCourse: { ...b.lastActiveByCourse, [courseId]: ns.id },
    }));
    setActiveId(ns.id);
    setErr(null);
    setRailOpen(false);
  }

  function deleteSession(id: string, ev: MouseEvent) {
    ev.stopPropagation();
    setBundle((prev) => {
      const rest = prev.sessions.filter((s) => s.id !== id);
      const nextRemember = { ...prev.lastActiveByCourse };
      for (const k of Object.keys(nextRemember)) {
        if (nextRemember[k as keyof typeof nextRemember] === id)
          delete nextRemember[k as keyof typeof nextRemember];
      }
      return { ...prev, sessions: rest, lastActiveByCourse: nextRemember };
    });
  }

  function assembleMessages(history: TeacherChatSession["messages"]): ChatMessage[] {
    const out: ChatMessage[] = [];
    const s = system.trim();
    if (s) out.push({ role: "system", content: s });
    for (const m of history) {
      out.push({ role: m.role, content: m.content });
    }
    return out;
  }

  async function submitChat() {
    const q = input.trim();
    if (!q || !courseId || busy || !apiKey) return;

    setErr(null);
    setInput("");

    const userMsg = { role: "user" as const, content: q };
    const assistantEmpty = { role: "assistant" as const, content: "" };

    streamTargetIdRef.current = activeId;

    const sessionSnap = bundle.sessions.find((s) => s.id === activeId);
    const historyForPayload = [...(sessionSnap?.messages ?? []), userMsg];

    setBundle((b) => ({
      ...b,
      sessions: b.sessions.map((s) =>
        s.id === activeId
          ? {
              ...s,
              messages: [...s.messages, userMsg, assistantEmpty],
              updatedAt: Date.now(),
            }
          : s,
      ),
    }));

    setBusy(true);

    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    try {
      await streamChatCompletion({
        messages: assembleMessages(historyForPayload),
        courseId,
        bearer: apiKey ?? undefined,
        signal: ac.signal,
        onDelta: (frag) => {
          const sid = streamTargetIdRef.current;
          if (!sid) return;
          setBundle((b) => ({
            ...b,
            sessions: b.sessions.map((s) => {
              if (s.id !== sid) return s;
              const msgs = [...s.messages];
              if (!msgs.length) return s;
              const last = msgs[msgs.length - 1];
              if (last.role !== "assistant") return s;
              msgs[msgs.length - 1] = { ...last, content: `${last.content}${frag}` };
              return { ...s, messages: msgs, updatedAt: Date.now() };
            }),
          }));
        },
      });
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setErr(e instanceof Error ? e.message : String(e));
        const sid = streamTargetIdRef.current;
        if (sid) {
          setBundle((b) => ({
            ...b,
            sessions: b.sessions.map((s) =>
              s.id === sid ? { ...s, messages: [...s.messages, userMsg], updatedAt: Date.now() } : s,
            ),
          }));
        }
      }
    } finally {
      streamTargetIdRef.current = null;
      setBusy(false);
      abortRef.current = null;
    }
  }

  async function send(ev: FormEvent) {
    ev.preventDefault();
    await submitChat();
  }

  function stop() {
    abortRef.current?.abort();
  }

  const selectedCourseTitle = courses.find((c) => c.id === courseId)?.title ?? "";
  const canChat = Boolean(courseId && apiKey);

  return (
    <div className="owe-chat">
      {/* Мобильный оверлей для боковой панели */}
      <button
        type="button"
        className={`owe-rail-scrim ${railOpen ? "owe-rail-scrim--visible" : ""}`}
        aria-label="Закрыть список чатов"
        onClick={() => setRailOpen(false)}
      />

      {/* Левая колонка: диалоги (как история чатов в Open WebUI) */}
      <aside className={`owe-rail ${railOpen ? "owe-rail--open" : ""}`}>
        <div className="owe-rail__head">
          <span className="owe-rail__ttl">Чаты курса</span>
          <button type="button" className="owe-rail__close-mobile" aria-label="Закрыть" onClick={() => setRailOpen(false)}>
            ×
          </button>
        </div>

        <button type="button" className="owe-new-chat" onClick={() => createNewChat()} disabled={!canChat}>
          <IconPlus /> <span>Новый чат</span>
        </button>
        <ul className="owe-conv-list">
          {sidebarSessions.map((s) => (
            <li key={s.id} className="owe-conv-li">
              <button
                type="button"
                className={`owe-conv-item ${s.id === activeId ? "owe-conv-item--active" : ""}`}
                onClick={() => pickSession(s.id)}
              >
                <span className="owe-conv-item__title">{sessionTitle(s)}</span>
                <span className="owe-conv-item__time">
                  {new Date(s.updatedAt).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}
                </span>
              </button>
              <button
                type="button"
                className="owe-conv-del"
                aria-label="Удалить диалог"
                title="Удалить"
                onClick={(ev) => deleteSession(s.id, ev)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>

        <p className="owe-rail__note">История чатов сохраняется на этом устройстве.</p>
      </aside>

      {/* Основная зона */}
      <div className="owe-pane">
        <header className="owe-topbar">
          <div className="owe-topbar__lead">
            <button
              type="button"
              className="owe-btn-icon owe-topbar__menu"
              aria-label="Диалоги"
              title="Диалоги"
              onClick={() => setRailOpen(true)}
            >
              <IconMenu />
            </button>
            <nav className="owe-nav-mini" aria-label="Платформа преподавателя">
              <Link to="/teacher">Обзор</Link>
              <span className="owe-nav-mini__sep" aria-hidden>
                /
              </span>
              <Link to="/teacher/courses">Курсы</Link>
            </nav>
          </div>

          <div className="owe-topbar__titles">
            <h1 className="owe-brand-title">Чат ИИ</h1>
            <p className="owe-brand-sub">RAG по курсу · модель задаётся на сервере</p>
          </div>

          <div className="owe-topbar__controls">
            <div className="owe-picker">
              <span className="owe-picker__hint">Курс</span>
              <div className="owe-picker__wrap">
                <select
                  className="owe-picker__select"
                  value={courseId}
                  disabled={!courses.length}
                  onChange={(e) => setCourseId(e.target.value)}
                >
                  {courses.length === 0 ? (
                    <option value="">Нет курсов</option>
                  ) : (
                    courses.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title}
                      </option>
                    ))
                  )}
                </select>
              </div>
            </div>
            {courseId && courses.some((c) => c.id === courseId) ? (
              <Link className="owe-link-mini" to={`/teacher/courses/${courseId}`} title="К материалам курса">
                материалы
              </Link>
            ) : null}
          </div>
        </header>

        {sysOpen && (
          <div className="owe-sys-panel">
            <label className="owe-sys-label">
              Системная инструкция (промпт преподавателя)
              <textarea
                className="owe-sys-textarea"
                rows={5}
                value={system}
                onChange={(e) => setSystem(e.target.value)}
                spellCheck={false}
              />
            </label>
          </div>
        )}

        {coursesErr ? <div className="owe-banner owe-banner--err">{coursesErr}</div> : null}
        {err ? <div className="owe-banner owe-banner--err">{err}</div> : null}

        {!apiKey ? (
          <div className="owe-banner owe-banner--err">Выполните вход в профиль преподавателя.</div>
        ) : null}

        <div className="owe-thread-scroll" ref={messagesScrollRef} role="log" aria-live="polite">
          {displayMessages.length === 0 ? (
            <div className="owe-empty">
              <div className="owe-empty__orb" aria-hidden />
              <h2 className="owe-empty__title">{selectedCourseTitle || "Выберите курс"}</h2>
              <p className="owe-empty__text">
                Задавайте вопросы по загруженным материалам. Ответы оформляются с поддержкой Markdown: код,
                таблицы, списки.
              </p>
              <ul className="owe-empty__tips">
                <li>Вопрос отправляется клавишей Enter (Shift+Enter — новая строка).</li>
                <li>Контекст поиска — коллекция Qdrant выбранного курса.</li>
              </ul>
            </div>
          ) : (
            <div className="owe-msgs">
              {displayMessages.map((m, i) => {
                const lastTyping = busy && i === displayMessages.length - 1 && m.role === "assistant";
                const isUser = m.role === "user";
                return (
                  <div key={i} className={`owe-msg owe-msg--${m.role}`}>
                    <div className="owe-msg__aside">
                      <div className={`owe-msg__avatar owe-msg__avatar--${m.role}`} aria-hidden>
                        {isUser ? "Вы" : "ИИ"}
                      </div>
                    </div>
                    <div className="owe-msg__bubble">
                      <div className="owe-msg__role">{isUser ? "Вы" : "Ассистент"}</div>
                      <div className="owe-msg__body">
                        {!isUser ? (
                          m.content ? (
                            <ChatMarkdown text={m.content} />
                          ) : lastTyping ? (
                            <span className="owe-typing" aria-busy="true">
                              <span />
                              <span />
                              <span />
                            </span>
                          ) : (
                            <p className="owe-msg-fallback">
                              Ответ не пришёл или поток был пустым. Проверьте сообщение выше или отправьте ещё раз.
                            </p>
                          )
                        ) : (
                          <p className="owe-msg-user-txt">{m.content}</p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              <div ref={listEndRef} className="owe-msgs-end" />
            </div>
          )}
        </div>

        <div className="owe-compose-wrap">
          <div className="owe-compose-tools">
            <button
              type="button"
              className={`owe-tool-btn ${sysOpen ? "owe-tool-btn--on" : ""}`}
              onClick={() => setSysOpen(!sysOpen)}
              title="Системный промпт"
            >
              <IconSettings /> <span>Системная инструкция</span>
            </button>
            <button
              type="button"
              className="owe-tool-btn"
              disabled={!busy}
              onClick={() => stop()}
              title="Остановить генерацию"
            >
              <IconStop /> <span>Стоп</span>
            </button>
          </div>

          <form className="owe-compose" onSubmit={(e) => void send(e)}>
            <textarea
              className="owe-compose__field"
              rows={1}
              placeholder={
                canChat
                  ? "Спросите о материалах курса…"
                  : "Сначала выберите курс из списка выше или создайте курс на странице «Курсы»"
              }
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy || !canChat}
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void submitChat();
                }
              }}
            />
            <button type="submit" className="owe-compose__send" disabled={busy || !canChat || !input.trim()} title="Отправить">
              <IconSend />
            </button>
          </form>
          <div className="owe-compose-hints">
            <span>Клавиши: Enter отправить · Shift+Enter новая строка · Ctrl+V вставить</span>
          </div>
        </div>
      </div>
    </div>
  );
}
