"""
Монолитная конфигурация приложения.

Читает все переменные из .env через Pydantic BaseSettings.
"""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Единая конфигурация из .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram Bots ---
    telegram_bot_token: str | None = Field(
        default=None,
        description="Токен основного бота (студенты)",
    )
    upload_bot_token: str | None = Field(
        default=None,
        description="Токен бота загрузки документов",
    )
    ingestion_service_url: str = Field(
        default="http://localhost:8001",
        description="URL Ingestion Service",
    )
    allowed_upload_user_ids: str = Field(
        default="",
        description="Telegram user IDs для upload (через запятую, пусто = все)",
    )

    # --- OpenRouter / LLM ---
    openrouter_api_key: str | None = Field(default=None, description="OpenRouter API key")
    openai_api_key: str | None = Field(default=None, description="OpenAI API key (fallback)")
    openrouter_model: str = Field(
        default="openai/gpt-4o-mini",
        description="Модель для LLM и intent classification",
    )
    enable_thinking: bool = Field(
        default=True,
        description="Включить reasoning/thinking у LLM (OpenRouter reasoning param)",
    )

    # --- Qdrant ---
    qdrant_host: str = Field(default="localhost", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant port")
    qdrant_collection_name: str = Field(
        default="bstu_materials",
        description="Коллекция материалов",
    )

    # --- RAG (Open WebUI / v1 chat) ---
    rag_enabled: bool = Field(
        default=True,
        description="Включить retrieval + контекст в /v1/chat/completions",
    )
    rag_top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Сколько чанков подмешивать в промпт (после fusion)",
    )
    rag_bm25_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Top-k для BM25-ветки hybrid retrieval",
    )
    rag_bm25_max_docs: int = Field(
        default=10_000,
        ge=256,
        le=500_000,
        description="Макс. документов из Qdrant для построения BM25-корпуса",
    )
    rag_hybrid_alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="alpha·dense + (1−alpha)·BM25; 1.0 = только dense, 0.0 = только BM25",
    )
    rag_query_max_turns: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Сколько последних user-сообщений склеивать для retrieval-запроса",
    )
    rag_relevance_threshold: float = Field(
        default=0.0,
        ge=0.0,
        description="Минимальный RRF-скор лучшего документа; ниже — отказ. 0 = отключено",
    )
    rag_problem_match_enabled: bool = Field(
        default=True,
        description="Глобальный выключатель античита; при false режим курса игнорируется",
    )
    rag_problem_match_threshold: float = Field(
        default=0.82,
        ge=0.0,
        le=1.0,
        description="Порог cosine similarity для базового античита (сопоставление с условием задачи)",
    )

    # --- Ingestion Service ---
    ingestion_service_port: int = Field(default=8001, description="Порт API")
    log_level: str = Field(default="INFO", description="Уровень логирования")

    # --- Celery ---
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL для Celery",
    )
    celery_result_backend: str | None = Field(
        default=None,
        description="Result backend (default: тот же что broker)",
    )

    # --- Chunking ---
    chunk_size: int = Field(default=500, description="Размер чанка (символов)")
    chunk_overlap: int = Field(default=50, description="Overlap чанков")
    chunk_strategy: str = Field(
        default="sliding_window",
        description="Стратегия: sliding_window | recursive",
    )

    # --- VLM (PDF extraction via Docling) ---
    vlm_model: str = Field(
        default="qwen/qwen-2.5-vl-7b-instruct",
        description="VLM для извлечения текста из PDF (OpenRouter)",
    )
    vlm_timeout: int = Field(
        default=120,
        description="Timeout VLM запросов (сек)",
    )
    vlm_concurrency: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Параллельных запросов к VLM API (OpenRouter) на одну PDF",
    )
    vlm_batch_size: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Страниц PDF в одной партии (Docling settings.perf.page_batch_size)",
    )

    # --- Embeddings ---
    embedding_model: str = Field(
        default="openai/text-embedding-3-small",
        description="Модель эмбеддингов (OpenRouter format)",
    )
    embedding_dimension: int = Field(default=1536, description="Размерность вектора")
    embedding_base_url: str | None = Field(
        default=None,
        description="Override base URL для embeddings",
    )

    # --- Database (PostgreSQL conversation storage) ---
    ingestion_db_url: str | None = Field(default=None, description="PostgreSQL URL (asyncpg)")

    # --- Problems platform ---
    platform_bootstrap_secret: str | None = Field(
        default=None,
        description="Bootstrap преподавателя (HEADER X-Platform-Bootstrap-Secret → POST /api/platform/instructors/bootstrap)",
    )
    platform_admin_username: str | None = Field(
        default=None,
        description="Логин платформенного администратора (вместе с PLATFORM_ADMIN_PASSWORD + PLATFORM_JWT_SECRET)",
    )
    platform_admin_password: str | None = Field(
        default=None,
        description="Пароль администратора из .env (plain); для продакена лучше длинная случайная строка",
    )
    platform_admin_secret: str | None = Field(
        default=None,
        description="Устарело: не используется",
    )
    platform_jwt_secret: str | None = Field(
        default=None,
        description="HS256 для JWT преподавателя, платформенного администратора и студентов (Bearer)",
    )
    platform_jwt_expire_hours: int = Field(
        default=168,
        ge=1,
        le=8760,
        description="TTL access_token преподавателя (JWT), часов",
    )
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Разрешённые origins для CORS (через запятую)",
    )
    code_judge_timeout_sec: int = Field(default=8, ge=1, le=120, description="Таймаут одного прогона код-судьи")
    platform_draft_max_retries: int = Field(default=2, ge=0, le=5)

    @model_validator(mode="after")
    def validate_chunk_params(self) -> "Config":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be < chunk_size ({self.chunk_size})"
            )
        # Гибрид задаётся одним коэффициентом rag_hybrid_alpha (см. rag/factory.py)
        return self

    # --- Properties ---

    @property
    def materials_dir(self) -> Path:
        """Директория для временных файлов при индексации."""
        materials_path = Path(__file__).resolve().parent.parent / "data" / "materials"
        materials_path.mkdir(parents=True, exist_ok=True)
        return materials_path

    @property
    def upload_history_dir(self) -> Path:
        """JSONL-журнал неудачных загрузок материалов курса (папка «История» на диске)."""
        p = Path(__file__).resolve().parent.parent / "data" / "upload_history"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def student_avatars_dir(self) -> Path:
        """Фото профилей студентов на диске (не попадают в ответах API как строка)."""
        p = Path(__file__).resolve().parent.parent / "data" / "student_avatars"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def embedding_api_key(self) -> str:
        """API key для embeddings."""
        key = self.openrouter_api_key or self.openai_api_key
        if not key:
            raise ValueError("OPENROUTER_API_KEY или OPENAI_API_KEY не задан в .env")
        return key

    @property
    def embedding_base_url_resolved(self) -> str:
        """Base URL для embeddings API."""
        if base_url := self.embedding_base_url:
            return base_url.rstrip("/")
        if self.openrouter_api_key:
            return "https://openrouter.ai/api/v1"
        return "https://api.openai.com/v1"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_upload_user_ids_list(self) -> list[int]:
        """Список разрешённых Telegram user IDs для upload."""
        raw_ids = self.allowed_upload_user_ids
        if not raw_ids.strip():
            return []
        try:
            return [int(item.strip()) for item in raw_ids.split(",") if item.strip()]
        except ValueError:
            return []


