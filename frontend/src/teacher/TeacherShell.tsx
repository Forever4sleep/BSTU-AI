import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";

import { useTeacherAuth } from "./TeacherAuthContext";

const navCls = ({ isActive }: { isActive: boolean }) =>
  `t-side__link ${isActive ? "t-side__link--active" : ""}`;

export function TeacherShell() {
  const { apiKey, clearSession } = useTeacherAuth();
  const loc = useLocation();

  /** Полноэкранный режим как Open WebUI: без max-width у контента и без лишних отступов у main. */
  const fullWorkspaceChat =
    loc.pathname === "/teacher/chat" || loc.pathname.startsWith("/teacher/chat/");
  const draftReviewWorkspace = /\/teacher\/courses\/[^/]+\/drafts\//.test(loc.pathname);

  if (!apiKey) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }

  return (
    <div
      className={`t-root${fullWorkspaceChat ? " t-root--chat-fs" : ""}${draftReviewWorkspace ? " t-root--draft-fs" : ""}`}
    >
      <aside className="t-side">
        <div className="t-side__brand">
          <span className="stu-brand__mark t-side__mark" aria-hidden />
          <div>
            <div className="t-side__title">Преподаватель</div>
            <div className="t-side__sub">BSTU Platform</div>
          </div>
        </div>
        <nav className="t-side__nav">
          <NavLink to="/teacher" end className={navCls}>
            Обзор
          </NavLink>
          <NavLink to="/teacher/cabinet" className={navCls}>
            Профиль
          </NavLink>
          <NavLink to="/teacher/courses" className={navCls}>
            Курсы
          </NavLink>
          <NavLink to="/teacher/chat" className={navCls}>
            Чат ИИ
          </NavLink>
        </nav>
        <div className="t-side__foot">
          <NavLink to="/" className="t-side__link t-side__link--ghost">
            ← На главную
          </NavLink>
          <button type="button" className="ds-btn ds-btn--ghost ds-btn--block" onClick={clearSession}>
            Выйти
          </button>
        </div>
      </aside>
      <div
        className={`t-main${fullWorkspaceChat ? " t-main--chat-fs" : ""}${draftReviewWorkspace ? " t-main--draft-split" : ""}`}
      >
        <Outlet />
      </div>
    </div>
  );
}
