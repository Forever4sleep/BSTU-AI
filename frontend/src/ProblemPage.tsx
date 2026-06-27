import Editor from "@monaco-editor/react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { problemKindLabel } from "./labels";
import { apiPlatformJob, apiPostPublicWithStudent, apiPublicWithStudent } from "./api";
import { loadProblemDraft, patchProblemDraft } from "./problemDraftStorage";
import type { CodingVerdict, ProblemDetail } from "./types";
import { ChatMarkdown } from "./teacher/ChatMarkdown";
import { getStoredStudentAccessKey } from "./studentAccessKey";

function participantPayloadId(): string {
  const k = getStoredStudentAccessKey().trim();
  return k.length > 0 ? k.slice(0, 128) : "web-ui";
}

function problemDetailPath(problemId: string): string {
  const q = new URLSearchParams();
  const pid = participantPayloadId();
  if (pid && pid !== "web-ui") q.set("participant_id", pid);
  const qs = q.toString();
  return `/api/public/problems/${problemId}${qs ? `?${qs}` : ""}`;
}

async function pollGradeJob(jobId: string): Promise<Record<string, unknown>> {
  for (;;) {
    const st = await apiPlatformJob(jobId);
    if (st.status === "SUCCESS") {
      const r = st.result;
      return typeof r === "object" && r !== null ? (r as Record<string, unknown>) : {};
    }
    if (st.status === "FAILURE" || st.status === "REVOKED") {
      throw new Error(st.error ?? `Задача оценки: ${st.status}`);
    }
    await new Promise((res) => setTimeout(res, 1100));
  }
}

