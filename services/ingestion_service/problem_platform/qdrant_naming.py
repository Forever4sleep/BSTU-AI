"""Именование коллекций Qdrant для курсов платформы."""


def course_collection_from_slug(course_slug: str) -> str:
    """Стандартное имя коллекции Qdrant по slug курса (уникально при уникальном slug)."""
    cleaned = "".join(ch if str(ch).isalnum() else "_" for ch in course_slug.strip().lower())
    cleaned = "_".join(p for p in cleaned.split("_") if p) or "course"
    raw = "bstu_course_" + cleaned
    return raw[:248]


def course_problems_collection_from_slug(course_slug: str) -> str:
    """Коллекция Qdrant с эмбеддингами опубликованных задач курса (для anti-cheat в RAG)."""
    return f"{course_collection_from_slug(course_slug)}_problems"[:248]
