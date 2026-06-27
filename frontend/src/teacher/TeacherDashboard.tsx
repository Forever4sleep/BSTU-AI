import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { platformGetJson } from "../platformApi";
import { useTeacherAuth } from "./TeacherAuthContext";

type DashboardCourse = {
  course_id: string;
  slug: string;
  title: string;
  visibility_mode: string;
  published_problems: number;
  submissions_total: number;
  successful_submissions: number;
  distinct_submitters: number;
  popular_problem_title?: string | null;
  submissions_week: number;
  avg_attempt_score_pct?: number | null;
};

type DashboardResp = {
  totals: { registry_students: number; registry_groups: number; courses: number };
  courses: DashboardCourse[];
  study_groups_activity: { group_title: string; submissions_attempts: number; successful_submissions: number }[];
};

function shortLabel(s: string, n = 36) {
  const t = s.trim();
  return t.length <= n ? t : `${t.slice(0, n)}…`;
}

function DashHBar({
  label,
  value,
  max,
  variant = "violet",
}: {
  label: string;
  value: number;
  max: number;
  variant?: "violet" | "cyan";
}) {
  const pct = max > 0 ? Math.min(100, (100 * value) / max) : 0;
  return (
    <div className={`t-dash-hbar t-dash-hbar--${variant}`} title={label}>
      <div className="t-dash-hbar__label">{shortLabel(label, 40)}</div>
      <div className="t-dash-hbar__track" role="img" aria-label={`${label}: ${value}`}>
        <div className="t-dash-hbar__fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="t-dash-hbar__num">{value}</div>
    </div>
  );
}

function SuccessRing({ percent }: { percent: number }) {
  const p = Math.max(0, Math.min(100, percent));
  return (
    <div
      className="t-dash-ring"
      style={{
        background: `conic-gradient(var(--accent2) ${p}%, rgba(255,255,255,0.07) ${p}%)`,
      }}
      role="img"
      aria-label={`Зачётных попыток ${Math.round(p)} процентов`}
    >
      <div className="t-dash-ring__hole">
        <strong className="t-dash-ring__pct">{Math.round(p)}%</strong>
        <span className="t-dash-ring__sub">зачётных попыток</span>
      </div>
    </div>
  );
}

