import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { platformGetJson, platformPatchJson } from "../platformApi";
import { useTeacherAuth } from "./TeacherAuthContext";
import type { InstructorMeOut } from "./types";

/** Только профиль преподавателя. Группы и студенты ведёт администратор (/admin); доступ групп к курсу — в карточке курса. */
export function TeacherCabinetPage() {
  const { apiKey } = useTeacherAuth();
  const [me, setMe] = useState<InstructorMeOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [dispName, setDispName] = useState("");
  const [fullName, setFullName] = useState("");

  const load = useCallback(async () => {
    if (!apiKey) return;
    setErr(null);
    try {
      const profile = await platformGetJson<InstructorMeOut>("/api/platform/me", apiKey);
      setMe(profile);
      setDispName(profile.display_name);
      setFullName(profile.full_name ?? "");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [apiKey]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveProfile(ev: FormEvent) {
    ev.preventDefault();
    if (!apiKey) return;
    setMsg(null);
    setErr(null);
    try {
      const p = await platformPatchJson<InstructorMeOut>("/api/platform/me", apiKey, {
        display_name: dispName.trim() || undefined,
        full_name: fullName.trim() || null,
      });
      setMe(p);
      setMsg("Профиль сохранён.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="t-page">
      <header className="t-page__head">
        <h1 className="t-page__title">Профиль преподавателя</h1>
        <p className="t-page__sub">
          Группы, студенты и ключи доступа создаются{" "}
          <Link to="/admin" className="ds-link-bold">
            администратором
          </Link>
          . Какие группы видят задания и флаги «Чат ИИ» для вашего курса — вкладка{" "}
          <strong>«Доступ»</strong> внутри нужного курса.
        </p>
      </header>

      {err && <div className="ds-alert ds-alert--err">{err}</div>}
      {msg && <div className="ds-alert ds-alert--ok">{msg}</div>}
      {!me && !err && <p className="ds-caption">Загрузка…</p>}

      {me && (
        <div className="ds-card">
          <h2 className="t-page__h2">Данные профиля</h2>
          <form className="ds-form" onSubmit={(e) => void saveProfile(e)}>
            <label className="ds-label">
              Имя в интерфейсе (display name)
              <input className="ds-input" value={dispName} onChange={(e) => setDispName(e.target.value)} />
            </label>
            <label className="ds-label">
              ФИО (для документов / отображения)
              <input
                className="ds-input"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Иванов Иван Иванович"
              />
            </label>
            {me.username ? (
              <p className="ds-caption">
                Логин: <code className="ds-code">{me.username}</code>
              </p>
            ) : (
              <p className="ds-caption">Логин не задан (вход по сохранённому API-ключу).</p>
            )}
            <button type="submit" className="ds-btn ds-btn--primary">
              Сохранить
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
