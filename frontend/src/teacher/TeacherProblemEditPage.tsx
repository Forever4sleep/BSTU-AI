import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { platformGetJson, platformPatchJson } from "../platformApi";
import { ChatMarkdown } from "./ChatMarkdown";
import { useTeacherAuth } from "./TeacherAuthContext";
import type { InstructorProblemDetailOut } from "./types";

export function TeacherProblemEditPage() {
  const { courseId, problemId } = useParams<{ courseId: string; problemId: string }>();
  const { apiKey } = useTeacherAuth();
  const [detail, setDetail] = useState<InstructorProblemDetailOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [statement, setStatement] = useState("");
  const [referenceAnswer, setReferenceAnswer] = useState("");
  const [gradingRubric, setGradingRubric] = useState("");
  const [starterCode, setStarterCode] = useState("");
  const [mcqLines, setMcqLines] = useState("");
  const [mcqCorrect, setMcqCorrect] = useState("");
  const [testsJson, setTestsJson] = useState("[]");
  const [difficulty, setDifficulty] = useState("");
  const [maxAttempts, setMaxAttempts] = useState("");
  const [scorePolicy, setScorePolicy] = useState<"best" | "last">("best");

  const load = useCallback(async () => {
    if (!apiKey || !courseId || !problemId) return;
    setErr(null);
    try {
      const d = await platformGetJson<InstructorProblemDetailOut>(
        `/api/platform/courses/${courseId}/problems/${problemId}/instructor-detail`,
        apiKey,
      );
      setDetail(d);
      setTitle(d.title);
      setStatement(d.statement);
      setReferenceAnswer(d.reference_answer ?? "");
      setGradingRubric(d.grading_rubric ?? "");
      setStarterCode(d.starter_code ?? "");
      setMcqLines((d.mcq_options ?? []).join("\n"));
      setMcqCorrect(d.mcq_correct_index != null ? String(d.mcq_correct_index) : "");
      setTestsJson(JSON.stringify(d.coding_tests ?? [], null, 2));
      setDifficulty(d.difficulty != null ? String(d.difficulty) : "");
      setMaxAttempts(d.max_attempts != null ? String(d.max_attempts) : "");
      setScorePolicy(d.score_policy === "last" ? "last" : "best");
    } catch (e) {
      setDetail(null);
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [apiKey, courseId, problemId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (!apiKey || !courseId || !problemId || !detail) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      let diffVal: number | null = null;
      if (difficulty.trim() !== "") {
        diffVal = parseInt(difficulty, 10);
        if (Number.isNaN(diffVal) || diffVal < 1 || diffVal > 10) {
          throw new Error("Сложность должна быть числом от 1 до 10 или пустым полем.");
        }
      }
      let maxA: number | null = null;
      if (maxAttempts.trim() !== "") {
        maxA = parseInt(maxAttempts, 10);
        if (Number.isNaN(maxA) || maxA < 1) throw new Error("Макс. попыток — положительное число или пусто.");
      }

      const body: Record<string, unknown> = {
        title,
        statement,
        difficulty: diffVal,
        max_attempts: maxA,
        score_policy: scorePolicy,
      };

      if (detail.kind === "free_text") {
        body.reference_answer = referenceAnswer.trim() ? referenceAnswer : null;
        body.grading_rubric = gradingRubric.trim() ? gradingRubric : null;
      }
      if (detail.kind === "coding") {
        body.starter_code = starterCode;
        let tests: unknown;
        try {
          tests = JSON.parse(testsJson.trim() || "[]");
        } catch {
          throw new Error("Неверный JSON в поле «Тесты».");
        }
        if (!Array.isArray(tests)) throw new Error("Тесты должны быть JSON-массивом.");
        body.coding_tests = tests;
      }
      if (detail.kind === "mcq") {
        const opts = mcqLines.split("\n").map((s) => s.trim()).filter(Boolean);
        body.mcq_options = opts;
        const ciRaw = mcqCorrect.trim();
        if (ciRaw === "") body.mcq_correct_index = null;
        else {
          const ci = parseInt(ciRaw, 10);
          if (Number.isNaN(ci) || ci < 0) throw new Error("Некорректный индекс верного ответа.");
          body.mcq_correct_index = ci;
          if (opts.length > 0 && ci >= opts.length) {
            throw new Error("Индекс верного ответа должен быть меньше числа вариантов.");
          }
        }
      }

      await platformPatchJson(`/api/platform/courses/${courseId}/problems/${problemId}`, apiKey, body);
      setMsg("Изменения сохранены.");
      void load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!courseId || !problemId) {
    return <p className="ds-alert ds-alert--err">Некорректный URL.</p>;
  }

  return (
    <div className="t-page">
      <nav className="ds-breadcrumb">
        <Link to="/teacher/courses">Курсы</Link>
        <span className="ds-breadcrumb__sep">/</span>
        <Link to={`/teacher/courses/${encodeURIComponent(courseId)}`}>Курс</Link>
        <span className="ds-breadcrumb__sep">/</span>
        <span>Редактирование задачи</span>
      </nav>

      <header className="t-page__head">
        <h1 className="t-page__title">Редактирование задания</h1>
        <p className="t-page__sub">
          Условие и эталон (и параметры курса) сохраняются для студентов сразу после «Сохранить».
        </p>
      </header>

      {err && <div className="ds-alert ds-alert--err">{err}</div>}
      {msg && <div className="ds-alert ds-alert--ok">{msg}</div>}

      {!detail && !err && <p className="ds-caption">Загрузка…</p>}

      {detail && (
        <form className="t-problem-edit" onSubmit={(e) => void onSubmit(e)}>
          <div className="t-problem-edit__grid">
            <section className="t-problem-edit__col" aria-label="Условие">
              <label className="ds-label">
                Заголовок
                <input className="ds-input" value={title} onChange={(e) => setTitle(e.target.value)} />
              </label>
              <label className="ds-label">
                Условие (Markdown)
                <textarea
                  className="ds-input t-problem-edit__textarea"
                  value={statement}
                  onChange={(e) => setStatement(e.target.value)}
                  rows={14}
                  spellCheck
                />
              </label>
              <div className="t-problem-edit__preview">
                <span className="t-problem-edit__preview-label">Предпросмотр</span>
                <div className="t-draft-statement">
                  <ChatMarkdown text={statement.trim() || "_(пусто)_"} />
                </div>
              </div>
            </section>

            <section className="t-problem-edit__col" aria-label="Эталон и настройки">
              <div className="ds-badge ds-badge--muted" style={{ marginBottom: "0.5rem" }}>
                Тип: {detail.kind}
              </div>

              {detail.kind === "free_text" && (
                <>
                  <label className="ds-label">
                    Эталонный ответ
                    <textarea
                      className="ds-input t-problem-edit__textarea"
                      value={referenceAnswer}
                      onChange={(e) => setReferenceAnswer(e.target.value)}
                      rows={10}
                      spellCheck
                    />
                  </label>
                  <label className="ds-label">
                    Рубрика оценивания (опционально)
                    <textarea
                      className="ds-input t-problem-edit__textarea"
                      value={gradingRubric}
                      onChange={(e) => setGradingRubric(e.target.value)}
                      rows={6}
                    />
                  </label>
                </>
              )}

              {detail.kind === "coding" && (
                <>
                  <label className="ds-label">
                    Шаблон кода (Python)
                    <textarea
                      className="ds-input t-problem-edit__textarea ds-code"
                      value={starterCode}
                      onChange={(e) => setStarterCode(e.target.value)}
                      rows={12}
                      spellCheck={false}
                    />
                  </label>
                  <label className="ds-label">
                    Тесты (JSON: массив объектов stdin_data, expected_stdout, is_public)
                    <textarea
                      className="ds-input t-problem-edit__textarea ds-code"
                      value={testsJson}
                      onChange={(e) => setTestsJson(e.target.value)}
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
                      className="ds-input t-problem-edit__textarea"
                      value={mcqLines}
                      onChange={(e) => setMcqLines(e.target.value)}
                      rows={8}
                    />
                  </label>
                  <label className="ds-label">
                    Индекс верного ответа (0 — первый)
                    <input
                      className="ds-input"
                      value={mcqCorrect}
                      onChange={(e) => setMcqCorrect(e.target.value)}
                      inputMode="numeric"
                      placeholder="например 0"
                    />
                  </label>
                </>
              )}

              <fieldset className="t-prob-inst-grid t-problem-edit__fieldset">
                <legend className="t-problem-edit__legend">Параметры ведения</legend>
                <label className="t-prob-inst-field">
                  Сложность 1–10
                  <input
                    className="ds-input"
                    type="number"
                    min={1}
                    max={10}
                    value={difficulty}
                    onChange={(e) => setDifficulty(e.target.value)}
                  />
                </label>
                <label className="t-prob-inst-field">
                  Макс. попыток (пусто = ∞)
                  <input
                    className="ds-input"
                    type="number"
                    min={1}
                    placeholder="∞"
                    value={maxAttempts}
                    onChange={(e) => setMaxAttempts(e.target.value)}
                  />
                </label>
                <label className="t-prob-inst-field">
                  Учёт балла
                  <select
                    className="ds-input"
                    value={scorePolicy}
                    onChange={(e) => setScorePolicy(e.target.value === "last" ? "last" : "best")}
                  >
                    <option value="best">Лучшая попытка</option>
                    <option value="last">Последняя попытка</option>
                  </select>
                </label>
              </fieldset>

              <div className="t-problem-edit__actions">
                <button type="submit" className="ds-btn ds-btn--primary" disabled={busy}>
                  {busy ? "Сохранение…" : "Сохранить"}
                </button>
                <Link className="ds-btn ds-btn--ghost" to={`/teacher/courses/${encodeURIComponent(courseId)}`}>
                  К курсу
                </Link>
              </div>
            </section>
          </div>
        </form>
      )}
    </div>
  );
}
