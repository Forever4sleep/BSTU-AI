import { buildApiUrl } from "../api";

export type ChatRole = "system" | "user" | "assistant";

export type ChatMessage = {
  role: ChatRole;
  content: string;
};

/** POST /v1/chat/completions с stream: true, разбор SSE (data: {json}). */
export async function streamChatCompletion(options: {
  messages: ChatMessage[];
  /** Если не передать — сервер возьмёт модель из конфигурации. */
  model?: string | null;
  /** RAG по UUID курса; вместе с courseSlug передаётся только один из двух. */
  courseId?: string | null;
  /** Альтернатива UUID (slug из URL курса) — поддержка старых ответов без поля ``id``. */
  courseSlug?: string | null;
  /** Bearer платформы (JWT) допускается — бэкенд подставит OpenRouter-ключ из .env. */
  bearer?: string | null;
  signal?: AbortSignal;
  onDelta: (fragment: string) => void;
}): Promise<void> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (options.bearer?.trim()) {
    headers.Authorization = `Bearer ${options.bearer.trim()}`;
  }

  const r = await fetch(buildApiUrl("/v1/chat/completions"), {
    method: "POST",
    headers,
    body: JSON.stringify({
      ...(options.model?.trim() ? { model: options.model.trim() } : {}),
      messages: options.messages,
      stream: true,
      ...(options.courseId?.trim()
        ? { bstu_course_id: options.courseId.trim() }
        : options.courseSlug?.trim()
          ? { bstu_course_slug: options.courseSlug.trim().toLowerCase() }
          : {}),
    }),
    signal: options.signal,
  });

  if (!r.ok || !r.body) {
    const t = await r.text();
    throw new Error(`${r.status} ${t}`);
  }

  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let deltasEmitted = 0;

  const pumpLine = (lineRaw: string) => {
    const line = lineRaw.trim();
    if (!line.startsWith("data:")) return;
    const payload = line.slice(5).trim();
    if (payload === "[DONE]") return;
    let obj: unknown;
    try {
      obj = JSON.parse(payload);
    } catch {
      return;
    }
    if (!obj || typeof obj !== "object") return;
    const o = obj as {
      error?: { message?: string } | string;
      choices?: Array<{ delta?: { content?: string | null }; message?: { content?: string } }>;
    };
    if (o.error) {
      const em =
        typeof o.error === "string"
          ? o.error
          : typeof o.error?.message === "string"
            ? o.error.message
            : JSON.stringify(o.error);
      throw new Error(em || "Ошибка потока от модели");
    }
    const choice = o.choices?.[0];
    let c = choice?.delta?.content;
    if ((c === undefined || c === null) && typeof choice?.message?.content === "string") {
      c = choice.message.content;
    }
    if (typeof c === "string" && c.length) {
      deltasEmitted += 1;
      options.onDelta(c);
    }
  };

  const pumpBlock = (block: string) => {
    for (const rawLine of block.split("\n")) {
      pumpLine(rawLine);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const chunks = buf.split(/\n\n+/);
    buf = chunks.pop() ?? "";
    for (const chunk of chunks) {
      pumpBlock(chunk);
    }
  }
  if (buf.trim()) pumpBlock(buf);

  if (deltasEmitted === 0) {
    throw new Error(
      "Модель не вернула ответ. Проверьте, что для курса загружены материалы и включён чат с ИИ.",
    );
  }
}
