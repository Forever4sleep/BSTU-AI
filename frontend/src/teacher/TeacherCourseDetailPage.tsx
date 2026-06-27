import { DragEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  platformDelete,
  platformDownloadBlob,
  platformGetJson,
  platformJobStatus,
  platformPatchJson,
  platformPostJson,
  platformPutJson,
  platformUpload,
} from "../platformApi";
import { materialIndexStatusLabel, problemKindLabel } from "../labels";
import {
  AGENT_KIND_KEYS,
  AGENT_KIND_LABELS,
  AGENT_PROGRESS_STEPS,
  AgentKindKey,
  agentFriendlyDetail,
  agentGenerationResultMessage,
  agentPhaseFromMeta,
  agentPhaseIndex,
  agentProgressPercent,
  agentStatusTitle,
  distributeKindsEvenly,
  kindQuotaPreview,
} from "./agentGenerationUi";
import {
  clearAgentDraftJob,
  loadAgentDraftJob,
  saveAgentDraftJob,
} from "./agentJobStorage";
import { useTeacherAuth } from "./TeacherAuthContext";
import type {
  CourseMaterialOut,
  CourseOut,
  DraftRow,
  GroupPolicyRowOut,
  InstructorProblemOut,
  JobTrack,
  StudyGroupOut,
  UploadHistoryRow,
} from "./types";

type TabId = "materials" | "problems" | "studio" | "access" | "settings";

const BATCH_PLATFORM_KEYS = [
  "documents",
  "documents/failed",
  "material-upload-history",
  "problems-instructor",
  "drafts",
  "group-access",
] as const;

async function fetchStudyGroupsCatalog(
  apiKey: string,
): Promise<{ groups: StudyGroupOut[]; warn?: string }> {
  try {
    const gs = await platformGetJson<StudyGroupOut[]>(`/api/platform/study-groups`, apiKey);
    return { groups: gs };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const is404 = /^404\b/.test(msg);
    if (is404) {
      try {
        const gs = await platformGetJson<StudyGroupOut[]>(`/api/platform/groups`, apiKey);
        return { groups: gs };
      } catch (e2) {
        console.warn("[TeacherCourseDetail] study-groups and /groups unavailable:", e2);
        return {
          groups: [],
          warn: "Каталог учебных групп недоступен. Раздел «Доступ» покажет пустой список до обновления сервера.",
        };
      }
    }
    console.warn("[TeacherCourseDetail] study-groups failed:", msg);
    return {
      groups: [],
      warn: "Не удалось загрузить каталог групп. Раздел «Доступ» покажет пустой список.",
    };
  }
}

type AccessDraftRow = {
  study_group_id: string;
  title: string;
  linked: boolean;
  problems_visible: boolean;
  chat_ai_allowed: boolean;
};

const TERMINAL = new Set(["SUCCESS", "FAILURE", "REVOKED"]);

type AgentDraftJobResult = {
  created?: number;
  drafts?: { draft_id: string }[];
  warnings?: string[];
  documents_used?: string[];
};

type AgentJobLive = {
  status: string;
  meta?: { phase?: string; label?: string };
};

function humanizeCeleryMessage(msg: string): string {
  const t = msg.trim();
  const looksUnregistered =
    /unregistered task/i.test(t) ||
    /NotRegistered/i.test(t) ||
    t === "platform.generate_agent_drafts" ||
    t.includes("platform.generate_agent_drafts");
  if (looksUnregistered) {
    return (
      "Фоновый воркер не зарегистрировал задачу генерации. Перезапустите сервис celery-worker. " +
      "В docker-compose у воркера должен быть том с кодом проекта (./:/app), как у ingestion-service. " +
      "Команда: docker compose up -d celery-worker"
    );
  }
  return msg;
}

function formatPlatformRequestError(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const m = /^(\d{3})\s+([\s\S]+)$/.exec(raw.trim());
  if (m) {
    try {
      const body = JSON.parse(m[2]) as { detail?: unknown };
      if (typeof body.detail === "string") return body.detail;
    } catch {
      /* raw body */
    }
  }
  return humanizeCeleryMessage(raw);
}


const DIFF_SHORT: Record<number, string> = {
  1: "вступит.",
  2: "базовый",
  3: "лёгкий",
  4: "ниже ср.",
  5: "средний",
  6: "выше ср.",
  7: "сложный",
  8: "глубокий",
  9: "экзамен",
  10: "макс.",
};