_config: Config | None = None


def get_config() -> Config:
    """Singleton конфигурации."""
    global _config
    if _config is None:
        _config = Config()
    return _config


# --- Helpers (для обратной совместимости) ---


def get_telegram_token() -> str:
    """Токен основного бота. Raises если не задан."""
    token = get_config().telegram_bot_token
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env")
    return token


def get_upload_bot_token() -> str:
    """Токен upload-бота. Raises если не задан."""
    token = get_config().upload_bot_token
    if not token:
        raise ValueError("UPLOAD_BOT_TOKEN не задан в .env")
    return token


def get_ingestion_service_url() -> str:
    """URL Ingestion Service."""
    return get_config().ingestion_service_url.rstrip("/")


def get_allowed_upload_user_ids() -> list[int]:
    """Разрешённые user IDs для upload (пусто = все)."""
    return get_config().allowed_upload_user_ids_list


def get_openrouter_api_key() -> str:
    """OpenRouter API key. Raises если не задан (пустой после strip тоже не считается)."""
    api_key = (get_config().openrouter_api_key or "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY не задан в .env")
    return api_key


def get_openrouter_model() -> str:
    """Модель OpenRouter."""
    return get_config().openrouter_model


def get_openrouter_base_url() -> str:
    """Base URL OpenRouter API."""
    return "https://openrouter.ai/api/v1"
