import { FormEvent, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { friendlyHttpError } from "./labels";
import { setAdminAccessToken } from "./adminSession";
import { cabinetHomeHref, cabinetPathAfterUnifiedLogin, purgeAllCabinetSessions } from "./cabinetPath";
import { setStudentSession } from "./studentAccessKey";
import { unifiedSessionLogin } from "./unifiedAuthApi";
import { useTeacherAuth } from "./teacher/TeacherAuthContext";

export function UnifiedLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { clearSession: clearTeacher, setApiKey: setTeacherToken } = useTeacherAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const storedFrom =
    typeof location.state === "object" && location.state && "from" in location.state
      ? (location.state as { from?: string }).from
      : undefined;

  const nextIfAuthed = cabinetHomeHref();

  useEffect(() => {
    const h = cabinetHomeHref();
    if (h !== "/login") navigate(h, { replace: true });
  }, [navigate]);

  /** Уже есть любая сохранённая сессия — не показываем форму, уводим в профиль. */
  if (nextIfAuthed !== "/login") {
    return (
      <div className="t-login">
        <div className="t-login__card ds-card ds-animate-in" style={{ maxWidth: 420 }}>
          <p className="t-page__sub" style={{ margin: 0 }}>
            Перенаправляем…
          </p>
        </div>
      </div>
    );
  }

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    setErr(null);
    const u = username.trim().toLowerCase();
    if (!u || !password) return;
    setBusy(true);
    try {
      purgeAllCabinetSessions(clearTeacher);

      const out = await unifiedSessionLogin(u, password);
      switch (out.role) {
        case "platform_admin":
          setAdminAccessToken(out.access_token);
          navigate(cabinetPathAfterUnifiedLogin("platform_admin", storedFrom), { replace: true });
          break;
        case "instructor":
          setTeacherToken(out.access_token);
          navigate(cabinetPathAfterUnifiedLogin("instructor", storedFrom), { replace: true });
          break;
        case "student": {
          const tok = out.access_token.trim();
          const key = (out.student_access_key ?? "").trim();
          setStudentSession(tok, key);
          navigate(cabinetPathAfterUnifiedLogin("student", storedFrom), { replace: true });
          break;
        }
        default:
          throw new Error("Неизвестная роль после входа.");
      }
    } catch (e) {
      purgeAllCabinetSessions(clearTeacher);
      setErr(friendlyHttpError(e, "Не удалось войти."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="t-login">
      <div className="t-login__card ds-card ds-animate-in" style={{ maxWidth: 460 }}>
        <h1 className="t-login__h">Вход</h1>
        <p className="ds-caption" style={{ marginTop: "-0.25rem", lineHeight: 1.5 }}>
          Введите те же учётные данные, которые вы получили у администратора или своего преподавателя —
          платформа сама распознает роль и откроет нужный раздел (студент, преподаватель или администратор
          платформы).
        </p>

        {err && <div className="ds-alert ds-alert--err">{err}</div>}

        <form className="ds-form ds-mt" onSubmit={(ev) => void onSubmit(ev)} autoComplete="on">
          <label className="ds-label">
            Логин
            <input
              className="ds-input"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(ev) => setUsername(ev.target.value)}
              required
            />
          </label>
          <label className="ds-label">
            Пароль
            <input
              className="ds-input"
              type="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(ev) => setPassword(ev.target.value)}
              required
            />
          </label>
          <button type="submit" className="ds-btn ds-btn--primary" disabled={busy}>
            {busy ? "Вход…" : "Войти"}
          </button>
        </form>

        <div className="ds-caption ds-mt" style={{ lineHeight: 1.6 }}>
          <button
            type="button"
            className="ds-link-bold"
            style={{ padding: 0, border: 0, background: "transparent" }}
            onClick={() => purgeAllCabinetSessions(clearTeacher)}
          >
            Выйти из всех аккаунтов на этом устройстве
          </button>
          <br />
          <Link to="/">На главную</Link>
          {" · "}
          <Link to="/cabinet">Профиль</Link>
        </div>
      </div>
    </div>
  );
}