export function ProblemPage() {
  const { slug, problemId } = useParams<{ slug: string; problemId: string }>();
  const [detail, setDetail] = useState<ProblemDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [choiceIndex, setChoiceIndex] = useState(0);
  const [freeText, setFreeText] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastResult, setLastResult] = useState<CodingVerdict | Record<string, unknown> | null>(
    null,
  );

  const reloadDetail = useCallback(async () => {
    if (!problemId) return;
    const d = await apiPublicWithStudent<ProblemDetail>(problemDetailPath(problemId));
    setDetail(d);
    const saved = loadProblemDraft(problemId) ?? {};
    if (d.kind === "coding") {
      setCode(
        typeof saved.code === "string"
          ? saved.code
          : d.starter_code?.trim()
            ? d.starter_code
            : defaultCodingStub(),
      );
    }
    if (d.kind === "free_text") {
      setFreeText(typeof saved.freeText === "string" ? saved.freeText : "");
    }
    if (d.kind === "mcq") {
      setChoiceIndex(typeof saved.choiceIndex === "number" ? saved.choiceIndex : 0);
    }
  }, [problemId]);

  useEffect(() => {
    if (!problemId) return;
    let cancelled = false;
    void (async () => {
      setErr(null);
      try {
        await reloadDetail();
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [problemId, reloadDetail]);

  /** Автосохранение черновика ответа */
  useEffect(() => {
    if (!problemId || !detail || detail.id !== problemId) return;
    const id = window.setTimeout(() => {
      if (detail.kind === "coding") patchProblemDraft(problemId, { code });
      if (detail.kind === "free_text") patchProblemDraft(problemId, { freeText });
      if (detail.kind === "mcq") patchProblemDraft(problemId, { choiceIndex });
    }, 380);
    return () => window.clearTimeout(id);
  }, [code, freeText, choiceIndex, problemId, detail]);

  const [outcomeNonce, setOutcomeNonce] = useState(0);
  useEffect(() => {
    if (lastResult) setOutcomeNonce((n) => n + 1);
  }, [lastResult]);

  async function submitCoding(publicOnly: boolean) {
    if (!problemId) return;
    setBusy(true);
    setErr(null);
    setLastResult(null);
    try {
      const body = {
        participant_id: participantPayloadId(),
        source_code: code,
      };
      const r = await apiPostPublicWithStudent<CodingVerdict>(
        `/api/public/problems/${problemId}/submit`,
        body,
        {
          public_only: publicOnly,
        },
      );
      setLastResult(r);
      await reloadDetail();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function submitMcq() {
    if (!problemId) return;
    setBusy(true);
    setLastResult(null);
    try {
      const r = await apiPostPublicWithStudent<Record<string, unknown>>(`/api/public/problems/${problemId}/submit`, {
        participant_id: participantPayloadId(),
        choice_index: choiceIndex,
      });
      setLastResult(r);
      setErr(null);
      await reloadDetail();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function submitFree() {
    if (!problemId) return;
    setBusy(true);
    setLastResult(null);
    setErr(null);
    try {
      const r = await apiPostPublicWithStudent<Record<string, unknown> & { async?: boolean; job_id?: string }>(
        `/api/public/problems/${problemId}/submit`,
        {
          participant_id: participantPayloadId(),
          text: freeText,
        },
      );
      if (r.async && r.job_id) {
        const final = await pollGradeJob(String(r.job_id));
        setLastResult(final);
      } else {
        setLastResult(r);
      }
      await reloadDetail();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const attemptsLocked = detail?.attempts_left === 0;
  const diffBand = detail?.difficulty_band;

  if (!slug || !problemId) {
    return <div className="ds-alert ds-alert--err">Некорректный URL.</div>;
  }

  return (
    <>
      <p className="ds-breadcrumb stu-problem-crumb stu-problem-crumb--minimal">
        <Link to={`/c/${encodeURIComponent(slug)}`}>← Задачи курса</Link>
      </p>

      {err && <div className="ds-alert ds-alert--err stu-fade-in">{err}</div>}
      {!detail && !err && (
        <p className="stu-problem-skel stu-fade-in">
          <span className="stu-problem-skel__dot" />
          Загрузка…
        </p>
      )}

      {detail && (
        <div className="stu-problem-workbench stu-problem-workbench--minimal stu-rise-in">
          <section className="stu-problem-col stu-problem-col--desc">
            <header className="stu-problem-head">
              <h1 className="stu-problem-title">{detail.title}</h1>
              <div className="stu-problem-badges">
                <span className="stu-chip">{problemKindLabel(detail.kind)}</span>
                {diffBand && (
                  <span className={`stu-lc-diff stu-lc-diff--${diffBand}`}>
                    {diffBand === "easy" ? "Лёгкая" : diffBand === "medium" ? "Средняя" : "Сложная"}
                  </span>
                )}
                {typeof detail.difficulty === "number" && (
                  <span className="stu-problem-meta-pill">{detail.difficulty}/10</span>
                )}
                <span className="stu-problem-meta-pill">макс. {detail.max_score} б.</span>
              </div>
              <div className="stu-problem-stats">
                {detail.max_attempts != null && (
                  <span>
                    Попытки: {detail.attempts_used ?? 0} / {detail.max_attempts}
                    {detail.attempts_left !== null && detail.attempts_left !== undefined && (
                      <> · осталось {detail.attempts_left}</>
                    )}
                  </span>
                )}
                {detail.max_attempts == null && <span>Попытки без лимита</span>}
                {detail.recorded_score != null && detail.recorded_score !== undefined && (
                  <span>
                    Учёт ({detail.score_policy === "last" ? "последний" : "лучший"} балл):{" "}
                    <strong>{detail.recorded_score}</strong> / {detail.max_score}
                  </span>
                )}
              </div>
              {detail.last_scoring_reason ? (
                <div className="stu-last-feedback stu-fade-in">
                  <div className="stu-last-feedback__label">Комментарий к последней проверке</div>
                  <div className="stu-last-feedback__body">
                    <ChatMarkdown text={detail.last_scoring_reason} />
                  </div>
                  {detail.last_submission_at ? (
                    <div className="stu-last-feedback__meta">
                      {new Date(detail.last_submission_at).toLocaleString()}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </header>
            <div className="stu-problem-statement">
              <ChatMarkdown text={detail.statement} />
            </div>
            {detail.kind === "coding" && (detail.examples?.length ?? 0) > 0 && (
              <div className="stu-problem-examples">
                <h2 className="stu-problem-h2">Примеры</h2>
                <ul className="stu-problem-ex-list">
                  {(detail.examples ?? []).map((ex, i) => (
                    <li key={i} className="stu-problem-ex">
                      <div className="stu-problem-ex-label">Пример {i + 1}</div>
                      <pre className="stu-problem-ex-io">
                        Вход: {ex.stdin}
                        {"\n"}
                        Ожидаемый вывод: {ex.expected_stdout}
                      </pre>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section className="stu-problem-col stu-problem-col--work">
            <div className="stu-problem-work-head">
              <span className="stu-problem-work-title">
                {detail.kind === "coding" && "Редактор"}
                {detail.kind === "mcq" && "Ответ"}
                {detail.kind === "free_text" && "Ваш ответ"}
              </span>
              {detail.kind === "coding" && <span className="stu-problem-lang">Python</span>}
            </div>

            {detail.kind === "coding" && (
              <>
                <p className="stu-problem-hint">
                  Реализуйте <code className="ds-code">solve(data: str) -&gt; str</code>.
                </p>
                <div className="stu-problem-editor editor-wrap">
                  <Editor
                    height={400}
                    defaultLanguage="python"
                    theme="vs-dark"
                    value={code}
                    onChange={(v) => setCode(v ?? "")}
                    options={{
                      minimap: { enabled: false },
                      fontSize: 14,
                      scrollBeyondLastLine: false,
                    }}
                  />
                </div>
                <div className="stu-form-row stu-problem-actions">
                  <button
                    type="button"
                    className="ds-btn ds-btn--ghost"
                    disabled={busy || attemptsLocked}
                    onClick={() => submitCoding(true)}
                  >
                    Публичные тесты
                  </button>
                  <button
                    type="button"
                    className="ds-btn ds-btn--primary"
                    disabled={busy || attemptsLocked}
                    onClick={() => submitCoding(false)}
                  >
                    Полная отправка
                  </button>
                </div>
              </>
            )}

            {detail.kind === "mcq" && (
              <>
                <div className="stu-problem-mcq">
                  {(detail.mcq_options ?? []).map((opt, idx) => (
                    <label key={idx} className="stu-problem-mcq-row">
                      <input
                        type="radio"
                        name="mcq"
                        checked={choiceIndex === idx}
                        onChange={() => setChoiceIndex(idx)}
                      />
                      <span>{opt}</span>
                    </label>
                  ))}
                </div>
                <div className="stu-form-row stu-problem-actions">
                  <button
                    type="button"
                    className="ds-btn ds-btn--primary"
                    disabled={busy || attemptsLocked}
                    onClick={() => submitMcq()}
                  >
                    Отправить
                  </button>
                </div>
              </>
            )}

            {detail.kind === "free_text" && (
              <>
                <textarea
                  className="ds-input--area stu-problem-textarea"
                  rows={14}
                  value={freeText}
                  onChange={(ev) => setFreeText(ev.target.value)}
                  placeholder="Введите развёрнутый ответ…"
                  disabled={attemptsLocked}
                />
                <div className="stu-form-row stu-problem-actions">
                  <button
                    type="button"
                    className="ds-btn ds-btn--primary"
                    disabled={busy || attemptsLocked}
                    onClick={() => submitFree()}
                  >
                    {busy ? "Проверка…" : "Отправить на проверку"}
                  </button>
                </div>
                {busy && (
                  <div className="stu-check-wait stu-fade-in" aria-live="polite">
                    <span className="stu-check-wait__pulse" aria-hidden />
                    <span>Идёт проверка ответа…</span>
                  </div>
                )}
              </>
            )}

            <SubmissionOutcome
              key={outcomeNonce}
              kind={detail.kind}
              maxScore={detail.max_score}
              result={lastResult}
            />
          </section>
        </div>
      )}
    </>
  );
}

function defaultCodingStub() {
  return `def solve(data: str) -> str:
    \"\"\"Пример заглушки — замените на своё решение.\"\"\"
    return ""
`;
}

function SubmissionOutcome({
  kind,
  maxScore,
  result,
}: {
  kind: string;
  maxScore: number;
  result: CodingVerdict | Record<string, unknown> | null;
}) {
  if (!result) return null;
  const r = result as Record<string, unknown>;

  if (kind === "coding") {
    const v = String(r.verdict ?? "");
    const mode = r.evaluation_mode;
    const ok = v === "AC";
    const headline = ok ? "Прошёл проверку" : "Не прошёл проверку";
    const sub =
      typeof r.message === "string"
        ? r.message
        : ok
          ? "Все тесты пройдены."
          : "Есть ошибки в решении или в выводе.";
    return (
      <div
        className={`stu-outcome stu-rise-in stu-outcome--${ok ? "ok" : "bad"}`}
        role="status"
      >
        <div className="stu-outcome__badge">{ok ? "✓" : "✗"}</div>
        <div className="stu-outcome__body">
          <div className="stu-outcome__title">{headline}</div>
          <p className="stu-outcome__text">{sub}</p>
          {mode === "public_only" && (
            <p className="stu-outcome__hint">Режим: только публичные тесты (скрытые не запускались).</p>
          )}
          {Array.isArray(r.cases_public) && (r.cases_public as unknown[]).length > 0 && (
            <ul className="stu-outcome-tests">
              {(r.cases_public as Array<{ passed?: boolean }>).map((c, i) => (
                <li key={i} className={c.passed ? "stu-outcome-tests__ok" : "stu-outcome-tests__bad"}>
                  Публичный тест {i + 1}: {c.passed ? "ок" : "ошибка"}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    );
  }

  if (kind === "mcq") {
    const v = String(r.verdict ?? "");
    const ok = v === "AC";
    return (
      <div className={`stu-outcome stu-rise-in stu-outcome--${ok ? "ok" : "bad"}`} role="status">
        <div className="stu-outcome__badge">{ok ? "✓" : "✗"}</div>
        <div className="stu-outcome__body">
          <div className="stu-outcome__title">{ok ? "Правильно" : "Неправильно"}</div>
          <p className="stu-outcome__text">
            {ok ? "Выбран верный вариант." : "Выбран неверный вариант."}
          </p>
        </div>
      </div>
    );
  }

  if (kind === "free_text") {
    if (r.error != null && r.error !== "") {
      const errMsg =
        typeof r.error === "string"
          ? r.error
          : typeof r.error === "object" && r.error && "detail" in r.error
            ? String((r.error as { detail?: unknown }).detail)
            : String(r.error);
      return (
        <div className="stu-outcome stu-rise-in stu-outcome--bad" role="status">
          <div className="stu-outcome__badge">!</div>
          <div className="stu-outcome__body">
            <div className="stu-outcome__title">Ошибка проверки</div>
            <p className="stu-outcome__text">{errMsg}</p>
          </div>
        </div>
      );
    }
    const scoreRaw = r.score;
    const score = typeof scoreRaw === "number" ? scoreRaw : parseFloat(String(scoreRaw ?? "0"));
    const fb = typeof r.feedback_ru === "string" ? r.feedback_ru.trim() : "";
    const max = Number.isFinite(maxScore) && maxScore > 0 ? maxScore : 10;
    const full = score >= max - 1e-6;
    const none = score <= 1e-6;
    const tone = full ? "ok" : none ? "bad" : "partial";
    const title = full ? "Правильно (полный балл)" : none ? "Неправильно" : "Частично верно";
    return (
      <div className={`stu-outcome stu-rise-in stu-outcome--${tone}`} role="status">
        <div className="stu-outcome__badge">{full ? "✓" : none ? "✗" : "◐"}</div>
        <div className="stu-outcome__body">
          <div className="stu-outcome__title">{title}</div>
          <p className="stu-outcome__score">
            Балл: <strong>{score.toFixed(1)}</strong> / {max}
          </p>
          {fb ? <p className="stu-outcome__feedback">{fb}</p> : null}
        </div>
      </div>
    );
  }

  return null;
}
