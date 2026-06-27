/** UI для генерации черновиков — без технических логов в интерфейсе преподавателя. */

export type AgentKindKey = "coding" | "mcq" | "free_text";

export const AGENT_KIND_KEYS: AgentKindKey[] = ["coding", "mcq", "free_text"];

export const AGENT_KIND_LABELS: Record<AgentKindKey, string> = {
  coding: "Программирование",
  mcq: "Тест",
  free_text: "Свободный ответ",
};

export const AGENT_KIND_SHORT: Record<AgentKindKey, string> = {
  coding: "код",
  mcq: "тест",
  free_text: "текст",
};

export type AgentProgressPhase = "queue" | "analyze" | "generate" | "finish";

export const AGENT_PROGRESS_STEPS: { phase: AgentProgressPhase; label: string }[] = [
  { phase: "queue", label: "Старт" },
  { phase: "analyze", label: "Лекции" },
  { phase: "generate", label: "Задачи" },
  { phase: "finish", label: "Готово" },
];

export function agentStatusTitle(status: string): string {
  switch (status) {
    case "PENDING":
      return "Ожидание";
    case "STARTED":
      return "Запуск";
    case "PROGRESS":
      return "Генерация";
    case "SUCCESS":
      return "Готово";
    case "FAILURE":
      return "Ошибка";
    default:
      return "Генерация";
  }
}

export function agentPhaseFromMeta(meta?: { phase?: string; label?: string }): AgentProgressPhase {
  const p = (meta?.phase ?? "").trim().toLowerCase();
  if (p === "analyze" || p === "context" || p === "plan") return "analyze";
  if (p === "generate" || p === "agent") return "generate";
  if (p === "finish" || p === "done") return "finish";
  return "queue";
}

export function agentPhaseIndex(phase: AgentProgressPhase): number {
  return AGENT_PROGRESS_STEPS.findIndex((s) => s.phase === phase);
}

export function agentProgressPercent(phase: AgentProgressPhase): number {
  switch (phase) {
    case "queue":
      return 12;
    case "analyze":
      return 38;
    case "generate":
      return 72;
    case "finish":
      return 100;
    default:
      return 8;
  }
}

export function agentFriendlyDetail(
  status: string,
  meta?: { phase?: string; label?: string },
): string {
  const label = (meta?.label ?? "").trim();
  if (label && !label.startsWith("[")) return label;

  switch (status) {
    case "PENDING":
      return "Готовим генератор задач…";
    case "STARTED":
      return "Подключаемся к материалам курса…";
    case "PROGRESS":
      switch (agentPhaseFromMeta(meta)) {
        case "analyze":
          return "Изучаем выбранные лекции…";
        case "generate":
          return "ИИ составляет формулировки и эталоны…";
        case "finish":
          return "Сохраняем черновики…";
        default:
          return "Генерируем черновики…";
      }
    default:
      return "Генерируем черновики…";
  }
}

export function agentGenerationResultMessage(created: number, warnings?: string[]): string {
  if (created > 0) {
    const w = warnings?.filter(Boolean).length ?? 0;
    if (w > 0) {
      return `Готово: создано ${created} черновик${draftWordEnding(created)}. Часть слотов пропущена — откройте вкладку «Задания».`;
    }
    return `Готово: ${created} черновик${draftWordEnding(created)} на проверке. Откройте вкладку «Задания».`;
  }
  return "Черновики не созданы. Попробуйте меньше задач за раз или другие лекции.";
}

function draftWordEnding(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "";
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return "а";
  return "ов";
}

export function kindQuotaPreview(quotas: Record<AgentKindKey, number>): string {
  const parts = AGENT_KIND_KEYS.filter((k) => quotas[k] > 0).map(
    (k) => `${quotas[k]} ${AGENT_KIND_SHORT[k]}`,
  );
  return parts.length ? parts.join(" · ") : "—";
}

export function distributeKindsEvenly(total: number): Record<AgentKindKey, number> {
  if (total <= 0) return { coding: 0, mcq: 0, free_text: 0 };
  const base = Math.floor(total / 3);
  let rem = total - base * 3;
  const out: Record<AgentKindKey, number> = { coding: base, mcq: base, free_text: base };
  for (const k of AGENT_KIND_KEYS) {
    if (rem <= 0) break;
    out[k] += 1;
    rem -= 1;
  }
  return out;
}

/** @deprecated используйте kindQuotaPreview */
export function kindRotationPreview(total: number): string {
  return kindQuotaPreview(distributeKindsEvenly(total));
}