export function TeacherDashboard() {
  const { apiKey } = useTeacherAuth();
  const [dash, setDash] = useState<DashboardResp | null>(null);
  const [dashErr, setDashErr] = useState<string | null>(null);

  useEffect(() => {
    if (!apiKey) return;
    let cancelled = false;
    (async () => {
      setDashErr(null);
      try {
        const d = await platformGetJson<DashboardResp>("/api/platform/analytics/dashboard", apiKey);
        if (!cancelled) setDash(d);
      } catch (e) {
        if (!cancelled) setDashErr(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiKey]);

  const courseBarMax = useMemo(() => {
    if (!dash?.courses.length) return 1;
    return Math.max(1, ...dash.courses.map((c) => c.submissions_total));
  }, [dash]);

  const groupBarMax = useMemo(() => {
    if (!dash?.study_groups_activity.length) return 1;
    return Math.max(1, ...dash.study_groups_activity.map((g) => g.successful_submissions));
  }, [dash]);

  const weekBarMax = useMemo(() => {
    if (!dash?.courses.length) return 1;
    return Math.max(1, ...dash.courses.map((c) => c.submissions_week));
  }, [dash]);

  const aggregate = useMemo(() => {
    if (!dash) return { sub: 0, ok: 0 };
    const sub = dash.courses.reduce((a, c) => a + c.submissions_total, 0);
    const ok = dash.courses.reduce((a, c) => a + c.successful_submissions, 0);
    return { sub, ok };
  }, [dash]);

  const successPct = aggregate.sub > 0 ? (100 * aggregate.ok) / aggregate.sub : 0;

  return (
    <div className="t-page">
      <header className="t-page__head">
        <h1 className="t-page__title">Обзор</h1>
        <p className="t-page__sub">
          Визуальная сводка по вашим курсам. Реестр групп и студентов ведётся администратором — раздел{" "}
          <Link to="/admin" className="ds-link-bold">
            /admin
          </Link>
          . Профиль преподавателя —{" "}
          <Link to="/teacher/cabinet" className="ds-link-bold">
            здесь
          </Link>
          .
        </p>
      </header>

      <div className="ds-grid ds-grid--4">
        <div className="ds-stat ds-animate-in" style={{ animationDelay: "0ms" }}>
          <div className="ds-stat__label">В реестре студентов</div>
          <div className="ds-stat__value">{dash ? dash.totals.registry_students : "—"}</div>
          <div className="ds-caption">Платформа (ключи админа)</div>
        </div>
        <div className="ds-stat ds-animate-in" style={{ animationDelay: "40ms" }}>
          <div className="ds-stat__label">Групп в системе</div>
          <div className="ds-stat__value">{dash ? dash.totals.registry_groups : "—"}</div>
        </div>
        <div className="ds-stat ds-animate-in" style={{ animationDelay: "80ms" }}>
          <div className="ds-stat__label">Ваших курсов</div>
          <div className="ds-stat__value">{dash ? dash.totals.courses : "—"}</div>
        </div>
        <div className="ds-stat ds-stat--accent ds-animate-in" style={{ animationDelay: "120ms" }}>
          <div className="ds-stat__label">Дальше</div>
          <div className="ds-stat__value" style={{ fontSize: "1rem" }}>
            <Link to="/teacher/courses" className="ds-link-bold">
              Курсы →
            </Link>
          </div>
        </div>
      </div>

      {dashErr && (
        <div className="ds-alert ds-alert--err ds-mb" style={{ marginTop: "1rem" }}>
          Не удалось загрузить дашборд: {dashErr}
        </div>
      )}

      {!dashErr && dash && dash.courses.length > 0 && (
        <div className="ds-card ds-mt t-dash-visual">
          <div className="t-dash-visual__head">
            <div>
              <h2 className="t-page__h2 t-page__h2--flush">Активность по курсам</h2>
              <p className="ds-caption ds-mb0">Длина полосы — число отправок решений (все время).</p>
            </div>
            <SuccessRing percent={successPct} />
          </div>
          <div className="t-dash-hbar-list">
            {dash.courses.map((c) => (
              <DashHBar key={c.course_id} label={c.title} value={c.submissions_total} max={courseBarMax} variant="violet" />
            ))}
          </div>

          <h3 className="t-page__h2" style={{ fontSize: "1.05rem", marginTop: "1.35rem" }}>
            «Пульс» за последние 7 дней
          </h3>
          <p className="ds-caption ds-mb">Высота столбика — число новых отправок по курсу за неделю.</p>
          <div className="t-dash-spark" role="list">
            {dash.courses.map((c) => {
              const maxPx = 112;
              const hPx =
                weekBarMax > 0 ? Math.max(8, Math.round((maxPx * c.submissions_week) / weekBarMax)) : 8;
              return (
                <div key={c.course_id} className="t-dash-spark__col" title={`${c.title}: ${c.submissions_week} за неделю`}>
                  <div className="t-dash-spark__bar" style={{ height: `${hPx}px` }} />
                  <div className="t-dash-spark__cap">{c.submissions_week}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!dashErr && dash && dash.study_groups_activity.length > 0 && (
        <div className="ds-card ds-mt">
          <h2 className="t-page__h2">Группы и зачёты</h2>
          <p className="ds-caption ds-mb">
            Успешные отправки (≈ полный балл) по студентам группы на <strong>ваших</strong> курсах. Длина — относительно
            лидера.
          </p>
          <div className="t-dash-hbar-list">
            {dash.study_groups_activity
              .slice()
              .sort((a, b) => b.successful_submissions - a.successful_submissions)
              .map((g) => (
                <DashHBar
                  key={g.group_title}
                  label={g.group_title}
                  value={g.successful_submissions}
                  max={groupBarMax}
                  variant="cyan"
                />
              ))}
          </div>
          <p className="ds-caption ds-mt">
            Всего попыток по группам (включая незачёт):{" "}
            {dash.study_groups_activity.reduce((a, g) => a + g.submissions_attempts, 0)}
          </p>
        </div>
      )}

      {!dashErr && dash && dash.courses.length > 0 && (
        <div className="ds-card ds-mt">
          <h2 className="t-page__h2">Карточки курсов</h2>
          <div className="ds-grid ds-grid--2">
            {dash.courses.map((c) => {
              const share =
                c.submissions_total > 0 ? Math.round((100 * c.successful_submissions) / c.submissions_total) : null;
              return (
                <div key={c.course_id} className="ds-card ds-card--soft">
                  <h3 className="t-page__h2" style={{ fontSize: "1.06rem", marginBottom: "0.25rem" }}>
                    {c.title}
                  </h3>
                  <p className="ds-caption ds-mb">
                    <Link to={`/teacher/courses/${c.course_id}`}>Материалы и доступ групп</Link> ·{" "}
                    <code className="ds-code">{c.visibility_mode}</code>
                  </p>
                  <div className="t-dash-mini">
                    <div>
                      <span className="t-dash-mini__n">{c.published_problems}</span>
                      <span className="t-dash-mini__l">задач</span>
                    </div>
                    <div>
                      <span className="t-dash-mini__n">{c.distinct_submitters}</span>
                      <span className="t-dash-mini__l">ключей</span>
                    </div>
                    <div>
                      <span className="t-dash-mini__n">{share ?? "—"}</span>
                      <span className="t-dash-mini__l">% зачёта</span>
                    </div>
                  </div>
                  <p className="ds-caption ds-mt">
                    Хит по попыткам: <strong>{c.popular_problem_title ?? "—"}</strong>
                  </p>
                  {c.avg_attempt_score_pct != null && (
                    <p className="ds-caption">Средний % от макс. за попытку: {c.avg_attempt_score_pct}%</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="ds-grid ds-grid--2 ds-mt">
        <div className="ds-card ds-card--soft t-page__card">
          <h2 className="t-page__h2">Чат ИИ</h2>
          <p className="ds-caption ds-mb">RAG по выбранному курсу, модель на сервере.</p>
          <Link to="/teacher/chat" className="ds-btn ds-btn--primary">
            Открыть чат ИИ →
          </Link>
        </div>
        <div className="ds-card ds-card--soft">
          <h2 className="t-page__h2">Быстрый старт</h2>
          <ol className="ds-steps">
            <li>Админ создаёт группы и студентов с ключами.</li>
            <li>Вы настраиваете вкладку «Доступ» у каждого курса — какие группы видят задания.</li>
            <li>
              <Link to="/teacher/cabinet">Профиль</Link> — ФИО и отображаемое имя.
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
