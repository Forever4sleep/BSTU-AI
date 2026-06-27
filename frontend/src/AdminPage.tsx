import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { getAdminAccessToken } from "./adminSession";
import { purgeAllCabinetSessions } from "./cabinetPath";
import {
  adminCreateInstructor,
  adminDelete,
  adminGetJson,
  adminListStudyGroups,
  adminPatchJson,
  adminPostJson,
  adminDeleteStudyGroup,
  adminPostStudyGroup,
} from "./platformApi";
import type { PlatformStudentCreatedOut, PlatformStudentOut, StudyGroupOut } from "./teacher/types";
import { useTeacherAuth } from "./teacher/TeacherAuthContext";

type AdminTab = "instructor" | "groups" | "students";

function adminTokenReady(): boolean {
  return Boolean(getAdminAccessToken().trim());
}

export function AdminPage() {
  const navigate = useNavigate();
  const { clearSession: clearTeacher } = useTeacherAuth();
  const [tab, setTab] = useState<AdminTab>("instructor");

  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const [groups, setGroups] = useState<StudyGroupOut[]>([]);
  const [newGroupTitle, setNewGroupTitle] = useState("");

  const [students, setStudents] = useState<PlatformStudentOut[]>([]);
  const [newStudentName, setNewStudentName] = useState("");
  const [newStudentGroupId, setNewStudentGroupId] = useState("");

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [credentialFlash, setCredentialFlash] = useState<{
    username: string | null;
    password: string | null;
    access_key: string;
  } | null>(null);

  useEffect(() => {
    if (!adminTokenReady()) navigate("/login", { replace: true });
  }, [navigate]);

  const loadGroups = useCallback(async () => {
    if (!adminTokenReady()) return;
    const g = await adminListStudyGroups();
    setGroups(g);
    setNewStudentGroupId((prev) => (prev === "" && g[0] ? g[0].id : prev));
  }, []);

  const loadStudents = useCallback(async () => {
    if (!adminTokenReady()) return;
    const s = await adminGetJson<PlatformStudentOut[]>("/api/platform/admin/students");
    setStudents(s);
  }, []);

  useEffect(() => {
    if (!adminTokenReady()) return;
    if (tab !== "groups" && tab !== "students") return;
    void (async () => {
      try {
        setErr(null);
        if (tab === "groups") await loadGroups();
        if (tab === "students") {
          await loadGroups();
          await loadStudents();
        }
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [tab, loadGroups, loadStudents]);

  async function onCreateInstructor(ev: FormEvent) {
    ev.preventDefault();
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      await adminCreateInstructor({
        display_name: displayName.trim(),
        username: username.trim(),
        password,
      });
      setMsg("Преподаватель создан. Логин и пароль передайте отдельным каналом.");
      setPassword("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onAddGroup(ev: FormEvent) {
    ev.preventDefault();
    if (!newGroupTitle.trim()) return;
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      await adminPostStudyGroup(newGroupTitle.trim());
      setNewGroupTitle("");
      setMsg("Группа создана.");
      await loadGroups();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onAddStudent(ev: FormEvent) {
    ev.preventDefault();
    if (!newStudentName.trim()) return;
    setErr(null);
    setCredentialFlash(null);
    setBusy(true);
    try {
      const body: Record<string, unknown> = { full_name: newStudentName.trim() };
      const gid = newStudentGroupId.trim();
      if (gid) body.study_group_id = gid;
      const created = await adminPostJson<PlatformStudentCreatedOut>("/api/platform/admin/students", body);
      setNewStudentName("");
      setCredentialFlash({
        username: created.username ?? null,
        password: created.initial_password_plain ?? null,
        access_key: created.access_key,
      });
      setMsg("Студент создан — сохраните логин и пароль (пароль больше не показывается).");
      await loadStudents();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function rotateKey(id: string) {
    if (!confirm("Выдать студенту новый ключ доступа?")) return;
    try {
      await adminPostJson<{ access_key: string }>(`/api/platform/admin/students/${encodeURIComponent(id)}/rotate-access-key`, {});
      await loadStudents();
      setMsg("Ключ обновлён.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function delStudent(id: string) {
    if (!confirm("Удалить студента?")) return;
    try {
      await adminDelete(`/api/platform/admin/students/${encodeURIComponent(id)}`);
      await loadStudents();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function patchStudentUsername(student: PlatformStudentOut) {
    const v = window.prompt(
      `Логин для единого входа /login (латиница, цифры, точка, дефис, подчёркивание). Текущий: ${student.username ?? "нет"}`,
      student.username ?? "",
    );
    if (v === null) return;
    const eu = v.trim().toLowerCase();
    if (!eu) {
      setErr("Логин не может быть пустым.");
      return;
    }
    setErr(null);
    try {
      await adminPatchJson<PlatformStudentOut>(`/api/platform/admin/students/${encodeURIComponent(student.id)}`, {
        username: eu,
      });
      setMsg("Логин обновлён. Если пароль студент забыл или не был задан — нажмите «Пароль».");
      await loadStudents();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function resetStudentPw(student: PlatformStudentOut) {
    if (!student.username?.trim()) {
      setErr("Сначала задайте логин студента (кнопка «Логин» в строке студента).");
      return;
    }
    if (!confirm("Сгенерировать новый пароль для студента? Старый пароль перестанет действовать.")) return;
    setErr(null);
    try {
      const r = await adminPostJson<{ initial_password_plain: string }>(
        `/api/platform/admin/students/${encodeURIComponent(student.id)}/reset-password`,
        {},
      );
      setCredentialFlash({
        username: student.username ?? null,
        password: r.initial_password_plain ?? null,
        access_key: student.access_key,
      });
      setMsg("Пароль выдан заново — передайте данные студенту (окно ниже).");
      await loadStudents();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function delGroup(id: string) {
    if (!confirm("Удалить группу? Студенты останутся без группы.")) return;
    try {
      await adminDeleteStudyGroup(id);
      await loadGroups();
      await loadStudents();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="t-login">
      <div className="t-login__card ds-card ds-animate-in" style={{ maxWidth: 980, width: "100%" }}>
        <h1 className="t-login__h">Администратор платформы</h1>
        <p className="ds-caption ds-mb">
          Создание преподавателей, учебных групп и студентов. Логин студента задаётся автоматически как{" "}
          <code className="ds-code ds-code--sm">{"{группа}_{фио}"}</code> (транслит). Пароль студента генерируется на сервере и показывается один
          раз ниже. Преподаватель настраивает привязку групп к курсам (вкладка «Доступ»). Если в таблице у студента нет логина (старые записи после
          миграций) или вход не принимает пароль — задайте логин кнопкой «Логин», затем «Пароль».
        </p>
        <p className="ds-caption ds-mb" style={{ marginTop: "-0.35rem" }}>
          <button
            type="button"
            className="ds-btn ds-btn--ghost ds-btn--sm"
            onClick={() => {
              purgeAllCabinetSessions(clearTeacher);
              navigate("/login");
            }}
          >
            Выйти из админки
          </button>
        </p>

        <div className="ds-tabs ds-mt">
          <button type="button" className={`ds-tab ${tab === "instructor" ? "ds-tab--active" : ""}`} onClick={() => setTab("instructor")}>
            Преподаватели
          </button>
          <button type="button" className={`ds-tab ${tab === "groups" ? "ds-tab--active" : ""}`} onClick={() => setTab("groups")}>
            Группы
          </button>
          <button type="button" className={`ds-tab ${tab === "students" ? "ds-tab--active" : ""}`} onClick={() => setTab("students")}>
            Студенты
          </button>
        </div>

        {err && <div className="ds-alert ds-alert--err ds-mt">{err}</div>}
        {msg && (
          <div className="ds-alert ds-alert--ok ds-mt">
            {msg}{" "}
            <button type="button" className="ds-link-bold" onClick={() => setMsg(null)}>
              Скрыть
            </button>
          </div>
        )}

        {tab === "instructor" && (
          <form className="ds-form ds-mt" onSubmit={(e) => void onCreateInstructor(e)}>
            <label className="ds-label">
              ФИО / отображаемое имя преподавателя
              <input className="ds-input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
            </label>
            <label className="ds-label">
              Логин
              <input className="ds-input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" required />
            </label>
            <label className="ds-label">
              Пароль (мин. 8)
              <input
                type="password"
                className="ds-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                required
                minLength={8}
              />
            </label>
            <button type="submit" className="ds-btn ds-btn--primary" disabled={busy || !adminTokenReady()}>
              {busy ? "Создание…" : "Создать аккаунт преподавателя"}
            </button>
          </form>
        )}

        {tab === "groups" && (
          <div className="ds-mt">
            <form className="ds-form ds-mb" onSubmit={(e) => void onAddGroup(e)}>
              <label className="ds-label">
                Новая группа
                <input
                  className="ds-input"
                  placeholder="ИТ-21"
                  value={newGroupTitle}
                  onChange={(e) => setNewGroupTitle(e.target.value)}
                />
              </label>
              <button type="submit" className="ds-btn ds-btn--primary" disabled={busy || !adminTokenReady() || !newGroupTitle.trim()}>
                Добавить
              </button>
            </form>
            {groups.length === 0 && <p className="ds-empty">Пока нет групп.</p>}
            {groups.map((g) => (
              <div key={g.id} style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
                <strong style={{ flex: 1 }}>{g.title}</strong>
                <code className="ds-code ds-code--sm">{g.id.slice(0, 8)}…</code>
                <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => void delGroup(g.id)}>
                  Удалить
                </button>
              </div>
            ))}
          </div>
        )}

        {tab === "students" && (
          <div className="ds-mt">
            {credentialFlash && (
              <div className="ds-alert ds-alert--warn ds-mb" style={{ lineHeight: 1.5 }}>
                <strong>Вновь созданный студент — передайте эти данные лично.</strong>
                <div className="ds-caption" style={{ marginTop: "0.35rem" }}>
                  Логин вида <code className="ds-code ds-code--sm">slag_gruppy_slug_fio</code> (уникальность — суффиксы{" "}
                  <code className="ds-code ds-code--sm">_2</code>, … при повторе).
                </div>
                <div style={{ marginTop: "0.55rem" }}>
                  Логин: <code className="ds-code">{credentialFlash.username ?? "—"}</code>
                </div>
                {credentialFlash.password ? (
                  <div>
                    Временный пароль (один раз): <code className="ds-code">{credentialFlash.password}</code>
                  </div>
                ) : null}
                <div style={{ marginTop: "0.55rem" }}>
                  <button
                    type="button"
                    className="ds-btn ds-btn--ghost ds-btn--sm"
                    onClick={() =>
                      void navigator.clipboard.writeText(
                        `${credentialFlash.username ?? ""}\t${credentialFlash.password ?? ""}`,
                      )
                    }
                  >
                    Копировать строку
                  </button>
                  <button
                    type="button"
                    className="ds-btn ds-btn--ghost ds-btn--sm ds-ml-sm"
                    onClick={() => setCredentialFlash(null)}
                  >
                    Скрыть
                  </button>
                </div>
              </div>
            )}
            <form className="ds-form ds-mb" onSubmit={(e) => void onAddStudent(e)}>
              <label className="ds-label">
                ФИО студента
                <input className="ds-input" value={newStudentName} onChange={(e) => setNewStudentName(e.target.value)} required />
              </label>
              <label className="ds-label">
                Группа
                <select className="ds-input" value={newStudentGroupId} onChange={(e) => setNewStudentGroupId(e.target.value)}>
                  <option value="">— не назначена (закрытые курсы недоступны) —</option>
                  {groups.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.title}
                    </option>
                  ))}
                </select>
              </label>
              <button type="submit" className="ds-btn ds-btn--primary" disabled={busy || !adminTokenReady()}>
                Создать: логин + пароль
              </button>
            </form>

            {students.length === 0 && <p className="ds-empty">Студентов пока нет.</p>}
            {students.length > 0 && (
              <table className="ds-table">
                <thead>
                  <tr>
                    <th>ФИО</th>
                    <th>Логин</th>
                    <th>Группа</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {students.map((s) => (
                    <tr key={s.id}>
                      <td>{s.full_name}</td>
                      <td>
                        {s.username ? <code className="ds-code ds-code--sm">{s.username}</code> : <span className="ds-caption">—</span>}
                      </td>
                      <td>{s.study_group_title ?? "—"}</td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => void patchStudentUsername(s)}>
                          Логин
                        </button>
                        <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => void resetStudentPw(s)}>
                          Пароль
                        </button>
                        <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => void rotateKey(s.id)}>
                          Новый ключ
                        </button>
                        <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => void delStudent(s.id)}>
                          Удалить
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        <p className="ds-caption" style={{ marginTop: "1.25rem", marginBottom: 0 }}>
          <Link to="/">На главную</Link>
          {" · "}
          <button
            type="button"
            className="ds-link-bold"
            style={{ padding: 0, border: 0, background: "transparent" }}
            onClick={() => {
              purgeAllCabinetSessions(clearTeacher);
              navigate("/login");
            }}
          >
            Сменить пользователя
          </button>
        </p>
      </div>
    </div>
  );
}