export function TeacherCourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();
  const { apiKey } = useTeacherAuth();

  const [tab, setTab] = useState<TabId>("materials");
  const [course, setCourse] = useState<CourseOut | null>(null);
  const [materials, setMaterials] = useState<CourseMaterialOut[]>([]);
  const [problems, setProblems] = useState<InstructorProblemOut[]>([]);
  const [drafts, setDrafts] = useState<DraftRow[]>([]);

  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [loadWarn, setLoadWarn] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [uploadSubject, setUploadSubject] = useState("");
  const [pickedFiles, setPickedFiles] = useState<File[]>([]);
  const [dropActive, setDropActive] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [failedMaterials, setFailedMaterials] = useState<CourseMaterialOut[]>([]);
  const [diskHistory, setDiskHistory] = useState<UploadHistoryRow[]>([]);
  const [studyGroups, setStudyGroups] = useState<StudyGroupOut[]>([]);
  const [groupPolicies, setGroupPolicies] = useState<GroupPolicyRowOut[]>([]);
  const [accessDraft, setAccessDraft] = useState<AccessDraftRow[]>([]);
  const [visibilityDraft, setVisibilityDraft] = useState<"public" | "groups">("public");
  const [settingsChatEnabled, setSettingsChatEnabled] = useState(true);
  const [settingsAntiCheat, setSettingsAntiCheat] = useState<"off" | "basic" | "advanced">("advanced");
  const [settingsBusy, setSettingsBusy] = useState(false);

  /** Агент генерации: выбранные лекции (catalog document id) и квоты сложности 1–10 */
  const [agentDocSelection, setAgentDocSelection] = useState<Record<string, boolean>>({});
  const [deletingMaterialId, setDeletingMaterialId] = useState<string | null>(null);
  const [deletingProblemId, setDeletingProblemId] = useState<string | null>(null);
  const [deletingDraftId, setDeletingDraftId] = useState<string | null>(null);
  const [agentQuota, setAgentQuota] = useState<number[]>(() => Array.from({ length: 10 }, () => 0));
  const [agentKindQuota, setAgentKindQuota] = useState<Record<AgentKindKey, number>>({
    coding: 0,
    mcq: 0,
    free_text: 0,
  });
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentJobId, setAgentJobId] = useState<string | null>(null);
  const [agentJobStartedAt, setAgentJobStartedAt] = useState<number | null>(null);
  const [agentLive, setAgentLive] = useState<AgentJobLive | null>(null);
  const [, setAgentTick] = useState(0);

  const [probEdit, setProbEdit] = useState<
    Record<string, { d: string; m: string; pol: "best" | "last" }>
  >({});

  const [jobMap, setJobMap] = useState<Record<string, JobTrack>>({});
  const jobMapRef = useRef(jobMap);
  jobMapRef.current = jobMap;

  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepthRef = useRef(0);

  const mergeFileLists = useCallback((incoming: File[]) => {
    setPickedFiles((prev) => {
      const map = new Map<string, File>();
      const key = (f: File) => `${f.name}\0${f.size}\0${f.lastModified}`;
      for (const f of prev) map.set(key(f), f);
      for (const f of incoming) map.set(key(f), f);
      return [...map.values()];
    });
  }, []);

  function onDropZoneDragEnter(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current += 1;
    setDropActive(true);
  }

  function onDropZoneDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setDropActive(false);
  }

  function onDropZoneDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
  }

  function onDropZoneDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = 0;
    setDropActive(false);
    const list = Array.from(e.dataTransfer.files ?? []);
    mergeFileLists(list);
  }

  const loadAll = useCallback(async () => {
    if (!apiKey || !courseId) return;
    setLoadErr(null);
    setLoadWarn(null);
    try {
      const c = await platformGetJson<CourseOut>(`/api/platform/courses/${courseId}`, apiKey);
      setCourse(c);
      const [catalog, settled] = await Promise.all([
        fetchStudyGroupsCatalog(apiKey),
        Promise.allSettled([
          platformGetJson<CourseMaterialOut[]>(`/api/platform/courses/${courseId}/documents`, apiKey),
          platformGetJson<CourseMaterialOut[]>(`/api/platform/courses/${courseId}/documents/failed`, apiKey),
          platformGetJson<UploadHistoryRow[]>(
            `/api/platform/courses/${courseId}/material-upload-history?limit=100`,
            apiKey,
          ),
          platformGetJson<InstructorProblemOut[]>(
            `/api/platform/courses/${courseId}/problems-instructor`,
            apiKey,
          ),
          platformGetJson<DraftRow[]>(`/api/platform/courses/${courseId}/drafts`, apiKey),
          platformGetJson<GroupPolicyRowOut[]>(`/api/platform/courses/${courseId}/group-access`, apiKey),
        ]),
      ]);

      settled.forEach((result, i) => {
        if (result.status === "rejected") {
          console.warn(
            `[TeacherCourseDetail] ${BATCH_PLATFORM_KEYS[i]} failed:`,
            result.reason,
          );
        }
      });

      const m = settled[0].status === "fulfilled" ? settled[0].value : [];
      const fm = settled[1].status === "fulfilled" ? settled[1].value : [];
      const uh = settled[2].status === "fulfilled" ? settled[2].value : [];
      const p = settled[3].status === "fulfilled" ? settled[3].value : [];
      const d = settled[4].status === "fulfilled" ? settled[4].value : [];
      const po = settled[5].status === "fulfilled" ? settled[5].value : [];

      setMaterials(m);
      setFailedMaterials(fm);
      setDiskHistory(uh);
      setProblems(p);
      setDrafts(d);
      setStudyGroups(catalog.groups);
      if (catalog.warn) setLoadWarn(catalog.warn);
      setGroupPolicies(po);
      const vm = (c.visibility_mode === "groups" ? "groups" : "public") as "public" | "groups";
      setVisibilityDraft(vm);
      setSettingsChatEnabled(c.chat_assistant_enabled !== false);
      setSettingsAntiCheat(
        c.anti_cheat_mode === "off" || c.anti_cheat_mode === "basic" ? c.anti_cheat_mode : "advanced",
      );
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : String(e));
    }
  }, [apiKey, courseId]);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const indexedMaterials = useMemo(
    () => materials.filter((m) => m.index_status === "indexed"),
    [materials],
  );

  const pendingDrafts = useMemo(
    () => drafts.filter((d) => d.status === "pending_review"),
    [drafts],
  );

  const agentQuotaTotal = useMemo(() => agentQuota.reduce((a, b) => a + b, 0), [agentQuota]);

  const agentKindTotal = useMemo(
    () => AGENT_KIND_KEYS.reduce((sum, k) => sum + agentKindQuota[k], 0),
    [agentKindQuota],
  );

  const agentQuotasMatch = agentQuotaTotal > 0 && agentKindTotal === agentQuotaTotal;

  const agentSelectedLectureCount = useMemo(
    () => Object.values(agentDocSelection).filter(Boolean).length,
    [agentDocSelection],
  );

  const agentLivePhase = agentLive ? agentPhaseFromMeta(agentLive.meta) : "queue";
  const agentLivePhaseIdx = agentPhaseIndex(agentLivePhase);
  const agentLivePercent = agentProgressPercent(agentLivePhase);

  const bumpAgentQuota = useCallback((index: number, delta: number) => {
    setAgentQuota((prev) => {
      const cp = [...prev];
      const sum = cp.reduce((a, b) => a + b, 0);
      const nextVal = Math.max(0, Math.min(25, cp[index] + delta));
      const nextSum = sum - cp[index] + nextVal;
      if (delta > 0 && nextSum > 25) return prev;
      cp[index] = nextVal;
      return cp;
    });
  }, []);

  const bumpAgentKind = useCallback(
    (key: AgentKindKey, delta: number) => {
      setAgentKindQuota((prev) => {
        const sum = AGENT_KIND_KEYS.reduce((a, k) => a + prev[k], 0);
        const nextVal = Math.max(0, prev[key] + delta);
        const nextSum = sum - prev[key] + nextVal;
        const cap = agentQuotaTotal > 0 ? agentQuotaTotal : 25;
        if (delta > 0 && nextSum > cap) return prev;
        return { ...prev, [key]: nextVal };
      });
    },
    [agentQuotaTotal],
  );

  useEffect(() => {
    if (!courseId || !apiKey || agentJobId) return;
    const saved = loadAgentDraftJob(courseId);
    if (!saved) return;

    let cancelled = false;
    void (async () => {
      try {
        const st = await platformJobStatus(saved.jobId);
        if (cancelled) return;
        if (st.status === "SUCCESS") {
          clearAgentDraftJob(courseId);
          const res = st.result as AgentDraftJobResult | undefined;
          const n = res?.created ?? 0;
          const w = res?.warnings?.filter(Boolean);
          setMsg(agentGenerationResultMessage(n, w));
          if (n > 0) setTab("problems");
          void loadAll();
          return;
        }
        if (st.status === "FAILURE" || st.status === "REVOKED") {
          clearAgentDraftJob(courseId);
          setActionErr(humanizeCeleryMessage(st.error ?? `Задача завершилась со статусом ${st.status}`));
          return;
        }
        setAgentJobId(saved.jobId);
        setAgentJobStartedAt(saved.startedAt);
        setAgentLive({ status: st.status, meta: st.meta });
      } catch {
        if (!cancelled) clearAgentDraftJob(courseId);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [courseId, apiKey, agentJobId, loadAll]);

  useEffect(() => {
    if (!agentJobId) return;
    const t = window.setInterval(() => setAgentTick((x) => x + 1), 1000);
    return () => window.clearInterval(t);
  }, [agentJobId]);

  useEffect(() => {
    if (!agentJobId) return;
    let cancelled = false;
    let iv = 0;

    const poll = async () => {
      try {
        const st = await platformJobStatus(agentJobId);
        if (cancelled) return;
        if (st.status === "SUCCESS") {
          window.clearInterval(iv);
          if (courseId) clearAgentDraftJob(courseId);
          setAgentJobId(null);
          setAgentJobStartedAt(null);
          setAgentLive(null);
          const res = st.result as AgentDraftJobResult | undefined;
          const n = res?.created ?? 0;
          const w = res?.warnings?.filter(Boolean);
          setMsg(agentGenerationResultMessage(n, w));
          if (n > 0) setTab("problems");
          void loadAll();
        } else if (st.status === "FAILURE" || st.status === "REVOKED") {
          window.clearInterval(iv);
          if (courseId) clearAgentDraftJob(courseId);
          setAgentJobId(null);
          setAgentJobStartedAt(null);
          setAgentLive(null);
          setActionErr(humanizeCeleryMessage(st.error ?? `Задача завершилась со статусом ${st.status}`));
        } else {
          setAgentLive({ status: st.status, meta: st.meta });
        }
      } catch (e) {
        window.clearInterval(iv);
        if (courseId) clearAgentDraftJob(courseId);
        setAgentJobId(null);
        setAgentJobStartedAt(null);
        setAgentLive(null);
        setActionErr(formatPlatformRequestError(e));
      }
    };

    void poll();
    iv = window.setInterval(() => void poll(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(iv);
    };
  }, [agentJobId, courseId, loadAll]);

  useEffect(() => {
    const next: Record<string, { d: string; m: string; pol: "best" | "last" }> = {};
    for (const x of problems) {
      next[x.id] = {
        d: x.difficulty != null ? String(x.difficulty) : "",
        m: x.max_attempts != null ? String(x.max_attempts) : "",
        pol: x.score_policy === "last" ? "last" : "best",
      };
    }
    setProbEdit(next);
  }, [problems]);

  useEffect(() => {
    if (tab !== "access") return;
    const pmap = new Map(groupPolicies.map((pol) => [pol.study_group_id, pol]));
    setAccessDraft(
      studyGroups.map((g) => {
        const pol = pmap.get(g.id);
        return {
          study_group_id: g.id,
          title: g.title,
          linked: pol !== undefined,
          /* группа без политики не «в курсе»: задания/чат не активны до отметки «В курсе» */
          problems_visible: Boolean(pol?.problems_visible),
          chat_ai_allowed: Boolean(pol?.chat_ai_allowed),
        };
      }),
    );
  }, [tab, studyGroups, groupPolicies]);

  useEffect(() => {
    const iv = window.setInterval(async () => {
      const m = { ...jobMapRef.current };
      const open = Object.entries(m).filter(([, tr]) => !tr.done);
      if (open.length === 0) return;
      let changed = false;
      for (const [jid, tr] of open) {
        try {
          const s = await platformJobStatus(jid);
          const terminal = TERMINAL.has(s.status);
          m[jid] = { ...tr, status: s.status, error: s.error, result: s.result, done: terminal };
          changed = true;
        } catch {
          m[jid] = { ...tr, status: "poll_error", error: "Опрос задачи", done: true };
          changed = true;
        }
      }
      if (changed) setJobMap(m);
    }, 2500);
    return () => window.clearInterval(iv);
  }, []);

  async function onUpload(ev: FormEvent) {
    ev.preventDefault();
    if (!courseId || pickedFiles.length === 0) {
      setActionErr("Выберите один или несколько файлов");
      return;
    }
    setActionErr(null);
    setMsg(null);
    setUploadBusy(true);
    const errors: string[] = [];
    try {
      for (const file of pickedFiles) {
        const fd = new FormData();
        fd.append("file", file);
        const subj = uploadSubject.trim();
        if (subj) fd.append("subject", subj);
        try {
          const res = await platformUpload(`/api/platform/courses/${courseId}/upload`, apiKey!, fd);
          setJobMap((prev) => ({
            ...prev,
            [res.job_id]: { filename: file.name, status: "PENDING", done: false },
          }));
        } catch (e) {
          errors.push(`${file.name}: ${e instanceof Error ? e.message : String(e)}`);
        }
        await loadAll();
      }
      if (errors.length) setActionErr(errors.join(" · "));
      else setMsg(`В очередь отправлено файлов: ${pickedFiles.length}`);
      setPickedFiles([]);
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : String(e));
    } finally {
      setUploadBusy(false);
    }
  }

  async function saveCourseVisibility(ev: FormEvent) {
    ev.preventDefault();
    if (!apiKey || !courseId) return;
    setActionErr(null);
    setMsg(null);
    try {
      const updated = await platformPatchJson<CourseOut>(
        `/api/platform/courses/${courseId}`,
        apiKey,
        { visibility_mode: visibilityDraft },
      );
      setCourse(updated);
      setMsg(`Режим курса: ${updated.visibility_mode === "groups" ? "только выбранные группы" : "публичный"}`);
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function saveCourseSettings(ev: FormEvent) {
    ev.preventDefault();
    if (!apiKey || !courseId) return;
    setActionErr(null);
    setMsg(null);
    setSettingsBusy(true);
    try {
      const updated = await platformPatchJson<CourseOut>(
        `/api/platform/courses/${courseId}/settings`,
        apiKey,
        {
          chat_assistant_enabled: settingsChatEnabled,
          anti_cheat_mode: settingsAntiCheat,
        },
      );
      setCourse(updated);
      setSettingsChatEnabled(updated.chat_assistant_enabled !== false);
      setSettingsAntiCheat(
        updated.anti_cheat_mode === "off" || updated.anti_cheat_mode === "basic"
          ? updated.anti_cheat_mode
          : "advanced",
      );
      setMsg("Настройки курса сохранены.");
    } catch (e) {
      setActionErr(formatPlatformRequestError(e));
    } finally {
      setSettingsBusy(false);
    }
  }

  async function saveGroupPolicies(ev: FormEvent) {
    ev.preventDefault();
    if (!apiKey || !courseId) return;
    setActionErr(null);
    setMsg(null);
    try {
      const policies = accessDraft
        .filter((r) => r.linked)
        .map((r) => ({
          study_group_id: r.study_group_id,
          problems_visible: r.problems_visible,
          chat_ai_allowed: r.chat_ai_allowed,
        }));
      const next = await platformPutJson<GroupPolicyRowOut[]>(
        `/api/platform/courses/${courseId}/group-access`,
        apiKey,
        { policies },
      );
      setGroupPolicies(next);
      setMsg(`Политики групп обновлены (${next.length}).`);
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function downloadMaterial(m: CourseMaterialOut) {
    if (!apiKey || !courseId) return;
    setActionErr(null);
    try {
      const blob = await platformDownloadBlob(
        `/api/platform/courses/${courseId}/documents/${encodeURIComponent(m.id)}/download`,
        apiKey,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = m.original_filename;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function deleteMaterial(m: CourseMaterialOut) {
    if (!apiKey || !courseId) return;
    if (!confirm(`Удалить «${m.original_filename}»? Файл будет удалён из курса и из поиска по материалам.`)) return;
    setActionErr(null);
    setDeletingMaterialId(m.id);
    try {
      await platformDelete(
        `/api/platform/courses/${courseId}/documents/${encodeURIComponent(m.id)}`,
        apiKey,
      );
      setMaterials((prev) => prev.filter((row) => row.id !== m.id));
      setAgentDocSelection((prev) => {
        const next = { ...prev };
        delete next[m.id];
        return next;
      });
      setMsg(`Материал «${m.original_filename}» удалён.`);
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingMaterialId(null);
    }
  }

  async function runDraftAgent(ev: FormEvent) {
    ev.preventDefault();
    if (!apiKey || !courseId) return;
    const ids = Object.entries(agentDocSelection)
      .filter(([, v]) => v)
      .map(([id]) => id);
    if (ids.length === 0) {
      setActionErr("Выберите хотя бы одну проиндексированную лекцию.");
      return;
    }
    const dq: Record<string, number> = {};
    agentQuota.forEach((n, i) => {
      if (n > 0) dq[String(i + 1)] = n;
    });
    if (agentQuotaTotal < 1 || agentQuotaTotal > 25) {
      setActionErr("Сумма задач по сложности должна быть от 1 до 25.");
      return;
    }
    if (agentKindTotal < 1) {
      setActionErr("Укажите количество задач хотя бы одного типа.");
      return;
    }
    if (agentKindTotal !== agentQuotaTotal) {
      setActionErr(
        `Сумма по типам (${agentKindTotal}) должна совпадать с суммой по сложности (${agentQuotaTotal}).`,
      );
      return;
    }
    const kq = {
      coding: agentKindQuota.coding,
      mcq: agentKindQuota.mcq,
      free_text: agentKindQuota.free_text,
    };
    setActionErr(null);
    setMsg(null);
    setAgentBusy(true);
    try {
      const out = await platformPostJson<{ job_id: string }>(
        `/api/platform/courses/${courseId}/draft-agent-jobs`,
        apiKey,
        { document_ids: ids, difficulty_quota: dq, kind_quota: kq },
      );
      const startedAt = Date.now();
      saveAgentDraftJob(courseId, { jobId: out.job_id, startedAt });
      setAgentJobId(out.job_id);
      setAgentJobStartedAt(startedAt);
      setAgentLive({ status: "PENDING" });
    } catch (e) {
      setActionErr(formatPlatformRequestError(e));
    } finally {
      setAgentBusy(false);
    }
  }

  async function saveProblemSettings(problemId: string) {
    if (!apiKey || !courseId) return;
    const row = probEdit[problemId];
    if (!row) return;
    setActionErr(null);
    try {
      await platformPatchJson(`/api/platform/courses/${courseId}/problems/${problemId}`, apiKey, {
        difficulty: row.d.trim() === "" ? null : parseInt(row.d, 10),
        max_attempts: row.m.trim() === "" ? null : parseInt(row.m, 10),
        score_policy: row.pol,
      });
      setMsg("Параметры задачи сохранены.");
      void loadAll();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function deleteProblem(p: InstructorProblemOut) {
    if (!apiKey || !courseId) return;
    if (
      !confirm(
        `Удалить задание «${p.title}»?\n\nСтуденты больше не увидят его, все попытки будут удалены без возможности восстановления.`,
      )
    ) {
      return;
    }
    setActionErr(null);
    setDeletingProblemId(p.id);
    try {
      await platformDelete(
        `/api/platform/courses/${courseId}/problems/${encodeURIComponent(p.id)}`,
        apiKey,
      );
      setProblems((prev) => prev.filter((row) => row.id !== p.id));
      setMsg(`Задание «${p.title}» удалено.`);
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingProblemId(null);
    }
  }

  async function deleteDraft(d: DraftRow) {
    if (!apiKey) return;
    if (!confirm(`Удалить черновик «${d.title || "Без названия"}»?`)) return;
    setActionErr(null);
    setDeletingDraftId(d.id);
    try {
      await platformDelete(`/api/platform/drafts/${encodeURIComponent(d.id)}`, apiKey);
      setDrafts((prev) => prev.filter((row) => row.id !== d.id));
      setMsg("Черновик удалён.");
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingDraftId(null);
    }
  }

  if (!courseId) return <p className="ds-alert ds-alert--err">Нет id курса</p>;

  return (
    <div className="t-page">
      <nav className="ds-breadcrumb">
        <Link to="/teacher/courses">Курсы</Link>
        <span className="ds-breadcrumb__sep">/</span>
        <span>{course?.title ?? "…"}</span>
      </nav>

      <header className="t-page__head">
        <h1 className="t-page__title">{course?.title ?? "Загрузка…"}</h1>
        <p className="t-page__sub">
          Slug: <code className="ds-code">{course?.slug}</code>
        </p>
      </header>

      {loadErr && <div className="ds-alert ds-alert--err">{loadErr}</div>}
      {loadWarn && <div className="ds-alert ds-mb">{loadWarn}</div>}
      {actionErr && <div className="ds-alert ds-alert--err">{actionErr}</div>}
      {msg && <div className="ds-alert ds-alert--ok">{msg}</div>}

      {agentJobId && agentJobStartedAt !== null && (
        <div className="t-agent-banner" role="status" aria-live="polite" aria-busy="true">
          <div className="t-agent-banner__track" aria-hidden>
            <div
              className="t-agent-banner__fill"
              style={{ width: `${agentLivePercent}%` }}
            />
          </div>
          <div className="t-agent-banner__row">
            <div className="t-agent-banner__spin" aria-hidden />
            <div className="t-agent-banner__text">
              <div className="t-agent-banner__title">
                {agentLive ? agentStatusTitle(agentLive.status) : "Запуск…"}
              </div>
              <div className="t-agent-banner__sub">
                {agentLive
                  ? agentFriendlyDetail(agentLive.status, agentLive.meta)
                  : "Подключаемся к материалам курса…"}
              </div>
              <ol className="t-agent-banner__steps" aria-label="Этапы генерации">
                {AGENT_PROGRESS_STEPS.map((step, i) => {
                  const done = i < agentLivePhaseIdx;
                  const active = i === agentLivePhaseIdx;
                  return (
                    <li
                      key={step.phase}
                      className={`t-agent-banner__step ${done ? "t-agent-banner__step--done" : ""} ${active ? "t-agent-banner__step--active" : ""}`}
                    >
                      <span className="t-agent-banner__step-dot" aria-hidden />
                      <span>{step.label}</span>
                    </li>
                  );
                })}
              </ol>
            </div>
            <div className="t-agent-banner__meta">
              <span className="t-agent-banner__sec">
                {Math.max(0, Math.floor((Date.now() - agentJobStartedAt) / 1000))}&nbsp;с
              </span>
            </div>
          </div>
        </div>
      )}

      <div className="ds-tabs">
        <button
          type="button"
          className={`ds-tab ${tab === "materials" ? "ds-tab--active" : ""}`}
          onClick={() => setTab("materials")}
        >
          Лекции и файлы
        </button>
        <button
          type="button"
          className={`ds-tab ${tab === "problems" ? "ds-tab--active" : ""}`}
          onClick={() => setTab("problems")}
        >
          Задания
        </button>
        <button
          type="button"
          className={`ds-tab ${tab === "studio" ? "ds-tab--active" : ""}`}
          onClick={() => setTab("studio")}
        >
          Конструктор
        </button>
        <button
          type="button"
          className={`ds-tab ${tab === "access" ? "ds-tab--active" : ""}`}
          onClick={() => setTab("access")}
        >
          Доступ
        </button>
        <button
          type="button"
          className={`ds-tab ${tab === "settings" ? "ds-tab--active" : ""}`}
          onClick={() => setTab("settings")}
        >
          Настройки
        </button>
      </div>

      {tab === "settings" && (
        <div className="ds-tab-panel ds-animate-in">
          <div className="ds-card ds-mb">
            <h2 className="t-page__h2">Чат и античит</h2>
            <p className="ds-caption ds-mb">
              Управление чат-ассистентом для студентов и защитой от подсказок по заданиям в RAG-чате.
              Флаги «Чат ИИ» для групп на вкладке{" "}
              <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => setTab("access")}>
                Доступ
              </button>{" "}
              по-прежнему действуют, когда чат включён.
            </p>
            <form className="ds-form t-course-settings" onSubmit={(e) => void saveCourseSettings(e)}>
              <label className="t-course-settings__row">
                <span className="t-course-settings__label">
                  <strong>Чат-ассистент</strong>
                  <span className="ds-caption">Студенты смогут выбрать курс в чате ИИ</span>
                </span>
                <input
                  type="checkbox"
                  className="t-course-settings__check"
                  checked={settingsChatEnabled}
                  onChange={(e) => setSettingsChatEnabled(e.target.checked)}
                />
              </label>

              <label className="ds-label">
                Античит в чате
                <select
                  className="ds-input"
                  value={settingsAntiCheat}
                  onChange={(e) =>
                    setSettingsAntiCheat(
                      e.target.value === "off" || e.target.value === "basic" ? e.target.value : "advanced",
                    )
                  }
                >
                  <option value="off">Выключен</option>
                  <option value="basic">Базовый (сопоставление с условием)</option>
                  <option value="advanced">Расширенный (ИИ-фильтр)</option>
                </select>
              </label>
              <p className="ds-caption" style={{ margin: "0.35rem 0 0" }}>
                {settingsAntiCheat === "off" && "Чат отвечает по лекциям без проверки на совпадение с заданиями."}
                {settingsAntiCheat === "basic" &&
                  "Вопрос сравнивается с текстом опубликованных заданий; при сильном совпадении готовое решение не выдаётся."}
                {settingsAntiCheat === "advanced" &&
                  "ИИ анализирует весь диалог и блокирует попытки получить решение домашних заданий."}
              </p>

              <button type="submit" className="ds-btn ds-btn--primary" disabled={settingsBusy}>
                {settingsBusy ? "Сохранение…" : "Сохранить настройки"}
              </button>
            </form>
          </div>
        </div>
      )}

      {tab === "access" && (
        <div className="ds-tab-panel ds-animate-in">
          <div className="ds-card ds-mb">
            <h2 className="t-page__h2">Режим видимости</h2>
            <p className="ds-caption ds-mb">
              <strong>Публичный</strong> — как раньше, любой по ссылке. <strong>По группам</strong> — список заданий видят только
              студенты с ключом, чья группа отмечена ниже («подключить группу к курсу»).
            </p>
            <form className="ds-form ds-mb" onSubmit={(e) => void saveCourseVisibility(e)}>
              <label className="ds-label">
                Режим
                <select
                  className="ds-input"
                  value={visibilityDraft}
                  onChange={(ev) =>
                    setVisibilityDraft(ev.target.value === "groups" ? "groups" : "public")
                  }
                >
                  <option value="public">Публичный</option>
                  <option value="groups">Только указанные группы</option>
                </select>
              </label>
              <button type="submit" className="ds-btn ds-btn--primary">
                Сохранить режим
              </button>
            </form>
          </div>
          <div className="ds-card">
            <h2 className="t-page__h2">Подключённые группы</h2>
            <p className="ds-caption ds-mb">
              Параметры: <strong>Задания</strong> — видеть список и открыть условие. <strong>Чат ИИ</strong> — студенческий
              чат по материалам курса (RAG). Перечень групп задаёт администратор в{" "}
              <Link to="/admin">/admin</Link>, преподаватель только подключает группы этого списка к курсу.
            </p>
            <p className="ds-caption ds-mb" style={{ opacity: 0.95 }}>
              <strong>Важно:</strong> сначала включите галочку <strong>В курсе</strong> для нужной строки и нажмите{" "}
              <strong>Сохранить политики</strong> — только тогда активируются столбцы «Задания» и «Чат ИИ». Режим видимости
              «Только указанные группы» сохраняется отдельно кнопкой <strong>Сохранить режим</strong>.
            </p>
            {studyGroups.length === 0 && (
              <p className="ds-empty">В системе пока нет групп — добавьте их в панели администратора (/admin).</p>
            )}
            {studyGroups.length > 0 && (
              <>
                <form className="ds-form" onSubmit={(e) => void saveGroupPolicies(e)}>
                  <table className="ds-table">
                    <thead>
                      <tr>
                        <th>Группа</th>
                        <th>В курсе</th>
                        <th>Задания</th>
                        <th>Чат ИИ (флаг)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {accessDraft.map((row, idx) => (
                        <tr key={row.study_group_id}>
                          <td>{row.title}</td>
                          <td>
                            <input
                              type="checkbox"
                              checked={row.linked}
                              aria-label={`Подключить ${row.title}`}
                              onChange={(ev) => {
                                const on = ev.target.checked;
                                setAccessDraft((prev) =>
                                  prev.map((r, i) =>
                                    i === idx
                                      ? on
                                        ? { ...r, linked: true, problems_visible: true, chat_ai_allowed: r.chat_ai_allowed }
                                        : { ...r, linked: false, problems_visible: false, chat_ai_allowed: false }
                                      : r,
                                  ),
                                );
                              }}
                            />
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              disabled={!row.linked}
                              checked={row.problems_visible}
                              onChange={(ev) =>
                                setAccessDraft((prev) =>
                                  prev.map((r, i) =>
                                    i === idx ? { ...r, problems_visible: ev.target.checked } : r,
                                  ),
                                )
                              }
                            />
                          </td>
                          <td>
                            <input
                              type="checkbox"
                              disabled={!row.linked}
                              checked={row.chat_ai_allowed}
                              onChange={(ev) =>
                                setAccessDraft((prev) =>
                                  prev.map((r, i) =>
                                    i === idx ? { ...r, chat_ai_allowed: ev.target.checked } : r,
                                  ),
                                )
                              }
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <button type="submit" className="ds-btn ds-btn--primary ds-mt">
                    Сохранить политики
                  </button>
                </form>
              </>
            )}
          </div>
        </div>
      )}

      {tab === "materials" && (
        <div className="ds-tab-panel ds-animate-in">
          <div className="ds-card ds-mb">
            <h2 className="t-page__h2">Загрузить материал</h2>
            <form className="ds-form" onSubmit={(e) => void onUpload(e)}>
              <div className="ds-label" style={{ display: "block" }}>
                <span style={{ marginBottom: "0.4rem", display: "inline-block" }}>Файлы</span>
                <div
                  role="button"
                  tabIndex={0}
                  className={`ds-dropzone ${dropActive ? "ds-dropzone--active" : ""}`}
                  onClick={() => fileInputRef.current?.click()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                  onDragEnter={onDropZoneDragEnter}
                  onDragLeave={onDropZoneDragLeave}
                  onDragOver={onDropZoneDragOver}
                  onDrop={onDropZoneDrop}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    className="ds-visually-hidden"
                    tabIndex={-1}
                    onChange={(e) => {
                      mergeFileLists(Array.from(e.target.files ?? []));
                      e.target.value = "";
                    }}
                  />
                  {!pickedFiles.length ? (
                    <>
                      <p className="ds-dropzone__title">Перетащите файлы сюда</p>
                      <p className="ds-dropzone__hint">
                        Отпустите для добавления в очередь. Либо нажмите в этой области, чтобы выбрать через
                        диалог системы — можно несколько сразу.
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="ds-dropzone__title">В очереди: {pickedFiles.length}</p>
                      <p className="ds-dropzone__hint">
                        Перетащите ещё файлы или нажмите сюда, чтобы добавить. Все отправятся по очереди.
                      </p>
                      <ul className="ds-dropzone__list">
                        {pickedFiles.map((f, idx) => (
                          <li key={`${idx}-${f.name}-${f.lastModified}`} className="ds-dropzone__row">
                            <span>
                              <strong>{f.name}</strong>
                              <span className="ds-caption" style={{ marginLeft: "0.35rem" }}>
                                {f.size.toLocaleString()} байт
                              </span>
                            </span>
                            <button
                              type="button"
                              className="ds-btn ds-btn--ghost ds-btn--sm"
                              onClick={(ev) => {
                                ev.stopPropagation();
                                setPickedFiles((prev) => prev.filter((_, i) => i !== idx));
                              }}
                            >
                              Убрать
                            </button>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              </div>
              <label className="ds-label">
                Тема для чанков (опционально)
                <input
                  className="ds-input"
                  value={uploadSubject}
                  onChange={(e) => setUploadSubject(e.target.value)}
                  placeholder="По умолчанию — из курса"
                />
              </label>
              <button
                type="submit"
                className="ds-btn ds-btn--primary"
                disabled={uploadBusy || pickedFiles.length === 0}
              >
                {uploadBusy ? "Загрузка…" : "Отправить в очередь индексации"}
              </button>
            </form>
          </div>

          {Object.keys(jobMap).length > 0 && (
            <div className="ds-card ds-mb">
              <h2 className="t-page__h2">Очередь индексации</h2>
              <table className="ds-table">
                <thead>
                  <tr>
                    <th>Задача</th>
                    <th>Файл</th>
                    <th>Статус</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(jobMap).map(([jid, tr]) => (
                    <tr key={jid}>
                      <td>
                        <code className="ds-code ds-code--sm">{jid.slice(0, 10)}…</code>
                      </td>
                      <td>{tr.filename}</td>
                      <td>
                        <span className="ds-badge">{tr.status}</span>
                        {tr.error && <div className="ds-caption ds-text-err">{tr.error}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

            <div className="ds-card">
            <div className="t-page__row">
              <h2 className="t-page__h2 t-page__h2--flush">Загруженные материалы</h2>
              <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => void loadAll()}>
                Обновить
              </button>
            </div>
            <p className="ds-caption" style={{ marginBottom: "0.5rem" }}>
              Файлы, готовые для чата и генерации задач.
            </p>
            {materials.length === 0 && <p className="ds-empty">Пока нет загруженных материалов.</p>}
            {materials.length > 0 && (
              <table className="ds-table">
                <thead>
                  <tr>
                    <th>Файл</th>
                    <th>Статус</th>
                    <th>Чанков</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {materials.map((m) => (
                    <tr key={m.id}>
                      <td>
                        <div className="ds-cell-title">{m.original_filename}</div>
                        <div className="ds-caption">{m.subject}</div>
                      </td>
                      <td>
                        <span className={`ds-pill ds-pill--${m.index_status === "indexed" ? "ok" : m.index_status === "failed" ? "err" : "wait"}`}>
                          {materialIndexStatusLabel(m.index_status)}
                        </span>
                      </td>
                      <td>{m.chunks_indexed}</td>
                      <td>
                        <div style={{ display: "flex", gap: "0.35rem", justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            className="ds-btn ds-btn--ghost ds-btn--sm"
                            onClick={() => void downloadMaterial(m)}
                          >
                            Скачать
                          </button>
                          <button
                            type="button"
                            className="ds-btn ds-btn--ghost ds-btn--sm"
                            disabled={deletingMaterialId === m.id}
                            onClick={() => void deleteMaterial(m)}
                          >
                            {deletingMaterialId === m.id ? "Удаление…" : "Удалить"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="ds-card ds-mt">
            <h2 className="t-page__h2">Ошибки загрузки</h2>
            <p className="ds-caption" style={{ marginBottom: "0.5rem" }}>
              Файлы, которые не удалось обработать.
            </p>
            {failedMaterials.length === 0 && diskHistory.length === 0 && (
              <p className="ds-empty">Пока нет ошибок загрузки/индексации для этого курса.</p>
            )}
            {failedMaterials.length > 0 && (
              <>
                <h3 className="t-page__h2" style={{ fontSize: "1rem" }}>
                  Неудачные загрузки
                </h3>
                <table className="ds-table ds-mb">
                  <thead>
                    <tr>
                      <th>Файл</th>
                      <th>Время</th>
                      <th>Ошибка</th>
                    </tr>
                  </thead>
                  <tbody>
                    {failedMaterials.map((m) => (
                      <tr key={m.id}>
                        <td>{m.original_filename}</td>
                        <td>{m.created_at ?? "—"}</td>
                        <td className="ds-text-err">{m.celery_error ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
            {diskHistory.length > 0 && (
              <>
                <h3 className="t-page__h2" style={{ fontSize: "1rem", marginTop: "1rem" }}>
                  Журнал
                </h3>
                <table className="ds-table">
                  <thead>
                    <tr>
                      <th>Время</th>
                      <th>Файл</th>
                      <th>Задача</th>
                      <th>Сообщение</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diskHistory.map((h, idx) => (
                      <tr key={`${h.ts}-${idx}`}>
                        <td>{h.ts}</td>
                        <td>{h.filename ?? "—"}</td>
                        <td>
                          <code className="ds-code ds-code--sm">{h.job_id?.slice(0, 12) ?? "—"}…</code>
                        </td>
                        <td className="ds-text-err">{h.error ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      )}

      {tab === "problems" && (
        <div className="ds-tab-panel ds-animate-in">
          <div className="ds-card">
            <div className="t-page__row">
              <div>
                <h2 className="t-page__h2 t-page__h2--flush">Задания курса</h2>
                <p className="ds-caption" style={{ margin: "0.35rem 0 0" }}>
                  Опубликованные задачи, которые видят студенты. Настройте сложность и попытки прямо здесь.
                </p>
              </div>
              <button type="button" className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => void loadAll()}>
                Обновить
              </button>
            </div>

            {problems.length === 0 ? (
              <p className="ds-empty">Заданий ещё нет. Сгенерируйте черновики на вкладке «Студия» или опубликуйте их после ревью.</p>
            ) : (
              <div className="t-task-grid">
                {problems.map((p) => (
                  <article key={p.id} className="t-task-card">
                    <header className="t-task-card__head">
                      <div className="t-task-card__tags">
                        <span className="t-task-chip">{problemKindLabel(p.kind)}</span>
                        {!p.published ? (
                          <span className="t-task-chip t-task-chip--muted">Скрыто от студентов</span>
                        ) : null}
                      </div>
                      <h3 className="t-task-card__title">{p.title}</h3>
                      <p className="t-task-card__meta">
                        {p.max_score} б.
                        {typeof p.difficulty === "number" ? ` · сложность ${p.difficulty}/10` : ""}
                      </p>
                    </header>

                    <div className="t-task-card__settings">
                      <label className="t-prob-inst-field">
                        Сложность
                        <input
                          className="ds-input"
                          type="number"
                          min={1}
                          max={10}
                          placeholder="1–10"
                          value={probEdit[p.id]?.d ?? ""}
                          onChange={(ev) =>
                            setProbEdit((prev) => ({
                              ...prev,
                              [p.id]: { ...(prev[p.id] ?? { d: "", m: "", pol: "best" }), d: ev.target.value },
                            }))
                          }
                        />
                      </label>
                      <label className="t-prob-inst-field">
                        Попыток
                        <input
                          className="ds-input"
                          type="number"
                          min={1}
                          max={999}
                          placeholder="∞"
                          value={probEdit[p.id]?.m ?? ""}
                          onChange={(ev) =>
                            setProbEdit((prev) => ({
                              ...prev,
                              [p.id]: { ...(prev[p.id] ?? { d: "", m: "", pol: "best" }), m: ev.target.value },
                            }))
                          }
                        />
                      </label>
                      <label className="t-prob-inst-field">
                        Учёт балла
                        <select
                          className="ds-input"
                          value={probEdit[p.id]?.pol ?? "best"}
                          onChange={(ev) =>
                            setProbEdit((prev) => ({
                              ...prev,
                              [p.id]: {
                                ...(prev[p.id] ?? { d: "", m: "", pol: "best" }),
                                pol: ev.target.value === "last" ? "last" : "best",
                              },
                            }))
                          }
                        >
                          <option value="best">Лучшая</option>
                          <option value="last">Последняя</option>
                        </select>
                      </label>
                      <button
                        type="button"
                        className="ds-btn ds-btn--ghost ds-btn--sm t-task-card__save"
                        onClick={() => void saveProblemSettings(p.id)}
                      >
                        Сохранить
                      </button>
                    </div>

                    <footer className="t-task-card__actions">
                      <Link
                        to={`/teacher/courses/${encodeURIComponent(courseId!)}/problems/${encodeURIComponent(p.id)}/edit`}
                        className="ds-btn ds-btn--ghost ds-btn--sm"
                      >
                        Редактировать
                      </Link>
                      {p.published && course ? (
                        <Link
                          to={`/c/${encodeURIComponent(course.slug)}/p/${p.id}`}
                          className="ds-btn ds-btn--ghost ds-btn--sm"
                        >
                          Как студент
                        </Link>
                      ) : null}
                      <button
                        type="button"
                        className="ds-btn ds-btn--ghost ds-btn--sm t-task-card__danger"
                        disabled={deletingProblemId === p.id}
                        onClick={() => void deleteProblem(p)}
                      >
                        {deletingProblemId === p.id ? "Удаление…" : "Удалить"}
                      </button>
                    </footer>
                  </article>
                ))}
              </div>
            )}
          </div>

          <div className="ds-card ds-mt">
            <div className="t-page__row">
              <div>
                <h2 className="t-page__h2 t-page__h2--flush">Черновики на проверке</h2>
                <p className="ds-caption" style={{ margin: "0.35rem 0 0" }}>
                  Задачи от генератора, которые ещё не опубликованы. Откройте ревью, отредактируйте и опубликуйте.
                </p>
              </div>
            </div>

            {pendingDrafts.length === 0 ? (
              <p className="ds-empty">Нет черновиков на проверке.</p>
            ) : (
              <div className="t-task-grid t-task-grid--drafts">
                {pendingDrafts.map((d) => (
                  <article key={d.id} className="t-task-card t-task-card--draft">
                    <header className="t-task-card__head">
                      <div className="t-task-card__tags">
                        <span className="t-task-chip">{problemKindLabel(d.kind)}</span>
                        {typeof d.difficulty === "number" ? (
                          <span className="t-task-chip t-task-chip--muted">сложность {d.difficulty}/10</span>
                        ) : null}
                      </div>
                      <Link
                        className="t-task-card__title t-task-card__title--link"
                        to={`/teacher/courses/${encodeURIComponent(courseId!)}/drafts/${encodeURIComponent(d.id)}`}
                      >
                        {d.title || "Без названия"}
                      </Link>
                    </header>
                    <footer className="t-task-card__actions">
                      <Link
                        className="ds-btn ds-btn--primary ds-btn--sm"
                        to={`/teacher/courses/${encodeURIComponent(courseId!)}/drafts/${encodeURIComponent(d.id)}`}
                      >
                        Открыть ревью
                      </Link>
                      <button
                        type="button"
                        className="ds-btn ds-btn--ghost ds-btn--sm t-task-card__danger"
                        disabled={deletingDraftId === d.id}
                        onClick={() => void deleteDraft(d)}
                      >
                        {deletingDraftId === d.id ? "Удаление…" : "Удалить"}
                      </button>
                    </footer>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === "studio" && (
        <div className="ds-tab-panel ds-animate-in">
          <div className="t-agent-studio">
            <header className="t-agent-studio__intro">
              <h2 className="t-page__h2 t-agent-studio__title">Генератор заданий</h2>
              <p className="ds-caption">
                Отметьте лекции, укажите типы и сложность черновиков. За один запуск — не более{" "}
                <strong>25</strong> задач; сумма по типам должна совпадать с суммой по сложности.
              </p>
            </header>

            {indexedMaterials.length === 0 ? (
              <div className="ds-card">
                <p className="ds-empty">
                  Нет готовых материалов. Загрузите файлы на вкладке «Лекции и файлы» и дождитесь окончания обработки.
                </p>
              </div>
            ) : (
              <>
                <div className="t-agent-studio__summary" aria-label="Параметры запуска">
                  <div className="t-agent-studio__stat">
                    <span className="t-agent-studio__stat-n">{agentSelectedLectureCount}</span>
                    <span className="t-agent-studio__stat-l">
                      {agentSelectedLectureCount === 1 ? "лекция" : agentSelectedLectureCount >= 2 && agentSelectedLectureCount <= 4 ? "лекции" : "лекций"}
                    </span>
                  </div>
                  <div className="t-agent-studio__stat">
                    <span className="t-agent-studio__stat-n">{agentQuotaTotal}</span>
                    <span className="t-agent-studio__stat-l">задач</span>
                  </div>
                  <div className="t-agent-studio__stat t-agent-studio__stat--wide">
                    <span className="t-agent-studio__stat-l">Типы</span>
                    <span className="t-agent-studio__stat-kinds">{kindQuotaPreview(agentKindQuota)}</span>
                  </div>
                  <div
                    className={`t-agent-studio__match ${agentQuotasMatch ? "t-agent-studio__match--ok" : agentQuotaTotal > 0 || agentKindTotal > 0 ? "t-agent-studio__match--warn" : ""}`}
                  >
                    {agentQuotasMatch
                      ? "Сложность и типы согласованы"
                      : agentQuotaTotal > 0 || agentKindTotal > 0
                        ? `Сложность: ${agentQuotaTotal} · типы: ${agentKindTotal}`
                        : "Задайте сложность и типы"}
                  </div>
                  <div className="t-agent-studio__quota-bar" aria-hidden>
                    <div
                      className={`t-agent-studio__quota-fill ${agentQuotaTotal > 25 ? "t-agent-studio__quota-fill--bad" : ""}`}
                      style={{ width: `${Math.min(100, (agentQuotaTotal / 25) * 100)}%` }}
                    />
                  </div>
                </div>

              <form className="t-agent-studio__grid" onSubmit={(e) => void runDraftAgent(e)}>
                <section className="t-agent-studio__panel t-agent-studio__panel--lec">
                  <div className="t-agent-studio__panel-head">
                    <div>
                      <h3 className="t-agent-studio__h3">Источники</h3>
                      <p className="ds-caption" style={{ margin: "0.25rem 0 0" }}>
                        Задания будут составлены только по отмеченным файлам.
                        {agentSelectedLectureCount > 0 && (
                          <span className="t-agent-studio__badge"> {agentSelectedLectureCount} выбрано</span>
                        )}
                      </p>
                    </div>
                    <div className="t-agent-studio__toolbar">
                      <button
                        type="button"
                        className="ds-btn ds-btn--ghost ds-btn--sm"
                        onClick={() => {
                          const next: Record<string, boolean> = {};
                          for (const m of indexedMaterials) next[m.id] = true;
                          setAgentDocSelection(next);
                        }}
                      >
                        Все
                      </button>
                      <button
                        type="button"
                        className="ds-btn ds-btn--ghost ds-btn--sm"
                        onClick={() => setAgentDocSelection({})}
                      >
                        Снять
                      </button>
                    </div>
                  </div>
                  <ul className="t-agent-lec">
                    {indexedMaterials.map((m) => {
                      const on = Boolean(agentDocSelection[m.id]);
                      return (
                        <li key={m.id}>
                          <button
                            type="button"
                            className={`t-agent-lec__card ${on ? "t-agent-lec__card--on" : ""}`}
                            onClick={() =>
                              setAgentDocSelection((prev) => ({
                                ...prev,
                                [m.id]: !on,
                              }))
                            }
                          >
                            <span className={`t-agent-lec__check ${on ? "t-agent-lec__check--on" : ""}`} aria-hidden />
                            <span className="t-agent-lec__body">
                              <span className="t-agent-lec__name">{m.original_filename}</span>
                              <span className="t-agent-lec__meta">
                                {m.chunks_indexed} фрагментов
                              </span>
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </section>

                <section className="t-agent-studio__panel t-agent-studio__panel--quota">
                  <div className="t-agent-studio__panel-head">
                    <div>
                      <h3 className="t-agent-studio__h3">Типы и сложность</h3>
                      <p className="ds-caption" style={{ margin: "0.25rem 0 0" }}>
                        Сначала типы задач, затем распределение по уровням 1–10.
                      </p>
                    </div>
                  </div>

                  <div className="t-agent-kind-block">
                    <div className="t-agent-kind-block__head">
                      <span className="t-agent-kind-block__title">Типы задач</span>
                      <button
                        type="button"
                        className="ds-btn ds-btn--ghost ds-btn--sm"
                        disabled={agentQuotaTotal < 1}
                        onClick={() => setAgentKindQuota(distributeKindsEvenly(agentQuotaTotal))}
                      >
                        Поровну
                      </button>
                    </div>
                    <ul className="t-agent-kind">
                      {AGENT_KIND_KEYS.map((key) => (
                        <li key={key} className="t-agent-kind__row">
                          <div className="t-agent-kind__label">
                            <span className="t-agent-kind__name">{AGENT_KIND_LABELS[key]}</span>
                          </div>
                          <div className="t-agent-quota__ctrl">
                            <button
                              type="button"
                              className="t-agent-quota__btn"
                              aria-label={`Уменьшить ${AGENT_KIND_LABELS[key]}`}
                              onClick={() => bumpAgentKind(key, -1)}
                            >
                              −
                            </button>
                            <span className="t-agent-quota__val">{agentKindQuota[key]}</span>
                            <button
                              type="button"
                              className="t-agent-quota__btn"
                              aria-label={`Увеличить ${AGENT_KIND_LABELS[key]}`}
                              onClick={() => bumpAgentKind(key, 1)}
                            >
                              +
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                    <p
                      className={`t-agent-quota__sum ${agentKindTotal !== agentQuotaTotal && (agentKindTotal > 0 || agentQuotaTotal > 0) ? "t-agent-quota__sum--bad" : ""}`}
                    >
                      По типам: <strong>{agentKindTotal}</strong>
                      {agentQuotaTotal > 0 && (
                        <>
                          {" "}
                          / {agentQuotaTotal} по сложности
                        </>
                      )}
                      {agentKindTotal !== agentQuotaTotal && agentQuotaTotal > 0 && (
                        <span className="t-agent-quota__warn"> — выровняйте суммы</span>
                      )}
                    </p>
                  </div>

                  <div className="t-agent-kind-block t-agent-kind-block--diff">
                    <div className="t-agent-kind-block__head">
                      <span className="t-agent-kind-block__title">Сложность</span>
                    </div>
                  <ul className="t-agent-quota">
                    {agentQuota.map((n, i) => (
                      <li key={i} className="t-agent-quota__row">
                        <div className="t-agent-quota__label">
                          <span className="t-agent-quota__lvl">{i + 1}</span>
                          <span className="t-agent-quota__hint">{DIFF_SHORT[i + 1] ?? ""}</span>
                        </div>
                        <div className="t-agent-quota__ctrl">
                          <button
                            type="button"
                            className="t-agent-quota__btn"
                            aria-label={`Уменьшить уровень ${i + 1}`}
                            onClick={() => bumpAgentQuota(i, -1)}
                          >
                            −
                          </button>
                          <span className="t-agent-quota__val">{n}</span>
                          <button
                            type="button"
                            className="t-agent-quota__btn"
                            aria-label={`Увеличить уровень ${i + 1}`}
                            onClick={() => bumpAgentQuota(i, 1)}
                          >
                            +
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                  <p
                    className={`t-agent-quota__sum ${agentQuotaTotal > 25 ? "t-agent-quota__sum--bad" : ""}`}
                  >
                    Всего: <strong>{agentQuotaTotal}</strong> / 25
                    {agentQuotaTotal > 25 && (
                      <span className="t-agent-quota__warn"> — уменьшите квоты</span>
                    )}
                  </p>
                  </div>

                  <div className="t-agent-studio__submit">
                    <button
                      type="submit"
                      className="ds-btn ds-btn--primary t-agent-studio__run"
                      disabled={
                        agentBusy ||
                        Boolean(agentJobId) ||
                        agentQuotaTotal < 1 ||
                        agentQuotaTotal > 25 ||
                        agentSelectedLectureCount < 1 ||
                        !agentQuotasMatch
                      }
                    >
                      {agentBusy || agentJobId ? (
                        <>
                          <span className="t-agent-studio__run-spin" aria-hidden />
                          Генерация…
                        </>
                      ) : (
                        "Сгенерировать черновики"
                      )}
                    </button>
                    <p className="ds-caption" style={{ margin: 0 }}>
                      {agentSelectedLectureCount < 1
                        ? "Выберите хотя бы одну лекцию."
                        : agentQuotaTotal < 1
                          ? "Укажите количество задач хотя бы на одном уровне сложности."
                          : agentKindTotal < 1
                            ? "Укажите количество задач хотя бы одного типа."
                            : !agentQuotasMatch
                              ? "Сумма по типам должна совпадать с суммой по сложности."
                              : "Ход генерации отображается в полосе над вкладками."}
                    </p>
                  </div>
                </section>
              </form>
              </>
            )}

            <div className="ds-card ds-card--dashed ds-mt">
              <h2 className="t-page__h2">Ручной конструктор</h2>
              <p className="ds-caption">Создание задачи вручную (код / тесты / MCQ) — позже.</p>
              <button type="button" className="ds-btn" disabled>
                Скоро
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
