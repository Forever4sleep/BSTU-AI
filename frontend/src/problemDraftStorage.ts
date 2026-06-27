/** Черновики ответов по задаче — переживают обновление страницы (localStorage). */

export type ProblemAnswerDraft = {
  code?: string;
  freeText?: string;
  choiceIndex?: number;
};

function key(problemId: string): string {
  return `bstu-problem-draft:${problemId}`;
}

export function loadProblemDraft(problemId: string): ProblemAnswerDraft | null {
  try {
    const raw = localStorage.getItem(key(problemId));
    if (!raw) return null;
    const v = JSON.parse(raw) as unknown;
    if (!v || typeof v !== "object") return null;
    return v as ProblemAnswerDraft;
  } catch {
    return null;
  }
}

export function saveProblemDraft(problemId: string, draft: ProblemAnswerDraft): void {
  try {
    localStorage.setItem(key(problemId), JSON.stringify(draft));
  } catch {
    /* quota / private mode */
  }
}

export function patchProblemDraft(problemId: string, patch: Partial<ProblemAnswerDraft>): void {
  const prev = loadProblemDraft(problemId) ?? {};
  saveProblemDraft(problemId, { ...prev, ...patch });
}
