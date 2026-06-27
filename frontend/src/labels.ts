/** Человекочитаемые подписи вместо сырых enum из API. */

export function problemKindLabel(kind: string): string {
  switch (kind) {
    case "coding":
      return "Программирование";
    case "mcq":
      return "Тест";
    case "free_text":
      return "Свободный ответ";
    default:
      return kind;
  }
}

export function courseVisibilityLabel(mode: string | undefined): string {
  switch (mode) {
    case "public":
      return "Открытый";
    case "groups":
      return "По группам";
    default:
      return "";
  }
}

export function weakSkillLabel(kind: string | null | undefined): string {
  if (!kind) return "Пока без явного слабого места";
  return problemKindLabel(kind);
}

export function draftStatusLabel(status: string): string {
  switch (status) {
    case "pending_review":
      return "На проверке";
    case "published":
      return "Опубликован";
    case "discarded":
      return "Отклонён";
    default:
      return "";
  }
}

export function materialIndexStatusLabel(status: string): string {
  switch (status) {
    case "indexed":
      return "Готов";
    case "failed":
      return "Ошибка";
    case "pending":
      return "В обработке";
    default:
      return status;
  }
}

export function friendlyHttpError(err: unknown, fallback = "Не удалось выполнить запрос."): string {
  const raw = err instanceof Error ? err.message : String(err);
  if (/^\s*401\b/.test(raw)) return "Неверный логин или пароль.";
  if (/^\s*403\b/.test(raw)) return "Нет доступа. Обратитесь к преподавателю.";
  if (/^\s*404\b/.test(raw)) return "Не найдено.";
  if (/^\s*413\b/.test(raw)) return "Файл слишком большой.";
  if (/^\s*5\d{2}\b/.test(raw)) return "Сервис временно недоступен. Попробуйте позже.";
  if (/^\s*\d{3}\b/.test(raw)) return fallback;
  return raw || fallback;
}
