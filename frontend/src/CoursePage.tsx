import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { apiGet, apiPublicWithStudent } from "./api";
import { problemKindLabel, friendlyHttpError } from "./labels";
import type { ProblemListItem } from "./types";
import { getStoredStudentAccessKey, getStudentAccessToken, setStoredStudentAccessKey } from "./studentAccessKey";

function is404Message(msg: string) {
  return /^\s*404\b/.test(msg) || msg.includes("Не найдено");
}

type CourseMeta = {
  slug: string;
  title: string;
  visibility_mode?: string;
  requires_student_access_key?: boolean;
};

export function CoursePage() {
  const { slug } = useParams<{ slug: string }>();
  const [title, setTitle] = useState<string | null>(null);
  const [problems, setProblems] = useState<ProblemListItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [needsKey, setNeedsKey] = useState(false);
  const [keyDraft, setKeyDraft] = useState("");
  const [showKeyForm, setShowKeyForm] = useState(false);

  useEffect(() => {
    setKeyDraft(getStoredStudentAccessKey());
  }, [slug]);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    (async () => {
      setErr(null);
      setProblems(null);
      setTitle(null);
      try {
        const c = await apiGet<CourseMeta>(`/api/public/courses/${encodeURIComponent(slug)}`);
        if (cancelled) return;
        setTitle(c.title);
        const gated = Boolean(c.requires_student_access_key ?? c.visibility_mode === "groups");
        setNeedsKey(gated);
        const list = await apiPublicWithStudent<ProblemListItem[]>(
          `/api/public/courses/${encodeURIComponent(slug)}/problems`,
        );
        if (cancelled) return;
        setErr(null);
        setProblems(list);
      } catch (e) {
        if (!cancelled) setErr(friendlyHttpError(e, "Не удалось загрузить курс."));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [slug]);

  function applyKey(ev: FormEvent) {
    ev.preventDefault();
    setStoredStudentAccessKey(keyDraft);
    setErr(null);
    setProblems(null);
    if (!slug) return;
    void (async () => {
      try {
        const list = await apiPublicWithStudent<ProblemListItem[]>(
          `/api/public/courses/${encodeURIComponent(slug)}/problems`,
        );
        setProblems(list);
        setShowKeyForm(false);
      } catch (e) {
        setErr(friendlyHttpError(e, "Не удалось загрузить задания."));
      }
    })();
  }

  if (!slug) {
    return <div className="ds-alert ds-alert--err">Некорректная ссылка на курс.</div>;
  }

  const slug404 = err && is404Message(err);
  const loggedIn = Boolean(getStudentAccessToken().trim());
  const gateFormVisible =
    needsKey && problems === null && !slug404 && (showKeyForm || (!loggedIn && !getStoredStudentAccessKey()));

  return (
    <>
      <header className="t-page__head">
        <h1 className="t-page__title">{slug404 ? "Курс не найден" : title ?? "Загрузка…"}</h1>
      </header>

      <div className="stu-card stu-rise-in">
        {gateFormVisible && (
          <div className={`ds-alert ${err?.includes("доступ") ? "ds-alert--err" : ""} ds-mb`}>
            <p style={{ margin: 0 }}>
              Этот курс доступен только студентам вашей группы.{" "}
              {!loggedIn ? (
                <>
                  <Link className="ds-link-bold" to="/login">
                    Войдите
                  </Link>{" "}
                  под учётной записью студента или укажите код доступа от преподавателя.
                </>
              ) : (
                <>Если задания не отображаются, уточните доступ у преподавателя или введите код доступа.</>
              )}
            </p>
            <form className="ds-form ds-mt" onSubmit={applyKey}>
              <label className="ds-label">
                Код доступа
                <input
                  className="ds-input"
                  value={keyDraft}
                  onChange={(e) => setKeyDraft(e.target.value)}
                  placeholder="Код от преподавателя"
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
              <button type="submit" className="ds-btn ds-btn--primary">
                Продолжить
              </button>
            </form>
          </div>
        )}

        {needsKey && problems === null && loggedIn && !gateFormVisible && !slug404 && !err && (
          <p className="ds-caption ds-mb">Загрузка заданий…</p>
        )}

        {needsKey && problems === null && loggedIn && !showKeyForm && err && !slug404 && (
          <p className="ds-caption ds-mb">
            <button type="button" className="ds-link-bold" onClick={() => setShowKeyForm(true)}>
              Ввести код доступа
            </button>
          </p>
        )}

        {err && !slug404 && !gateFormVisible && <div className="ds-alert ds-alert--err">{err}</div>}

        {slug404 && (
          <p className="ds-caption">
            Курс не найден. Проверьте идентификатор или обратитесь к преподавателю.
          </p>
        )}
        {!err && problems === null && !gateFormVisible && !slug404 && (
          <p className="ds-caption">Загрузка задач…</p>
        )}
        {!slug404 && problems && problems.length === 0 && (
          <p className="ds-empty">Пока нет опубликованных заданий.</p>
        )}
        {!slug404 && problems && problems.length > 0 && (
          <div className="stu-lc-wrap">
            <table className="stu-lc-table">
              <thead>
                <tr>
                  <th className="stu-lc-col-title">Задача</th>
                  <th className="stu-lc-col-result">Ваш результат</th>
                  <th className="stu-lc-col-diff">Сложность</th>
                  <th className="stu-lc-col-kind">Тип</th>
                </tr>
              </thead>
              <tbody>
                {problems.map((p) => (
                  <tr key={p.id} className="stu-lc-row">
                    <td>
                      <Link className="stu-lc-link" to={`/c/${encodeURIComponent(slug)}/p/${p.id}`}>
                        {p.title}
                      </Link>
                    </td>
                    <td className="stu-lc-col-result">
                      {p.recorded_score != null && p.recorded_score !== undefined ? (
                        <div className="stu-lc-result-cell">
                          <span className="stu-lc-score-line">
                            <strong>{Number(p.recorded_score).toFixed(1)}</strong>
                            {typeof p.max_score === "number" ? ` / ${p.max_score}` : ""}
                          </span>
                          {p.last_scoring_reason ? (
                            <div className="stu-lc-reason-preview" title={p.last_scoring_reason}>
                              {p.last_scoring_reason.length > 72
                                ? `${p.last_scoring_reason.slice(0, 72)}…`
                                : p.last_scoring_reason}
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <span className="stu-lc-diff-muted">—</span>
                      )}
                    </td>
                    <td>
                      {p.difficulty_band ? (
                        <span className={`stu-lc-diff stu-lc-diff--${p.difficulty_band}`}>
                          {p.difficulty_band === "easy"
                            ? "Лёгкая"
                            : p.difficulty_band === "medium"
                              ? "Средняя"
                              : "Сложная"}
                          {typeof p.difficulty === "number" ? ` · ${p.difficulty}/10` : ""}
                        </span>
                      ) : (
                        <span className="stu-lc-diff-muted">—</span>
                      )}
                    </td>
                    <td>
                      <span className="stu-chip stu-chip--muted">{problemKindLabel(p.kind)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
