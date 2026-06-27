export type ProblemDifficultyBand = "easy" | "medium" | "hard";

export type ProblemListItem = {
  id: string;
  kind: string;
  title: string;
  difficulty?: number | null;
  difficulty_band?: ProblemDifficultyBand | null;
  max_score?: number;
  score_policy?: string;
  attempts_used?: number;
  attempts_left?: number | null;
  best_score?: number | null;
  last_score?: number | null;
  recorded_score?: number | null;
  last_scoring_reason?: string | null;
};

export type ProblemDetail = {
  id: string;
  kind: string;
  title: string;
  statement: string;
  starter_code?: string | null;
  mcq_options?: string[] | null;
  max_score: number;
  examples?: { stdin: string; expected_stdout: string }[] | null;
  difficulty?: number | null;
  difficulty_band?: ProblemDifficultyBand | null;
  max_attempts?: number | null;
  score_policy?: string;
  attempts_used?: number;
  attempts_left?: number | null;
  best_score?: number | null;
  last_score?: number | null;
  recorded_score?: number | null;
  last_scoring_reason?: string | null;
  last_submission_at?: string | null;
};

export type CodingVerdict = {
  verdict: string;
  message?: string;
  cases_public?: Array<{
    passed: boolean;
    expected: string;
    got: string;
    error: string | null;
  }>;
  hidden?: { passed: number; total: number };
  evaluation_mode?: string;
  stored_submission_id?: string;
};
