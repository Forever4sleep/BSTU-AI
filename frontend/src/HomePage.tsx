import { FormEvent, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { cabinetHomeHref, purgeAllCabinetSessions } from "./cabinetPath";
import { courseVisibilityLabel, friendlyHttpError } from "./labels";
import { fetchStudentMyCourses, type StudentCourseRow } from "./studentApi";
import { getStudentAccessToken } from "./studentAccessKey";
import { useTeacherAuth } from "./teacher/TeacherAuthContext";

export function HomePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { clearSession: clearTeacher } = useTeacherAuth();
  const [courseId, setCourseId] = useState("");
  const [courses, setCourses] = useState<StudentCourseRow[] | null>(null);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [coursesErr, setCoursesErr] = useState<string | null>(null);

  const cabinet = cabinetHomeHref();
  const isAuthedSomeone = cabinet !== "/login";

  useEffect(() => {
    void location.pathname;
    const tok = getStudentAccessToken().trim();
    if (!tok) {
      setCourses(null);
      setCoursesLoading(false);
      setCoursesErr(null);
      return;
    }
    let cancelled = false;
    setCoursesLoading(true);
    setCoursesErr(null);
    void fetchStudentMyCourses()
      .then((d) => {
        if (!cancelled) setCourses(d.courses);
      })
      .catch((e: unknown) => {
        if (!cancelled) setCoursesErr(friendlyHttpError(e));
      })
      .finally(() => {
        if (!cancelled) setCoursesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  function submit(ev: FormEvent) {
    ev.preventDefault();
    const s = courseId.trim().toLowerCase();
    if (!s) return;
    navigate(`/c/${encodeURIComponent(s)}`);
  }

  function onLogout() {
    purgeAllCabinetSessions(clearTeacher);
    navigate("/login", { replace: true });
  }

  return (
    <>
      <header className="stu-hero">
        <h1 className="stu-hero__title">Учебные курсы</h1>
        <p className="stu-hero__sub">
          Открывайте курсы из списка ниже или найдите курс по <strong>идентификатору</strong>, который выдал преподаватель. Задачи с автопроверкой кода,
          тестами и текстовыми форматами.
        </p>
      </header>

      {courses && courses.length > 0 ? (
        <section className="stu-card ds-mb">
          <h2 className="stu-dash-h2" style={{ marginTop: 0 }}>
            Доступные вам курсы
          </h2>
          <p className="t-page__sub" style={{ marginTop: "-0.15rem", marginBottom: "1rem" }}>
            Те же курсы, что и в профиле.
          </p>
          <div className="stu-course-grid">
            {courses.map((c) => (
              <Link key={c.slug} className="stu-course-tile" to={`/c/${encodeURIComponent(c.slug)}`}>
                <div className="stu-course-tile__mark" aria-hidden />
                <div className="stu-course-tile__title">{c.title}</div>
                <div className="stu-course-tile__meta">{courseVisibilityLabel(c.visibility_mode) || "Курс"}</div>
                {c.instructor_name?.trim() ? (
                  <div className="stu-course-tile__teacher">
                    Преподаватель: {c.instructor_name.trim()}
                  </div>
                ) : null}
              </Link>
            ))}
          </div>
        </section>
      ) : coursesLoading ? (
        <p className="ds-caption ds-mb">Загружаем ваши курсы…</p>
      ) : getStudentAccessToken().trim() && coursesErr ? (
        <div className="ds-alert ds-alert--err ds-mb">{coursesErr}</div>
      ) : null}

      <div className="stu-card">
        <h2 className="stu-dash-h2" style={{ marginTop: 0 }}>
          Поиск по идентификатору курса
        </h2>
        <form className="stu-form-row" onSubmit={submit}>
          <label className="ds-label" style={{ flex: "0 1 280px" }}>
            Идентификатор курса
            <input
              className="ds-input"
              value={courseId}
              onChange={(e) => setCourseId(e.target.value)}
              placeholder="например, gen-ai"
              autoComplete="off"
            />
          </label>
          <button type="submit" className="ds-btn ds-btn--primary">
            Открыть курс
          </button>
        </form>
        <div className="stu-home-foot ds-mt" style={{ display: "flex", flexWrap: "wrap", gap: "0.65rem", alignItems: "center" }}>
          {isAuthedSomeone ? (
            <>
              <Link className="ds-btn ds-btn--ghost ds-btn--sm" to={cabinet}>
                Профиль
              </Link>
              <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={onLogout}>
                Выйти
              </button>
            </>
          ) : (
            <>
              <Link className="ds-btn ds-btn--primary ds-btn--sm" to="/login">
                Вход
              </Link>
              <Link className="ds-btn ds-btn--ghost ds-btn--sm" to="/cabinet">
                Профиль
              </Link>
            </>
          )}
        </div>
      </div>
    </>
  );
}
