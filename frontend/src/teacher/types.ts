export type CourseOut = {
  id: string;
  slug: string;
  title: string;
  subject_hint: string | null;
  visibility_mode?: string;
  chat_assistant_enabled?: boolean;
  anti_cheat_mode?: "off" | "basic" | "advanced";
};

export type CourseMaterialOut = {
  id: string;
  original_filename: string;
  subject: string;
  index_status: string;
  chunks_indexed: number;
  last_job_id: string | null;
  celery_error: string | null;
  created_at: string | null;
};

export type InstructorProblemOut = {
  id: string;
  kind: string;
  title: string;
  published: boolean;
  ordinal: number;
  max_score: number;
  difficulty?: number | null;
  max_attempts?: number | null;
  score_policy?: string;
};

/** GET …/problems/{id}/instructor-detail — полное содержимое для редактирования. */
export type InstructorProblemDetailOut = {
  id: string;
  kind: string;
  title: string;
  statement: string;
  reference_answer?: string | null;
  grading_rubric?: string | null;
  starter_code?: string | null;
  mcq_options?: string[] | null;
  mcq_correct_index?: number | null;
  coding_tests: Array<{ stdin_data?: string; expected_stdout?: string; is_public?: boolean }>;
  draft_id?: string | null;
  published: boolean;
  max_score: number;
  difficulty?: number | null;
  max_attempts?: number | null;
  score_policy?: string;
};

export type DraftRow = {
  id: string;
  status: string;
  kind: string;
  title: string;
  difficulty?: number | null;
};

/** GET /api/platform/drafts/{id} — ревью черновика. */
export type DraftDetailOut = {
  id: string;
  course_id: string;
  course_slug: string;
  course_title: string;
  status: string;
  kind: string;
  title: string;
  payload: DraftPayload;
  created_at: string | null;
};

export type DraftPayload = {
  statement?: string;
  starter_code?: string | null;
  coding_tests?: Array<{
    stdin_data?: string;
    expected_stdout?: string;
    is_public?: boolean;
  }>;
  mcq_options?: string[] | null;
  mcq_correct_index?: number | null;
  reference_answer?: string | null;
  grading_rubric?: string | null;
  difficulty?: number | null;
};

export type UploadHistoryRow = {
  ts: string;
  catalog_document_id?: string | null;
  filename?: string | null;
  job_id?: string | null;
  error?: string | null;
};

export type JobTrack = {
  filename: string;
  status: string;
  error?: string;
  result?: unknown;
  done: boolean;
};

export type InstructorMeOut = {
  id: string;
  display_name: string;
  full_name: string | null;
  username: string | null;
};

export type StudyGroupOut = { id: string; title: string };

export type PlatformStudentOut = {
  id: string;
  full_name: string;
  username: string | null;
  study_group_id: string | null;
  study_group_title: string | null;
  access_key: string;
};

/** Ответ POST /admin/students (разовый пароль). */
export type PlatformStudentCreatedOut = PlatformStudentOut & {
  initial_password_plain: string | null;
};

export type GroupPolicyRowOut = {
  study_group_id: string;
  study_group_title: string;
  problems_visible: boolean;
  chat_ai_allowed: boolean;
};
