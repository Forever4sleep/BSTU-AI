import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { platformGetJson, platformPostJson } from "../platformApi";
import { useTeacherAuth } from "./TeacherAuthContext";
import type { CourseOut } from "./types";

export function TeacherCoursesPage() {
  const { apiKey } = useTeacherAuth();
  const [courses, setCourses] = useState<CourseOut[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const [newSlug, setNewSlug] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newSubjectHint, setNewSubjectHint] = useState("");
  const [createBusy, setCreateBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!apiKey) return;
    setErr(null);
    try {
      const list = await platformGetJson<CourseOut[]>("/api/platform/courses", apiKey);
      setCourses(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [apiKey]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onCreate(ev: FormEvent) {
    ev.preventDefault();
    setCreateBusy(true);
    try {
      await platformPostJson<CourseOut>(
        "/api/platform/courses",
        apiKey,
        {
          slug: newSlug.trim().toLowerCase(),
          title: newTitle.trim(),
          subject_hint: newSubjectHint.trim() || undefined,
        },
      );
      setNewSlug("");
      setNewTitle("");
      setNewSubjectHint("");
      await refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setCreateBusy(false);
    }
  }

  return (
    <div className="t-page">
      <header className="t-page__head">
        <h1 className="t-page__title">Курсы</h1>
        <p className="t-page__sub">Разворачивайте «папку» курса или откройте страницу управления.</p>
      </header>

      {err && <div className="ds-alert ds-alert--err">{err}</div>}

      <section className="ds-card ds-mb">
        <h2 className="t-page__h2">Новый курс</h2>
        <p className="ds-caption">
          Slug: латиница, от 3 символов, <code className="ds-code">a-z0-9_-</code>
        </p>
        <form className="ds-form ds-form--row" onSubmit={onCreate}>
          <label className="ds-label">
            Slug
            <input className="ds-input" value={newSlug} onChange={(e) => setNewSlug(e.target.value)} required />
          </label>
          <label className="ds-label">
            Название
            <input className="ds-input" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} required />
          </label>
          <label className="ds-label">
            Тема (опц.)
            <input
              className="ds-input"
              value={newSubjectHint}
              onChange={(e) => setNewSubjectHint(e.target.value)}
            />
          </label>
          <button type="submit" className="ds-btn ds-btn--primary ds-form__btn" disabled={createBusy}>
            {createBusy ? "…" : "Создать"}
          </button>
        </form>
      </section>

      <section>
        {courses.length === 0 && <p className="ds-empty">Пока нет курсов — создайте первый выше.</p>}
        <ul className="ds-folder-list">
          {courses.map((c) => {
            const open = openId === c.id;
            return (
              <li key={c.id} className="ds-folder">
                <button
                  type="button"
                  className="ds-folder__head"
                  aria-expanded={open}
                  onClick={() => setOpenId(open ? null : c.id)}
                >
                  <span className={`ds-folder__chev ${open ? "ds-folder__chev--open" : ""}`} aria-hidden />
                  <span className="ds-folder__title">{c.title}</span>
                  <code className="ds-folder__slug">{c.slug}</code>
                </button>
                {open && (
                  <div className="ds-folder__body">
                    <p className="ds-caption">
                      {c.subject_hint ? <>Тема индексации: {c.subject_hint}</> : <>Тема по умолчанию — из названия курса.</>}
                    </p>
                    <div className="ds-folder__actions">
                      <Link to={`/teacher/courses/${c.id}`} className="ds-btn ds-btn--primary ds-btn--sm">
                        Открыть курс
                      </Link>
                      <Link to={`/c/${encodeURIComponent(c.slug)}`} className="ds-btn ds-btn--ghost ds-btn--sm">
                        Как видит студент
                      </Link>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
