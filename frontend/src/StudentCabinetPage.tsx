import type { CSSProperties, FormEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { StudentDashboardAvatar } from "./components/StudentDashboardAvatar";
import {
  changeStudentPassword,
  deleteStudentAvatar,
  fetchStudentExamProspect,
  fetchStudentMe,
  fetchStudentMyCourses,
  fetchStudentProgress,
  fetchStudentStats,
  logoutStudent,
  patchStudentProfile,
  uploadStudentAvatar,
  type ExamProspectPayload,
  type StudentCourseRow,
  type StudentMe,
  type StudentProgressPayload,
  type StudentStatsPayload,
} from "./studentApi";
import { getStudentAccessToken } from "./studentAccessKey";
import { courseVisibilityLabel, friendlyHttpError, problemKindLabel, weakSkillLabel } from "./labels";

function weightedAvgFromKinds(stats: StudentStatsPayload): number {
  let w = 0;
  let s = 0;
  for (const row of stats.by_kind) {
    w += row.attempts;
    s += row.avg_score_ratio * row.attempts;
  }
  return w > 0 ? s / w : 0;
}

export function StudentCabinetPage() {
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [me, setMe] = useState<StudentMe | null>(null);
  const [courses, setCourses] = useState<StudentCourseRow[]>([]);
  const [stats, setStats] = useState<StudentStatsPayload | null>(null);
  const [progress, setProgress] = useState<StudentProgressPayload | null>(null);
  const [exam, setExam] = useState<ExamProspectPayload | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [avatarRev, setAvatarRev] = useState(0);
  const [nameDraft, setNameDraft] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [pwCurrent, setPwCurrent] = useState("");
  const [pwNew, setPwNew] = useState("");
  const [pwConfirm, setPwConfirm] = useState("");
  const [pwSaving, setPwSaving] = useState(false);
  const [pwOk, setPwOk] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    if (!getStudentAccessToken().trim()) {
      navigate("/login");
      return;
    }
    setErr(null);
    setLoading(true);
    try {
      const [profile, crs, st, ex, pr] = await Promise.all([
        fetchStudentMe(),
        fetchStudentMyCourses(),
        fetchStudentStats(),
        fetchStudentExamProspect(),
        fetchStudentProgress().catch(() => null),
      ]);
      setMe(profile);
      setNameDraft(profile.full_name);
      setCourses(crs.courses);
      setStats(st);
      setExam(ex);
      setProgress(pr);
      setAvatarRev((v) => v + 1);
    } catch (e) {
      const msg = friendlyHttpError(e);
      setErr(msg);
      if (/401|вход/i.test(msg)) {
        logoutStudent();
        navigate("/login");
      }
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  async function onSaveProfile() {
    const n = nameDraft.trim();
    if (!n || !me) return;
    setProfileSaving(true);
    setErr(null);
    try {
      const next = await patchStudentProfile({ full_name: n });
      setMe(next);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setProfileSaving(false);
    }
  }

  async function onPickAvatar(f: File | null) {
    if (!f || !me) return;
    setErr(null);
    try {
      const next = await uploadStudentAvatar(f);
      setMe(next);
      setAvatarRev((v) => v + 1);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function onRemoveAvatar() {
    if (!me) return;
    setErr(null);
    try {
      const next = await deleteStudentAvatar();
      setMe(next);
      setAvatarRev((v) => v + 1);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function onChangePassword(ev: FormEvent) {
    ev.preventDefault();
    setPwOk(null);
    if (pwNew.length < 8) {
      setErr("Новый пароль — не менее 8 символов.");
      return;
    }
    if (pwNew !== pwConfirm) {
      setErr("Новый пароль и подтверждение не совпадают.");
      return;
    }
    setPwSaving(true);
    setErr(null);
    try {
      await changeStudentPassword({ current_password: pwCurrent, new_password: pwNew });
      setPwCurrent("");
      setPwNew("");
      setPwConfirm("");
      setPwOk("Пароль обновлён.");
    } catch (e) {
      setErr(friendlyHttpError(e, "Не удалось сменить пароль."));
    } finally {
      setPwSaving(false);
    }
  }

  function onLogout() {
    logoutStudent();
    navigate("/login");
  }

  const maxAttempts = stats?.by_course.reduce((m, r) => Math.max(m, r.attempts), 0) ?? 0;
  const avgRing = stats ? Math.round(weightedAvgFromKinds(stats) * 100) : 0;

  return (
    <>
      {loading && !err && (
        <p className="ds-caption" style={{ marginBottom: "1rem" }}>
          Загрузка…
        </p>
      )}

      {err && <div className="ds-alert ds-alert--err ds-mb">{err}</div>}

      {!loading && me && (
        <>
          <section className="stu-dash-hero stu-card">
            <StudentDashboardAvatar
              fullName={me.full_name}
              hasAvatar={Boolean(me.has_avatar)}
              revision={avatarRev}
            />
            <div className="stu-dash-hero__body">
              <h1 className="stu-dash-hero__title">Профиль</h1>
              <p className="stu-dash-hero__sub">
                <span className="stu-dash-hero__name">{me.full_name}</span>
                <span className="stu-dash-meta"> @{me.username}</span>
                {me.study_group_title ? (
                  <span className="stu-dash-meta"> · группа «{me.study_group_title}»</span>
                ) : null}
              </p>

              <div className="stu-dash-profile">
                <label className="ds-label">
                  Как показываем ваше имя
                  <input className="ds-input" value={nameDraft} onChange={(ev) => setNameDraft(ev.target.value)} />
                </label>
                <div className="stu-dash-profile__row">
                  <button type="button" className="ds-btn ds-btn--primary ds-btn--sm" disabled={profileSaving || nameDraft.trim() === me.full_name} onClick={() => void onSaveProfile()}>
                    {profileSaving ? "Сохраняем…" : "Сохранить имя"}
                  </button>
                  <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => fileRef.current?.click()}>
                    Загрузить фото
                  </button>
                  {me.has_avatar ? (
                    <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => void onRemoveAvatar()}>
                      Убрать фото
                    </button>
                  ) : null}
                  <input
                    ref={fileRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    hidden
                    onChange={(ev) => void onPickAvatar(ev.target.files?.[0] ?? null)}
                  />
                </div>
              </div>

              <form className="stu-dash-profile ds-mt" onSubmit={(ev) => void onChangePassword(ev)}>
                <h2 className="stu-dash-h3" style={{ marginTop: 0 }}>
                  Смена пароля
                </h2>
                <label className="ds-label">
                  Текущий пароль
                  <input
                    className="ds-input"
                    type="password"
                    value={pwCurrent}
                    onChange={(ev) => setPwCurrent(ev.target.value)}
                    autoComplete="current-password"
                  />
                </label>
                <label className="ds-label">
                  Новый пароль
                  <input
                    className="ds-input"
                    type="password"
                    value={pwNew}
                    onChange={(ev) => setPwNew(ev.target.value)}
                    autoComplete="new-password"
                    minLength={8}
                  />
                </label>
                <label className="ds-label">
                  Подтверждение
                  <input
                    className="ds-input"
                    type="password"
                    value={pwConfirm}
                    onChange={(ev) => setPwConfirm(ev.target.value)}
                    autoComplete="new-password"
                    minLength={8}
                  />
                </label>
                <div className="stu-dash-profile__row">
                  <button type="submit" className="ds-btn ds-btn--primary ds-btn--sm" disabled={pwSaving || !pwCurrent || !pwNew}>
                    {pwSaving ? "Сохраняем…" : "Обновить пароль"}
                  </button>
                </div>
                {pwOk ? <p className="ds-caption" style={{ margin: "0.5rem 0 0" }}>{pwOk}</p> : null}
              </form>

              <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm stu-dash-logout" onClick={onLogout}>
                Выйти
              </button>
            </div>

            <div className="stu-dash-hero__ring-wrap" aria-hidden>
              <div
                className="stu-dash-ring"
                style={{ "--stu-pct": String(Math.min(100, Math.max(0, avgRing))) } as CSSProperties}
              />
              <div className="stu-dash-ring__label">
                <span className="stu-dash-ring__value">{avgRing}%</span>
                <span className="stu-dash-ring__cap">средняя успеваемость</span>
              </div>
            </div>
          </section>

          {stats ? (
            <section className="stu-dash-metrics">
              <div className="stu-metric-card">
                <div className="stu-metric-card__label">Отправки</div>
                <div className="stu-metric-card__value">{stats.totals.submissions}</div>
              </div>
              <div className="stu-metric-card">
                <div className="stu-metric-card__label">Курсов с активностью</div>
                <div className="stu-metric-card__value">{stats.totals.courses_touched}</div>
              </div>
              <div className="stu-metric-card">
                <div className="stu-metric-card__label">Фокус</div>
                <div className="stu-metric-card__value stu-metric-card__value--sm">
                  {weakSkillLabel(stats.weak_skill_kind)}
                </div>
              </div>
            </section>
          ) : null}
        </>
      )}

      {progress && (
        <div className="stu-card ds-mb stu-rise-in">
          <h2 className="stu-dash-h2">Рейтинг и история</h2>
          <p className="t-page__sub stu-dash-lead">
            Условный рейтинг по проверенным работам: <strong>{progress.elo_rating}</strong>.
          </p>

          <h3 className="stu-dash-h3">Решённые задачи</h3>
          {progress.solved.length === 0 ? (
            <p className="ds-caption ds-mb">Пока ни одной задачи на полный балл.</p>
          ) : (
            <div className="stu-lc-wrap ds-mb">
              <table className="stu-lc-table stu-progress-table">
                <thead>
                  <tr>
                    <th>Задача</th>
                    <th>Курс</th>
                    <th>Рейтинг</th>
                    <th>Балл</th>
                  </tr>
                </thead>
                <tbody>
                  {progress.solved.map((s) => (
                    <tr key={s.problem_id}>
                      <td>
                        <Link className="stu-lc-link" to={`/c/${encodeURIComponent(s.course_slug)}/p/${s.problem_id}`}>
                          {s.title}
                        </Link>
                        <div className="ds-caption">
                          {problemKindLabel(s.kind)}
                          {typeof s.difficulty === "number" ? ` · сложность ${s.difficulty}/10` : ""}
                        </div>
                      </td>
                      <td>
                        {(() => {
                          const ct = courses.find((c) => c.slug === s.course_slug)?.title;
                          return (
                            <Link className="ds-link-bold" to={`/c/${encodeURIComponent(s.course_slug)}`}>
                              {ct ?? "Курс"}
                            </Link>
                          );
                        })()}
                      </td>
                      <td>
                        <span className="stu-elo-pill">{s.elo_after}</span>
                      </td>
                      <td>
                        {s.best_score} / {s.max_score}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3 className="stu-dash-h3">История попыток</h3>
          {progress.attempts.length === 0 ? (
            <p className="ds-caption">Отправок ещё не было.</p>
          ) : (
            <div className="stu-lc-wrap">
              <table className="stu-lc-table stu-progress-table">
                <thead>
                  <tr>
                    <th>Время</th>
                    <th>Задача</th>
                    <th>Балл</th>
                    <th>Комментарий проверки</th>
                  </tr>
                </thead>
                <tbody>
                  {progress.attempts.map((a) => (
                    <tr key={a.id}>
                      <td className="stu-progress-time">
                        {a.created_at ? new Date(a.created_at).toLocaleString() : "—"}
                      </td>
                      <td>
                        <Link className="stu-lc-link" to={`/c/${encodeURIComponent(a.course_slug)}/p/${a.problem_id}`}>
                          {a.title}
                        </Link>
                        <div className="ds-caption">{problemKindLabel(a.kind)}</div>
                      </td>
                      <td>
                        {a.score != null ? `${a.score} / ${a.max_score}` : "—"}
                        {a.passed ? <span className="stu-pass-ok"> · зачёт</span> : null}
                      </td>
                      <td className="stu-progress-reason">
                        {a.scoring_reason ? (
                          a.scoring_reason
                        ) : (
                          <span className="stu-lc-diff-muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {stats && stats.totals.submissions >= 0 && (
        <div className="stu-card ds-mb">
          <h2 className="stu-dash-h2">Прогресс по заданиям</h2>
          <p className="t-page__sub stu-dash-lead">
            Всего отправок: <strong>{stats.totals.submissions}</strong>, затронуто курсов:{" "}
            <strong>{stats.totals.courses_touched}</strong>
          </p>
          {stats.hints_ru.length > 0 ? (
            <ul className="stu-dash-hints">
              {stats.hints_ru.map((h) => (
                <li key={h.slice(0, 80)}>{h}</li>
              ))}
            </ul>
          ) : null}

          <div className="stu-dash-chart-block">
            <h3 className="stu-dash-h3">По типам задач</h3>
            <div className="stu-bars">
              {stats.by_kind.map((row) => (
                <div key={row.kind} className="stu-bar-row">
                  <div className="stu-bar-row__head">
                    <span>{problemKindLabel(row.kind)}</span>
                    <span className="stu-bar-row__muted">{Math.round(row.avg_score_ratio * 100)}% · попытки {row.attempts}</span>
                  </div>
                  <div className="stu-bar-track">
                    <div className="stu-bar-fill stu-bar-fill--accent" style={{ width: `${Math.round(row.avg_score_ratio * 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="stu-dash-chart-block">
            <h3 className="stu-dash-h3">По курсам</h3>
            <div className="stu-bars">
              {stats.by_course.map((row) => {
                const loadPct = maxAttempts > 0 ? Math.round((row.attempts / maxAttempts) * 100) : 0;
                return (
                  <div key={row.slug} className="stu-bar-row">
                    <div className="stu-bar-row__head">
                      <span>{row.title}</span>
                      <span className="stu-bar-row__muted">
                        {Math.round(row.avg_score_ratio * 100)}% · отпр. {row.attempts}
                      </span>
                    </div>
                    <div className="stu-bar-track">
                      <div className="stu-bar-fill stu-bar-fill--soft" style={{ width: `${loadPct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {exam && exam.courses.length > 0 && (
        <div className="stu-card ds-mb">
          <h2 className="stu-dash-h2">
            Прогноз перед экзаменом <span className="ds-caption">черновик</span>
          </h2>
          <p className="t-page__sub">{exam.note}</p>
          <div className="stu-exam-grid">
            {exam.courses.map((c) => (
              <div key={c.slug} className="stu-exam-card">
                <div className="stu-exam-card__title">{c.title}</div>
                <div className="stu-exam-card__forecast">
                  {c.exam_pass_probability == null ? c.forecast_stub : `${Math.round(c.exam_pass_probability * 100)}%`}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && (
        <div className="stu-card">
          <h2 className="stu-dash-h2">Ваши курсы</h2>
          {courses.length === 0 ? (
            <p className="ds-empty">Пока нет доступных курсов. Обратитесь к преподавателю.</p>
          ) : (
            <div className="stu-course-grid">
              {courses.map((c) => (
                <Link key={c.slug} className="stu-course-tile" to={`/c/${encodeURIComponent(c.slug)}`}>
                  <div className="stu-course-tile__mark" aria-hidden />
                  <div className="stu-course-tile__title">{c.title}</div>
                  <div className="stu-course-tile__meta">
                    {courseVisibilityLabel(c.visibility_mode) || "Курс"}
                  </div>
                  {c.instructor_name?.trim() ? (
                    <div className="stu-course-tile__teacher">
                      Преподаватель: {c.instructor_name.trim()}
                    </div>
                  ) : null}
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
