"""Models for BSTU-AI problems platform (instructors, courses, drafts, grading)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Table, Text, Column, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.ingestion_service.db.models import Base


def _utcnow() -> datetime:
    """Наивный UTC под TIMESTAMP WITHOUT TIME ZONE (asyncpg не шлёт aware в такие колонки)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


JSONDict = dict[str, Any]


class DocumentIndexStatus(str, Enum):
    pending = "pending"
    indexed = "indexed"
    failed = "failed"


class DraftStatus(str, Enum):
    pending_review = "pending_review"
    published = "published"
    discarded = "discarded"


class ProblemKind(str, Enum):
    coding = "coding"
    mcq = "mcq"
    free_text = "free_text"


course_documents = Table(
    "course_documents",
    Base.metadata,
    Column("course_id", ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("document_id", ForeignKey("documents_catalog.id", ondelete="CASCADE"), primary_key=True),
)


class PlatformAdmin(Base):
    """Глобальный администратор платформы (группы, студенты, создание преподавателей). Отдельно от аккаунта преподавателя."""

    __tablename__ = "platform_admins"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Instructor(Base):
    __tablename__ = "instructors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    courses: Mapped[list["Course"]] = relationship(back_populates="instructor")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    instructor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instructors.id", ondelete="CASCADE"),
        index=True,
    )
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    subject_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qdrant_collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    visibility_mode: Mapped[str] = mapped_column(String(24), default="public")
    chat_assistant_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    anti_cheat_mode: Mapped[str] = mapped_column(String(16), default="advanced")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    instructor: Mapped["Instructor"] = relationship(back_populates="courses")
    documents: Mapped[list["DocumentCatalog"]] = relationship(
        secondary=course_documents,
        back_populates="courses",
    )
    group_access_policies: Mapped[list["CourseGroupAccess"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
    )


class StudyGroup(Base):
    """Учебная группа (поток) — заводит администратор."""

    __tablename__ = "study_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    instructor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instructors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    students: Mapped[list["PlatformStudent"]] = relationship(back_populates="study_group")
    policies: Mapped[list["CourseGroupAccess"]] = relationship(back_populates="study_group")


class PlatformStudent(Base):
    """Студент платформы: ключ access_key (= participant_id), группа задаётся админом."""

    __tablename__ = "platform_students"
    __table_args__ = (UniqueConstraint("access_key", name="uq_platform_student_access_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    instructor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("instructors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    study_group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("study_groups.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    full_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_key: Mapped[str] = mapped_column(String(96), index=True)
    avatar_ext: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    study_group: Mapped["StudyGroup | None"] = relationship(back_populates="students")


class CourseGroupAccess(Base):
    """Разрешение для группы на курс: задания и (на будущее) чат по материалам."""

    __tablename__ = "course_group_access"

    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    study_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("study_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    problems_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    chat_ai_allowed: Mapped[bool] = mapped_column(Boolean, default=True)

    course: Mapped["Course"] = relationship(back_populates="group_access_policies")
    study_group: Mapped["StudyGroup"] = relationship(back_populates="policies")


class DocumentCatalog(Base):
    """Indexed source tied to instructor; id is propagated to Qdrant as catalog_document_id."""

    __tablename__ = "documents_catalog"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    instructor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instructors.id", ondelete="CASCADE"),
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(512))
    subject: Mapped[str] = mapped_column(String(255))
    storage_relpath: Mapped[str | None] = mapped_column(String(512), nullable=True)
    index_status: Mapped[str] = mapped_column(String(32), default=DocumentIndexStatus.pending.value)
    chunks_indexed: Mapped[int] = mapped_column(default=0)
    last_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    celery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    courses: Mapped[list["Course"]] = relationship(
        secondary=course_documents,
        back_populates="documents",
    )


class ProblemDraft(Base):
    __tablename__ = "problem_drafts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        index=True,
    )
    instructor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("instructors.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(String(32), default=DraftStatus.pending_review.value)
    kind: Mapped[str] = mapped_column(String(24), default=ProblemKind.free_text.value)
    title: Mapped[str] = mapped_column(String(512), default="")
    payload: Mapped[JSONDict] = mapped_column(JSONB, default=dict)
    provenance: Mapped[JSONDict | None] = mapped_column(JSONB, nullable=True)
    celery_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Problem(Base):
    __tablename__ = "platform_problems"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        index=True,
    )
    draft_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("problem_drafts.id", ondelete="SET NULL"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(512))
    statement: Mapped[str] = mapped_column(Text)
    starter_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    grading_rubric: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_score: Mapped[float] = mapped_column(Float, default=10.0)
    mcq_options: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    mcq_correct_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_policy: Mapped[str] = mapped_column(String(16), default="best")
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    testcases: Mapped[list["ProblemTestCase"]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
        order_by="ProblemTestCase.order_idx",
    )


class ProblemTestCase(Base):
    __tablename__ = "platform_problem_testcases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_problems.id", ondelete="CASCADE"),
        index=True,
    )
    stdin_data: Mapped[str] = mapped_column(Text, default="")
    expected_stdout: Mapped[str] = mapped_column(Text, default="")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    order_idx: Mapped[int] = mapped_column(Integer, default=0)

    problem: Mapped["Problem"] = relationship(back_populates="testcases")


class Submission(Base):
    __tablename__ = "platform_submissions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_problems.id", ondelete="CASCADE"),
        index=True,
    )
    participant_id: Mapped[str] = mapped_column(String(128), index=True, default="anon")
    source_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    mcq_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_text_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict_json: Mapped[JSONDict | None] = mapped_column(JSONB, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
