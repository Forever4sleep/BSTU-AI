import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { draftStatusLabel, problemKindLabel } from "../labels";
import { platformGetJson, platformPatchJson, platformPostJson } from "../platformApi";
import { ChatMarkdown } from "./ChatMarkdown";
import { useTeacherAuth } from "./TeacherAuthContext";
import type { DraftDetailOut, DraftPayload } from "./types";

export function TeacherDraftReviewPage() {
  const { courseId, draftId } = useParams<{ courseId: string; draftId: string }>();
  const { apiKey } = useTeacherAuth();
  const [detail, setDetail] = useState<DraftDetailOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saveBusy, setSaveBusy] = useState(false);
  const [publishedProblemId, setPublishedProblemId] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const [editTitle, setEditTitle] = useState("");
  const [editStatement, setEditStatement] = useState("");
  const [editRef, setEditRef] = useState("");
  const [editRubric, setEditRubric] = useState("");
  const [editStarter, setEditStarter] = useState("");
  const [editMcqLines, setEditMcqLines] = useState("");
  const [editMcqCorrect, setEditMcqCorrect] = useState("");
  const [editTestsJson, setEditTestsJson] = useState("[]");

  const load = useCallback(async () => {
    if (!apiKey || !draftId) return;
    setErr(null);
    try {
      const d = await platformGetJson<DraftDetailOut>(`/api/platform/drafts/${draftId}`, apiKey);
      if (courseId && d.course_id !== courseId) {
        setErr("Черновик относится к другому курсу.");
        setDetail(null);
        return;
      }
      setDetail(d);
      const pay = d.payload ?? {};
      setEditTitle(d.title ?? "");
      setEditStatement((pay.statement ?? "").trim());
      setEditRef((pay.reference_answer ?? "").trim());
      setEditRubric((pay.grading_rubric ?? "").trim());
      setEditStarter((pay.starter_code ?? "").trim());
      setEditMcqLines((pay.mcq_options ?? []).join("\n"));
      setEditMcqCorrect(pay.mcq_correct_index != null ? String(pay.mcq_correct_index) : "");
      setEditTestsJson(JSON.stringify(pay.coding_tests ?? [], null, 2));
    } catch (e) {
      setDetail(null);
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [apiKey, draftId, courseId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function publish() {
    if (!apiKey || !draftId) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await platformPostJson<{ problem_id: string }>(
        `/api/platform/drafts/${draftId}/publish`,
        apiKey,
        {},
      );
      setPublishedProblemId(r.problem_id);
      void load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft(ev: FormEvent) {
    ev.preventDefault();
    if (!apiKey || !draftId || !detail) return;
    setSaveBusy(true);
    setErr(null);
    setSaveMsg(null);
    try {
      const base: DraftPayload = { ...(detail.payload ?? {}) };
      const nextPayload: DraftPayload = {
        ...base,
        statement: editStatement,
        reference_answer: editRef.trim() ? editRef : null,
        grading_rubric: editRubric.trim() ? editRubric : null,
      };

      if (detail.kind === "coding") {
        nextPayload.starter_code = editStarter;
        let tests: unknown;
        try {
          tests = JSON.parse(editTestsJson.trim() || "[]");
        } catch {
          throw new Error("Неверный JSON в поле «Тесты».");
        }
        if (!Array.isArray(tests)) throw new Error("Тесты должны быть JSON-массивом.");
        nextPayload.coding_tests = tests as DraftPayload["coding_tests"];
      }

      if (detail.kind === "mcq") {
        const opts = editMcqLines.split("\n").map((s) => s.trim()).filter(Boolean);
        nextPayload.mcq_options = opts;
        const ciRaw = editMcqCorrect.trim();
        if (ciRaw === "") nextPayload.mcq_correct_index = null;
        else {
          const ci = parseInt(ciRaw, 10);
          if (Number.isNaN(ci) || ci < 0) throw new Error("Некорректный индекс верного ответа.");
          if (opts.length > 0 && ci >= opts.length) {
            throw new Error("Индекс верного ответа должен быть меньше числа вариантов.");
          }
          nextPayload.mcq_correct_index = ci;
        }
      }

      await platformPatchJson(`/api/platform/drafts/${draftId}`, apiKey, {
        title: editTitle,
        payload: nextPayload,
      });
      setSaveMsg("Черновик сохранён.");
      void load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaveBusy(false);
    }
  }

  if (!courseId || !draftId) {
    return <p className="ds-alert ds-alert--err">Некорректный URL.</p>;
  }

  const canPublish = detail?.status === "pending_review";

  return (
    <div className="t-draft-review">
      <header className="t-draft-toolbar">
        <div className="t-draft-toolbar__left">
          <Link to={`/teacher/courses/${encodeURIComponent(courseId)}`} className="t-draft-back">
            ← К курсу
          </Link>
          {detail && (
            <span className="t-draft-toolbar__crumb">
              {detail.course_title || "Курс"} / <span className="t-draft-toolbar__title">Черновик задания</span>
            </span>
          )}
        </div>
        <div className="t-draft-toolbar__actions">
          {publishedProblemId && detail?.course_slug && (
            <Link
              className="ds-btn ds-btn--ghost"
              to={`/c/${encodeURIComponent(detail.course_slug)}/p/${publishedProblemId}`}
            >
              Открыть как студент
            </Link>
          )}
          {detail && canPublish && (
            <button type="button" className="ds-btn ds-btn--primary" disabled={busy} onClick={() => void publish()}>
              {busy ? "Публикация…" : "Опубликовать в курс"}
            </button>
          )}
          {detail && !canPublish && (
            <span className="ds-badge ds-badge--muted">
              {draftStatusLabel(detail.status) || "Опубликован"}
            </span>
          )}
        </div>
      </header>

      {err && <div className="ds-alert ds-alert--err t-draft-alert">{err}</div>}
      {saveMsg && <div className="ds-alert ds-alert--ok t-draft-alert">{saveMsg}</div>}

      {!detail && !err && <p className="ds-caption t-draft-loading">Загрузка черновика…</p>}

      {detail && (
        <form className="t-draft-split" onSubmit={(e) => void saveDraft(e)}>
          <section className="t-draft-pane t-draft-pane--desc" aria-label="Условие">
            <div className="t-draft-tabs" role="tablist" aria-label="Разделы">
              <span className="t-draft-tab t-draft-tab--active">Условие</span>
            </div>
            <label className="ds-label">
              Заголовок
              <input className="ds-input" value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
            </label>
            <label className="ds-label">
              Текст условия (Markdown)
              <textarea
                className="ds-input t-draft-edit-textarea"
                value={editStatement}
                onChange={(e) => setEditStatement(e.target.value)}
                rows={16}
                spellCheck
              />
            </label>
            <div className="t-draft-desc-head t-draft-desc-head--compact">
              <div className="t-draft-meta">
                <span className="ds-badge">{problemKindLabel(detail.kind)}</span>
                {typeof detail.payload?.difficulty === "number" && (
                  <span className="t-draft-diff">Сложность {detail.payload.difficulty}/10</span>
                )}
              </div>
            </div>
            <div className="t-draft-statement t-draft-statement--preview">
              <span className="t-draft-preview-label">Предпросмотр</span>
              <ChatMarkdown text={editStatement.trim() || "_(пустое условие)_"} />
            </div>
          </section>

          <section className="t-draft-pane t-draft-pane--canvas" aria-label="Эталон и сохранение">
            <div className="t-draft-canvas-head">
              <span className="t-draft-canvas-title">
                {detail.kind === "coding" && "Шаблон и тесты"}
                {detail.kind === "mcq" && "Варианты ответа"}
                {detail.kind === "free_text" && "Эталон и критерии"}
              </span>
              {detail.kind === "coding" && <span className="t-draft-lang">Python</span>}
            </div>

            {detail.kind === "coding" && (
              <>
                <label className="ds-label">
                  Шаблон кода
                  <textarea
                    className="ds-input t-draft-edit-textarea ds-code"
                    value={editStarter}
                    onChange={(e) => setEditStarter(e.target.value)}
                    rows={14}
                    spellCheck={false}
                  />
                </label>
                <label className="ds-label">
                  Тесты (JSON)
                  <textarea
                    className="ds-input t-draft-edit-textarea ds-code"
                    value={editTestsJson}
                    onChange={(e) => setEditTestsJson(e.target.value)}
                    rows={12}
                    spellCheck={false}
                  />
                </label>
              </>
            )}

            {detail.kind === "mcq" && (
              <>
                <label className="ds-label">
                  Варианты (по одному на строку)
                  <textarea
                    className="ds-input t-draft-edit-textarea"
                    value={editMcqLines}
                    onChange={(e) => setEditMcqLines(e.target.value)}
                    rows={8}
                  />
                </label>
                <label className="ds-label">
                  Индекс верного ответа (0 — первый)
                  <input
                    className="ds-input"
                    value={editMcqCorrect}
                    onChange={(e) => setEditMcqCorrect(e.target.value)}
                    inputMode="numeric"
                  />
                </label>
              </>
            )}

            {detail.kind === "free_text" && (
              <>
                <label className="ds-label">
                  Эталонный ответ
                  <textarea
                    className="ds-input t-draft-edit-textarea"
                    value={editRef}
                    onChange={(e) => setEditRef(e.target.value)}
                    rows={10}
                    spellCheck
                  />
                </label>
                <label className="ds-label">
                  Рубрика (опционально)
                  <textarea
                    className="ds-input t-draft-edit-textarea"
                    value={editRubric}
                    onChange={(e) => setEditRubric(e.target.value)}
                    rows={6}
                  />
                </label>
              </>
            )}

            <div className="t-draft-save-row">
              <button type="submit" className="ds-btn ds-btn--primary" disabled={saveBusy}>
                {saveBusy ? "Сохранение…" : "Сохранить черновик"}
              </button>
              <p className="ds-caption" style={{ margin: 0 }}>
                Можно править в любом статусе черновика. После публикации редактируйте задачу на вкладке курса —
                «Условие и эталон».
              </p>
            </div>
          </section>
        </form>
      )}
    </div>
  );
}
