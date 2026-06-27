import { Link, Outlet, useLocation, useMatch } from "react-router-dom";

import { cabinetHomeHref } from "../cabinetPath";
import { getStudentAccessToken } from "../studentAccessKey";

export function StudentLayout() {
  const location = useLocation();
  const hideLoginNav = cabinetHomeHref() !== "/login";
  const showStudentChat = !!getStudentAccessToken().trim();
  const isChatRoute = Boolean(useMatch("/student/chat"));
  const isProblemRoute = Boolean(useMatch("/c/:slug/p/:problemId"));
  void location.pathname;

  return (
    <div
      className={`stu-root${isChatRoute ? " stu-root--chat-fs" : ""}${isProblemRoute ? " stu-root--problem-fs" : ""}`}
    >
      <header className="stu-topbar">
        <div className="stu-topbar__inner">
          <Link to="/" className="stu-brand">
            <span className="stu-brand__mark" aria-hidden />
            <span className="stu-brand__text">BSTU Learn</span>
          </Link>
          <nav className="stu-nav">
            <Link to="/">Главная</Link>
            <Link to="/cabinet">Профиль</Link>
            {showStudentChat ? <Link to="/student/chat">Чат ИИ</Link> : null}
            {!hideLoginNav && <Link to="/login">Вход</Link>}
          </nav>
        </div>
      </header>
      <main
        className={`stu-main${isChatRoute ? " stu-main--chat" : ""}${isProblemRoute ? " stu-main--problem-fs" : ""}`}
      >
        <Outlet />
      </main>
    </div>
  );
}
