"""
REST платформы задач: преподаватель (/api/platform) и студент (/api/public).
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from typing import Annotated, Any, Literal

from celery.exceptions import NotRegistered
from celery.result import AsyncResult
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from typing import AsyncGenerator

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import case, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from config import get_config
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.ingestion_service.celery_app import celery_app
from services.ingestion_service.db.problem_models import (
    Course as Pcourse,
    CourseGroupAccess,
    DocumentCatalog as Pdoc,
    DocumentIndexStatus,
    DraftStatus,
    Instructor as Pinst,
    PlatformAdmin,
    PlatformStudent,
    Problem,
    ProblemDraft,
    ProblemKind,
    ProblemTestCase,
    StudyGroup,
    Submission,
    course_documents,
)
from services.ingestion_service.processing.parsers import SUPPORTED_EXTENSIONS

from services.ingestion_service.problem_platform.graphs.draft_graph import CodingTestSpec, DraftItem

from services.ingestion_service.problem_platform.code_judge import run_python_tests
from services.ingestion_service.problem_platform.platform_auth import (
    decode_platform_admin_id_from_jwt,
    encode_instructor_jwt,
    encode_platform_admin_jwt,
    encode_student_jwt,
    generate_instructor_api_key,
    hash_api_key,
    hash_password,
    instructor_from_bearer,
    student_row_from_jwt,
    verify_password,
)
from services.ingestion_service.problem_platform.qdrant_naming import course_collection_from_slug
from services.ingestion_service.problem_platform.problem_qdrant import (
    delete_published_problem_from_qdrant,
    upsert_published_problem_to_qdrant,
)
from services.ingestion_service.problem_platform.upload_history import read_history_for_course
from services.ingestion_service.qdrant_client import create_qdrant_client, delete_catalog_document_chunks, ensure_collection
from services.ingestion_service.tasks import process_document

logger = logging.getLogger(__name__)

# ``sub`` в JWT при входе из .env (``PLATFORM_ADMIN_USERNAME`` / ``PLATFORM_ADMIN_PASSWORD``).
PLATFORM_ENV_ADMIN_JWT_SUB = uuid.UUID("018e0001-1111-7222-9999-000000000042")

platform_router = APIRouter(prefix="/api/platform", tags=["platform"])
public_router = APIRouter(prefix="/api/public", tags=["public"])

_slug_re = re.compile(r"^[a-z][a-z0-9_-]{2,126}$")
_username_re = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")
_STUDENT_AVATAR_MAX_BYTES = 1_200_000


def _mime_to_avatar_ext_from_sniff(mime: str) -> str | None:
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime)


def _stu_avatar_phys_path(student_id: uuid.UUID, ext_with_dot: str) -> Path:
    e = ext_with_dot if ext_with_dot.startswith(".") else f".{ext_with_dot}"
    return get_config().student_avatars_dir / f"{student_id}{e}"


def _stu_unlink_avatar_disk(student_id: uuid.UUID, ext: str | None) -> None:
    if not ext or not str(ext).strip():
        return
    p = _stu_avatar_phys_path(student_id, str(ext).strip())
    try:
        if p.is_file():
            p.unlink()
    except OSError:
        logger.warning("student avatar disk unlink failed for %s", student_id, exc_info=True)


def _sniff_image_mime_magic(data: bytes) -> str | None:
    if len(data) < 12:
        return None
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(data) >= 14 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def session_dep(request: Request) -> AsyncGenerator[AsyncSession, None]:
    factory: async_sessionmaker[AsyncSession] | None = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    async with factory() as ses:
        yield ses


SessionDep = Annotated[AsyncSession, Depends(session_dep)]
AuthScheme = HTTPBearer(auto_error=False)


async def resolve_public_student(
    session: SessionDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(AuthScheme)],
    x_student_access_key: Annotated[str | None, Header(alias="X-Student-Access-Key")] = None,
) -> PlatformStudent | None:
    """JWT студента или legacy-ключ доступа для закрытых курсов."""
    if creds and creds.credentials:
        row = await student_row_from_jwt(session, creds.credentials)
        if row is not None:
            return row
    hk = (x_student_access_key or "").strip()
    if len(hk) >= 4:
        return await session.scalar(select(PlatformStudent).where(PlatformStudent.access_key == hk))
    return None


PublicStudentDep = Annotated[PlatformStudent | None, Depends(resolve_public_student)]


async def resolve_student_jwt_only(
    session: SessionDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(AuthScheme)],
) -> PlatformStudent:
    if creds is None or not (creds.credentials or "").strip():
        raise HTTPException(status_code=401, detail="Нужен Bearer токен студента")
    row = await student_row_from_jwt(session, creds.credentials.strip())
    if row is None:
        raise HTTPException(status_code=401, detail="Неверный или просроченный токен студента")
    return row


StudentJWTDep = Annotated[PlatformStudent, Depends(resolve_student_jwt_only)]


async def resolve_platform_admin(
    session: SessionDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(AuthScheme)],
) -> None:
    if creds is None or not (creds.credentials or "").strip():
        raise HTTPException(status_code=401, detail="Войдите как администратор платформы (Bearer JWT).")
    cfg = get_config()
    secret = getattr(cfg, "platform_jwt_secret", None)
    if not secret:
        raise HTTPException(status_code=503, detail="platform_jwt_secret не задан.")
    aid = decode_platform_admin_id_from_jwt(creds.credentials.strip(), secret)
    if aid is None:
        raise HTTPException(status_code=401, detail="Неверный или просроченный токен администратора.")
    if aid == PLATFORM_ENV_ADMIN_JWT_SUB:
        eu = (getattr(cfg, "platform_admin_username", None) or "").strip()
        ep = getattr(cfg, "platform_admin_password", None)
        if ep is not None:
            ep = str(ep)
        if not eu or ep is None or ep == "":
            raise HTTPException(status_code=503, detail="В .env задайте PLATFORM_ADMIN_USERNAME и PLATFORM_ADMIN_PASSWORD.")
        return None
    adm = await session.get(PlatformAdmin, aid)
    if adm is None:
        raise HTTPException(status_code=401, detail="Неверный или просроченный токен администратора.")
    return None


PlatformAdminDep = Annotated[None, Depends(resolve_platform_admin)]


async def instructor_dep(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(AuthScheme)],
    session: SessionDep,
) -> Pinst:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    inst = await instructor_from_bearer(session, creds.credentials)
    if not inst:
        raise HTTPException(status_code=401, detail="Invalid instructor key")
    return inst


def _slug_ok(slug: str) -> bool:
    return bool(_slug_re.match(slug))


class BootstrapIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    username: str | None = None
    password: str | None = None


class CourseCreate(BaseModel):
    slug: str
    title: str = Field(min_length=1)
    subject_hint: str | None = None


class CourseOut(BaseModel):
    id: str
    slug: str
    title: str
    subject_hint: str | None
    visibility_mode: str = "public"
    chat_assistant_enabled: bool = True
    anti_cheat_mode: Literal["off", "basic", "advanced"] = "advanced"

    model_config = {"from_attributes": True}


def _normalize_anti_cheat_mode(raw: str | None) -> Literal["off", "basic", "advanced"]:
    v = (raw or "advanced").strip().lower()
    if v in ("off", "basic", "advanced"):
        return v  # type: ignore[return-value]
    return "advanced"


def _course_to_out(course: Pcourse) -> CourseOut:
    vm = getattr(course, "visibility_mode", None) or "public"
    if vm not in ("public", "groups"):
        vm = "public"
    chat_on = bool(getattr(course, "chat_assistant_enabled", True))
    return CourseOut(
        id=str(course.id),
        slug=course.slug,
        title=course.title,
        subject_hint=course.subject_hint,
        visibility_mode=vm,
        chat_assistant_enabled=chat_on,
        anti_cheat_mode=_normalize_anti_cheat_mode(getattr(course, "anti_cheat_mode", None)),
    )


def _new_student_access_key() -> str:
    return secrets.token_urlsafe(24)


_CYR_LOGIN_MAP: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "jo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "j",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "ju",
    "я": "ja",
}


def _group_title_login_stub(title: str, max_len: int = 28) -> str:
    chunks: list[str] = []
    for ch in title.strip():
        if ch.isascii() and ch.isalnum():
            chunks.append(ch.lower())
        elif ch.isspace() or ch in "-_/":
            chunks.append("_")
        else:
            cm = _CYR_LOGIN_MAP.get(ch.lower())
            if cm:
                chunks.append(cm)
    raw = "".join(chunks).strip("_")
    raw = re.sub(r"[^a-z0-9_.]+", "_", raw)
    while "__" in raw:
        raw = raw.replace("__", "_")
    raw = raw.strip("_").strip(".")
    if len(raw) < 2:
        raw = "stu"
    return raw[:max_len]


async def _allocate_student_login_group_fullname(
    session: AsyncSession,
    study_group_title: str | None,
    full_name: str,
    explicit_username: str | None,
) -> str:
    """Автологин: ``{название_группы}_{фио}`` (латиница/транслит), при коллизии — ``…_2``, ``…_3``.
    Если в теле указан ``username``, он проверяется на уникальность и сохраняется как есть."""
    if explicit_username:
        eu = explicit_username.strip().lower()
        if not _username_re.match(eu):
            raise HTTPException(status_code=400, detail="Некорректный username")
        taken = await session.scalar(
            select(func.count()).select_from(PlatformStudent).where(PlatformStudent.username == eu)
        )
        if taken and taken > 0:
            raise HTTPException(status_code=400, detail="Такой логин уже занят")
        return eu

    g_part = _group_title_login_stub((study_group_title or "nogrp").strip())[:34]
    n_part = _group_title_login_stub(full_name.strip())[:34]
    base_raw = f"{g_part}_{n_part}".strip("_").lower()
    base_raw = re.sub(r"_+", "_", base_raw).strip("_")
    if len(base_raw) < 3:
        base_raw = "student_user"

    cand0 = base_raw[:62]
    if not cand0[:1].isalpha():
        cand0 = f"s_{cand0}"[:62]
    if not _username_re.match(cand0):
        cand0 = f"stu_{_group_title_login_stub(full_name).replace('_','')[:20]}".lower()[:62]

    for i in range(1, 200):
        cand = cand0 if i == 1 else f"{cand0}_{i}"
        cand = cand[:62]
        if len(cand) < 3:
            cand = cand0[:59] + f"_{i}"
        taken = await session.scalar(
            select(func.count()).select_from(PlatformStudent).where(PlatformStudent.username == cand)
        )
        if not taken:
            return cand
    raise HTTPException(status_code=500, detail="Не удалось выбрать уникальный логин студента")


def _submission_success_ratio(score: float | None, mx: float) -> float:
    if mx <= 0:
        return 1.0 if (score or 0) >= 0 else 0.0
    return float(min(1.0, max(0.0, (score or 0.0) / mx)))


class InstructorBootstrapOut(BaseModel):
    id: str
    display_name: str
    api_key: str | None = None
    username: str | None = None
    access_token: str | None = None


class LoginIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username", mode="after")
    @classmethod
    def _username_lower(cls, v: str) -> str:
        return v.strip().lower()


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UnifiedLoginOut(BaseModel):
    """Единый ответ входа по логину/паролю: роль + токен (разные аудитории JWT)."""

    role: Literal["platform_admin", "instructor", "student"]
    access_token: str
    token_type: str = "bearer"
    student_access_key: str | None = None


class AdminCreateInstructorIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class AdminCreateInstructorOut(BaseModel):
    id: str
    display_name: str
    username: str


@platform_router.post("/admin/auth/login", response_model=LoginOut, tags=["platform-admin"])
async def platform_admin_login(body: LoginIn, session: SessionDep):
    """Вход администратора: пары из .env (``PLATFORM_ADMIN_USERNAME`` / ``PLATFORM_ADMIN_PASSWORD``) или аккаунт в ``platform_admins``."""
    cfg = get_config()
    jwt_secret = getattr(cfg, "platform_jwt_secret", None)
    if not jwt_secret:
        raise HTTPException(status_code=503, detail="platform_jwt_secret не задан.")

    hrs = int(getattr(cfg, "platform_jwt_expire_hours", 168) or 168)

    eu = (getattr(cfg, "platform_admin_username", None) or "").strip()
    ep_raw = getattr(cfg, "platform_admin_password", None)
    epstr = "" if ep_raw is None else str(ep_raw)

    bn = body.username
    if eu and epstr != "" and bn == eu.strip().lower() and body.password == epstr:
        return LoginOut(access_token=encode_platform_admin_jwt(PLATFORM_ENV_ADMIN_JWT_SUB, jwt_secret, hrs))

    adm = await session.scalar(select(PlatformAdmin).where(func.lower(PlatformAdmin.username) == bn))
    if adm is None or not getattr(adm, "password_hash", None):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    if not verify_password(body.password, adm.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    return LoginOut(access_token=encode_platform_admin_jwt(adm.id, jwt_secret, hrs))


@platform_router.post(
    "/admin/instructors",
    response_model=AdminCreateInstructorOut,
    tags=["platform-admin"],
)
async def admin_create_instructor(
    body: AdminCreateInstructorIn,
    session: SessionDep,
    _adm: PlatformAdminDep,
):
    """Создать аккаунт преподавателя через UI /admin после входа платформенного администратора."""
    cfg = get_config()
    jwt_secret_cfg = getattr(cfg, "platform_jwt_secret", None)
    if not jwt_secret_cfg:
        raise HTTPException(status_code=503, detail="PLATFORM_JWT_SECRET required for instructor login")

    un = body.username.strip().lower()
    if not _username_re.match(un):
        raise HTTPException(status_code=400, detail="Invalid username format")

    if await session.scalar(select(Pinst.id).where(Pinst.username == un)):
        raise HTTPException(status_code=409, detail="Username taken")

    plain_key = generate_instructor_api_key()
    inst = Pinst(
        display_name=body.display_name.strip(),
        username=un,
        password_hash=hash_password(body.password),
        api_key_hash=hash_api_key(plain_key),
    )
    session.add(inst)
    await session.commit()
    await session.refresh(inst)
    logger.info("admin created instructor username=%s id=%s", un, inst.id)
    return AdminCreateInstructorOut(id=str(inst.id), display_name=inst.display_name, username=un)


@platform_router.post("/auth/login", response_model=LoginOut)
async def platform_login(body: LoginIn, session: SessionDep):
    cfg = get_config()
    jwt_secret = getattr(cfg, "platform_jwt_secret", None)
    if not jwt_secret:
        raise HTTPException(status_code=503, detail="Password login unavailable (PLATFORM_JWT_SECRET)")
    un = body.username
    inst = await session.scalar(select(Pinst).where(Pinst.username == un))
    if inst is None or not inst.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, inst.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    hrs = getattr(cfg, "platform_jwt_expire_hours", 168)
    tok = encode_instructor_jwt(inst.id, jwt_secret, hrs)
    return LoginOut(access_token=tok)


@platform_router.post("/instructors/bootstrap", response_model=InstructorBootstrapOut)
async def bootstrap_instructor(
    body: BootstrapIn,
    session: SessionDep,
    secret: Annotated[str | None, Header(alias="X-Platform-Bootstrap-Secret")] = None,
):
    """Legacy bootstrap (скрипты / миграции). Новые аккаунты — POST /api/platform/admin/instructors."""
    cfg = get_config()
    expected = getattr(cfg, "platform_bootstrap_secret", None)
    if not expected or secret != expected:
        raise HTTPException(status_code=403, detail="Bootstrap disabled or wrong secret")

    has_u = bool(body.username and str(body.username).strip())
    has_p = bool(body.password and len(body.password) > 0)
    if has_u ^ has_p:
        raise HTTPException(status_code=400, detail="username and password must be supplied together")

    plain_key = generate_instructor_api_key()
    jwt_secret_cfg = getattr(cfg, "platform_jwt_secret", None)

    if has_u and has_p:
        un = body.username.strip().lower() if body.username else ""
        if not _username_re.match(un):
            raise HTTPException(status_code=400, detail="Invalid username format")
        if len(body.password) < 8:
            raise HTTPException(status_code=400, detail="Password min length 8")
        if await session.scalar(select(Pinst.id).where(Pinst.username == un)):
            raise HTTPException(status_code=409, detail="Username taken")
        if not jwt_secret_cfg:
            raise HTTPException(status_code=503, detail="PLATFORM_JWT_SECRET required for login/password onboarding")

        inst = Pinst(
            display_name=body.display_name.strip(),
            username=un,
            password_hash=hash_password(body.password),
            api_key_hash=hash_api_key(plain_key),
        )
        session.add(inst)
        await session.commit()
        await session.refresh(inst)
        hrs = getattr(cfg, "platform_jwt_expire_hours", 168)
        tok = encode_instructor_jwt(inst.id, jwt_secret_cfg, hrs)
        return InstructorBootstrapOut(
            id=str(inst.id),
            display_name=inst.display_name,
            username=un,
            access_token=tok,
        )

    inst = Pinst(display_name=body.display_name.strip(), api_key_hash=hash_api_key(plain_key))
    session.add(inst)
    await session.commit()
    await session.refresh(inst)
    return InstructorBootstrapOut(id=str(inst.id), display_name=inst.display_name, api_key=plain_key)


@platform_router.get("/courses", response_model=list[CourseOut])
async def list_my_courses(session: SessionDep, inst: Pinst = Depends(instructor_dep)):
    res = await session.execute(select(Pcourse).where(Pcourse.instructor_id == inst.id))
    rows = list(res.scalars())
    return [_course_to_out(c) for c in rows]


@platform_router.post("/courses", response_model=CourseOut)
async def create_course(
    body: CourseCreate,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    if not _slug_ok(body.slug):
        raise HTTPException(status_code=400, detail="Invalid slug")

    clash = await session.scalar(select(Pcourse.id).where(Pcourse.slug == body.slug))
    if clash:
        raise HTTPException(status_code=409, detail="Slug taken")

    col = course_collection_from_slug(body.slug)
    ensure_collection(create_qdrant_client(), collection_name=col)

    c = Pcourse(
        instructor_id=inst.id,
        slug=body.slug,
        title=body.title.strip(),
        subject_hint=(body.subject_hint or "").strip() or None,
        qdrant_collection_name=col,
    )
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return _course_to_out(c)


@platform_router.get("/courses/{course_id}", response_model=CourseOut)
async def get_my_course(
    course_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    c = await _course_owned(session, inst, course_id)
    return _course_to_out(c)


class InstructorMeOut(BaseModel):
    id: str
    display_name: str
    full_name: str | None
    username: str | None


class InstructorMePatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)


class CourseVisibilityPatch(BaseModel):
    visibility_mode: str


class CourseSettingsPatch(BaseModel):
    chat_assistant_enabled: bool | None = None
    anti_cheat_mode: Literal["off", "basic", "advanced"] | None = None


class StudyGroupCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)


class StudyGroupPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)


class StudyGroupOut(BaseModel):
    id: str
    title: str


class StudentCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    study_group_id: uuid.UUID | None = None
    username: str | None = Field(
        default=None,
        description="Редко нужно вручную; по умолчанию ``{slug_группы}_{slug_фио}``.",
    )


class StudentPatch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    study_group_id: uuid.UUID | None = None
    username: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Логин для входа студента; нужен для записей без username после ранней миграции БД.",
    )

    @field_validator("username", mode="after")
    @classmethod
    def _patch_username_lower(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.lower()


class StudentOut(BaseModel):
    id: str
    full_name: str
    username: str | None
    study_group_id: str | None
    study_group_title: str | None
    access_key: str


class StudentCreatedOut(StudentOut):
    """Разовые данные при создании студента."""

    initial_password_plain: str | None = Field(
        default=None,
        description="Показывается один раз после создания аккаунта.",
    )

    model_config = {"populate_by_name": True}


class StudentPasswordResetOut(BaseModel):
    """Одноразовый пароль после сброса (до следующего сохраните в админке)."""

    initial_password_plain: str


class GroupPolicyRowIn(BaseModel):
    study_group_id: uuid.UUID
    problems_visible: bool = True
    chat_ai_allowed: bool = True


class CoursePoliciesPut(BaseModel):
    policies: list[GroupPolicyRowIn]


class GroupPolicyRowOut(BaseModel):
    study_group_id: str
    study_group_title: str
    problems_visible: bool
    chat_ai_allowed: bool


@platform_router.get("/me", response_model=InstructorMeOut)
async def get_me(inst: Pinst = Depends(instructor_dep)):
    return InstructorMeOut(
        id=str(inst.id),
        display_name=inst.display_name,
        full_name=getattr(inst, "full_name", None),
        username=getattr(inst, "username", None),
    )


@platform_router.patch("/me", response_model=InstructorMeOut)
async def patch_me(body: InstructorMePatch, session: SessionDep, inst: Pinst = Depends(instructor_dep)):
    row = await session.get(Pinst, inst.id)
    if row is None:
        raise HTTPException(status_code=404)
    if body.display_name is not None:
        row.display_name = body.display_name.strip()
    if body.full_name is not None:
        fn = body.full_name.strip()
        row.full_name = fn or None
    await session.commit()
    await session.refresh(row)
    return InstructorMeOut(
        id=str(row.id),
        display_name=row.display_name,
        full_name=getattr(row, "full_name", None),
        username=getattr(row, "username", None),
    )


@platform_router.patch("/courses/{course_id}", response_model=CourseOut)
async def patch_course(
    course_id: uuid.UUID,
    body: CourseVisibilityPatch,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    vm = body.visibility_mode.strip().lower()
    if vm not in ("public", "groups"):
        raise HTTPException(status_code=400, detail="visibility_mode must be public or groups")
    course = await _course_owned(session, inst, course_id)
    course.visibility_mode = vm
    session.add(course)
    await session.commit()
    await session.refresh(course)
    return _course_to_out(course)


@platform_router.patch("/courses/{course_id}/settings", response_model=CourseOut)
async def patch_course_settings(
    course_id: uuid.UUID,
    body: CourseSettingsPatch,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    """Чат-ассистент и режим античита для курса."""
    if body.chat_assistant_enabled is None and body.anti_cheat_mode is None:
        raise HTTPException(status_code=400, detail="Укажите хотя бы одно поле для обновления.")
    course = await _course_owned(session, inst, course_id)
    if body.chat_assistant_enabled is not None:
        course.chat_assistant_enabled = body.chat_assistant_enabled
    if body.anti_cheat_mode is not None:
        course.anti_cheat_mode = body.anti_cheat_mode
    session.add(course)
    await session.commit()
    await session.refresh(course)
    return _course_to_out(course)


async def _list_study_groups_catalog(session: AsyncSession) -> list[StudyGroupOut]:
    res = await session.execute(select(StudyGroup).order_by(StudyGroup.title))
    return [StudyGroupOut(id=str(g.id), title=g.title) for g in res.scalars()]


@platform_router.get("/study-groups", response_model=list[StudyGroupOut])
async def list_study_groups_catalog(session: SessionDep, _inst: Pinst = Depends(instructor_dep)):
    """Список всех групп платформы (только для выбора в настройках курса — создаются администратором)."""
    return await _list_study_groups_catalog(session)


@platform_router.get("/groups", response_model=list[StudyGroupOut])
async def list_groups_catalog_alias(session: SessionDep, _inst: Pinst = Depends(instructor_dep)):
    """Тот же каталог, что ``/study-groups``, для совместимости со старыми развёртываниями."""
    return await _list_study_groups_catalog(session)


@platform_router.get("/courses/{course_id}/group-access", response_model=list[GroupPolicyRowOut])
async def get_course_policies(course_id: uuid.UUID, session: SessionDep, inst: Pinst = Depends(instructor_dep)):
    await _course_owned(session, inst, course_id)
    res = await session.execute(
        select(CourseGroupAccess, StudyGroup)
        .join(StudyGroup, StudyGroup.id == CourseGroupAccess.study_group_id)
        .where(CourseGroupAccess.course_id == course_id)
    )
    rows: list[GroupPolicyRowOut] = []
    for pol, grp in res.all():
        rows.append(
            GroupPolicyRowOut(
                study_group_id=str(pol.study_group_id),
                study_group_title=grp.title,
                problems_visible=bool(pol.problems_visible),
                chat_ai_allowed=bool(pol.chat_ai_allowed),
            )
        )
    rows.sort(key=lambda r: r.study_group_title.lower())
    return rows


@platform_router.put("/courses/{course_id}/group-access", response_model=list[GroupPolicyRowOut])
async def put_course_policies(
    course_id: uuid.UUID,
    body: CoursePoliciesPut,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    await _course_owned(session, inst, course_id)
    for row in body.policies:
        g = await session.get(StudyGroup, row.study_group_id)
        if not g:
            raise HTTPException(status_code=400, detail=f"Unknown group {row.study_group_id}")

    await session.execute(delete(CourseGroupAccess).where(CourseGroupAccess.course_id == course_id))
    for row in body.policies:
        session.add(
            CourseGroupAccess(
                course_id=course_id,
                study_group_id=row.study_group_id,
                problems_visible=row.problems_visible,
                chat_ai_allowed=row.chat_ai_allowed,
            )
        )
    await session.commit()
    return await get_course_policies(course_id, session, inst)


@platform_router.get("/analytics/dashboard")
async def instructor_dashboard(session: SessionDep, inst: Pinst = Depends(instructor_dep)):
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)

    totals = {
        "registry_students": int(await session.scalar(select(func.count()).select_from(PlatformStudent)) or 0),
        "registry_groups": int(await session.scalar(select(func.count()).select_from(StudyGroup)) or 0),
        "courses": int(
            await session.scalar(select(func.count()).select_from(Pcourse).where(Pcourse.instructor_id == inst.id)) or 0
        ),
    }

    cres = await session.execute(select(Pcourse).where(Pcourse.instructor_id == inst.id).order_by(Pcourse.title))
    courses_out: list[dict] = []
    for course in cres.scalars():
        cid = course.id
        pub_n = await session.scalar(
            select(func.count()).select_from(Problem).where(Problem.course_id == cid, Problem.published.is_(True))
        )
        sub_tot = await session.scalar(
            select(func.count()).select_from(Submission).join(Problem, Problem.id == Submission.problem_id).where(Problem.course_id == cid)
        )
        ok_sub = await session.scalar(
            select(func.count())
            .select_from(Submission)
            .join(Problem, Problem.id == Submission.problem_id)
            .where(
                Problem.course_id == cid,
                Submission.score.isnot(None),
                Problem.max_score.isnot(None),
                Submission.score >= Problem.max_score * 0.98,
            )
        )
        distinct_p = await session.scalar(
            select(func.count(func.distinct(Submission.participant_id)))
            .select_from(Submission)
            .join(Problem, Problem.id == Submission.problem_id)
            .where(Problem.course_id == cid)
        )

        popular = (
            await session.execute(
                select(Problem.title, func.count(Submission.id).label("cnt"))
                .select_from(Submission)
                .join(Problem, Submission.problem_id == Problem.id)
                .where(Problem.course_id == cid)
                .group_by(Problem.id)
                .order_by(func.count(Submission.id).desc())
                .limit(1)
            )
        ).first()
        recent = await session.scalar(
            select(func.count())
            .select_from(Submission)
            .join(Problem, Submission.problem_id == Problem.id)
            .where(
                Problem.course_id == cid,
                Submission.created_at >= cutoff,
            )
        )
        avg_score_pct: float | None = None
        avg_row = (
            await session.execute(
                select(func.avg(case((Problem.max_score > 0, 100.0 * Submission.score / Problem.max_score), else_=None)))
                .select_from(Submission)
                .join(Problem, Submission.problem_id == Problem.id)
                .where(
                    Problem.course_id == cid,
                    Submission.score.isnot(None),
                    Problem.max_score > 0,
                )
            )
        ).scalar()
        if avg_row is not None:
            avg_score_pct = round(float(avg_row), 1)

        courses_out.append(
            {
                "course_id": str(cid),
                "slug": course.slug,
                "title": course.title,
                "visibility_mode": getattr(course, "visibility_mode", None) or "public",
                "published_problems": int(pub_n or 0),
                "submissions_total": int(sub_tot or 0),
                "successful_submissions": int(ok_sub or 0),
                "distinct_submitters": int(distinct_p or 0),
                "popular_problem_title": popular[0] if popular else None,
                "submissions_week": int(recent or 0),
                "avg_attempt_score_pct": avg_score_pct,
            }
        )

    group_agg: list[dict] = []
    gres = await session.execute(select(StudyGroup).order_by(StudyGroup.title))
    groups = list(gres.scalars())
    for grp in sorted(groups, key=lambda g: g.title.lower()):
        part_keys = (
            (
                await session.execute(
                    select(PlatformStudent.access_key).where(
                        PlatformStudent.study_group_id == grp.id,
                    )
                )
            ).scalars().all()
        )
        if not part_keys:
            continue
        attempts = await session.scalar(select(func.count()).select_from(Submission).where(Submission.participant_id.in_(part_keys)))
        ok_g = await session.scalar(
            select(func.count())
            .select_from(Submission)
            .join(Problem, Submission.problem_id == Problem.id)
            .join(Pcourse, Pcourse.id == Problem.course_id)
            .where(
                Pcourse.instructor_id == inst.id,
                Submission.participant_id.in_(part_keys),
                Submission.score.isnot(None),
                Problem.max_score.isnot(None),
                Submission.score >= Problem.max_score * 0.98,
            )
        )
        group_agg.append(
            {
                "group_title": grp.title,
                "submissions_attempts": int(attempts or 0),
                "successful_submissions": int(ok_g or 0),
            }
        )

    return {"totals": totals, "courses": courses_out, "study_groups_activity": group_agg}


async def _course_owned(session: AsyncSession, inst: Pinst, course_id: uuid.UUID) -> Pcourse:
    course = await session.get(Pcourse, course_id)
    if not course or course.instructor_id != inst.id:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _persist_course_qdrant_collection(course: Pcourse) -> str:
    col = (
        course.qdrant_collection_name.strip()
        if course.qdrant_collection_name
        else course_collection_from_slug(course.slug)
    )
    ensure_collection(create_qdrant_client(), collection_name=col)
    return col


def _safe_material_filename(name: str) -> str:
    base = Path(name).name
    if not base or base in (".", ".."):
        return "file.bin"
    return base[:240]


@platform_router.post("/courses/{course_id}/upload")
async def upload_course_material(
    course_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
    file: UploadFile = File(...),
    subject: str | None = Form(None),
):
    course = await _course_owned(session, inst, course_id)
    filename = file.filename or "unknown"
    suf = Path(filename).suffix.lower()
    if suf == ".doc":
        suf = ".docx"
    if suf not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported type {suf}")

    subj = (subject or course.subject_hint or course.title).strip()

    catalog = Pdoc(
        instructor_id=inst.id,
        original_filename=filename,
        subject=subj,
    )
    session.add(catalog)
    await session.flush()
    await session.execute(insert(course_documents).values(course_id=course.id, document_id=catalog.id))

    col = (
        course.qdrant_collection_name.strip()
        if course.qdrant_collection_name
        else ""
    )
    if not col:
        col = _persist_course_qdrant_collection(course)
        course.qdrant_collection_name = col
        session.add(course)
        await session.flush()
    ensure_collection(create_qdrant_client(), collection_name=col)

    materials_dir = get_config().materials_dir
    rel = Path("catalog") / str(course.id) / f"{catalog.id.hex}_{_safe_material_filename(filename)}"
    dest = (materials_dir / rel).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await file.read())
    catalog.storage_relpath = rel.as_posix()
    session.add(catalog)

    await session.commit()

    task = process_document.delay(
        str(dest),
        subj,
        filename,
        catalog_document_id=str(catalog.id),
        collection_name=col,
        course_id=str(course.id),
        delete_file_after=False,
    )
    await session.refresh(catalog)
    # job id persisted in catalog by Celery startup
    return {"job_id": task.id, "document_catalog_id": str(catalog.id)}


class CourseMaterialOut(BaseModel):
    id: str
    original_filename: str
    subject: str
    index_status: str
    chunks_indexed: int
    last_job_id: str | None = None
    celery_error: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True}


@platform_router.get("/courses/{course_id}/documents", response_model=list[CourseMaterialOut])
async def list_course_documents(
    course_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    course = await _course_owned(session, inst, course_id)
    res = await session.execute(
        select(Pdoc)
        .join(course_documents, Pdoc.id == course_documents.c.document_id)
        .where(
            course_documents.c.course_id == course.id,
            Pdoc.index_status == DocumentIndexStatus.indexed.value,
        )
        .order_by(Pdoc.created_at.desc())
    )
    rows = list(res.scalars())
    out: list[CourseMaterialOut] = []
    for d in rows:
        ca = d.created_at.isoformat() if getattr(d, "created_at", None) else None
        out.append(
            CourseMaterialOut(
                id=str(d.id),
                original_filename=d.original_filename,
                subject=d.subject,
                index_status=d.index_status,
                chunks_indexed=int(d.chunks_indexed or 0),
                last_job_id=d.last_job_id,
                celery_error=d.celery_error,
                created_at=ca,
            )
        )
    return out


class UploadHistoryRow(BaseModel):
    ts: str
    catalog_document_id: str | None = None
    filename: str | None = None
    job_id: str | None = None
    error: str | None = None


@platform_router.get("/courses/{course_id}/documents/failed", response_model=list[CourseMaterialOut])
async def list_course_documents_failed(
    course_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    """Неуспешно проиндексированные попытки (для вкладки «История» / отладки)."""
    course = await _course_owned(session, inst, course_id)
    res = await session.execute(
        select(Pdoc)
        .join(course_documents, Pdoc.id == course_documents.c.document_id)
        .where(
            course_documents.c.course_id == course.id,
            Pdoc.index_status == DocumentIndexStatus.failed.value,
        )
        .order_by(Pdoc.created_at.desc())
    )
    rows = list(res.scalars())
    out: list[CourseMaterialOut] = []
    for d in rows:
        ca = d.created_at.isoformat() if getattr(d, "created_at", None) else None
        out.append(
            CourseMaterialOut(
                id=str(d.id),
                original_filename=d.original_filename,
                subject=d.subject,
                index_status=d.index_status,
                chunks_indexed=int(d.chunks_indexed or 0),
                last_job_id=d.last_job_id,
                celery_error=d.celery_error,
                created_at=ca,
            )
        )
    return out


@platform_router.get(
    "/courses/{course_id}/material-upload-history",
    response_model=list[UploadHistoryRow],
)
async def material_upload_disk_history(
    course_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
    limit: int = Query(100, ge=1, le=500),
):
    """Записи из папки data/upload_history (*.jsonl) по данному курсу."""
    await _course_owned(session, inst, course_id)
    cfg = get_config()
    raw = read_history_for_course(cfg.upload_history_dir, course_id, limit=limit)
    return [
        UploadHistoryRow(
            ts=str(r.get("ts") or ""),
            catalog_document_id=r.get("catalog_document_id"),
            filename=r.get("filename"),
            job_id=r.get("job_id"),
            error=r.get("error"),
        )
        for r in raw
    ]


@platform_router.get("/courses/{course_id}/documents/{document_id}/download")
async def download_course_material(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    """Скачать успешно проиндексированный сохранённый файл (Bearer преподавателя)."""
    course = await _course_owned(session, inst, course_id)
    res = await session.execute(
        select(Pdoc)
        .join(course_documents, Pdoc.id == course_documents.c.document_id)
        .where(course_documents.c.course_id == course.id, Pdoc.id == document_id)
    )
    doc = res.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.index_status != DocumentIndexStatus.indexed.value:
        raise HTTPException(status_code=404, detail="File available only after successful indexing")
    if not doc.storage_relpath:
        raise HTTPException(status_code=404, detail="Stored file reference missing")

    cfg = get_config()
    root = cfg.materials_dir.resolve()
    target = (root / Path(doc.storage_relpath)).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad storage path")

    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not on disk")

    return FileResponse(
        path=target,
        filename=doc.original_filename,
        media_type="application/octet-stream",
    )


@platform_router.delete("/courses/{course_id}/documents/{document_id}")
async def delete_course_material(
    course_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    """Удалить материал курса: связь, файл и чанки в Qdrant (если документ больше нигде не используется)."""
    course = await _course_owned(session, inst, course_id)
    res = await session.execute(
        select(Pdoc)
        .join(course_documents, Pdoc.id == course_documents.c.document_id)
        .where(course_documents.c.course_id == course.id, Pdoc.id == document_id)
    )
    doc = res.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    col = (course.qdrant_collection_name or "").strip() or course_collection_from_slug(course.slug)
    client = getattr(request.app.state, "qdrant_client", None)
    if client is not None:
        try:
            await asyncio.to_thread(
                delete_catalog_document_chunks,
                client,
                collection_name=col,
                catalog_document_id=str(document_id),
            )
        except Exception:
            logger.exception("Qdrant chunk delete failed for document %s", document_id)

    await session.execute(
        delete(course_documents).where(
            course_documents.c.course_id == course.id,
            course_documents.c.document_id == document_id,
        )
    )
    await session.flush()

    other_links = await session.scalar(
        select(func.count())
        .select_from(course_documents)
        .where(course_documents.c.document_id == document_id)
    )
    if not other_links:
        if doc.storage_relpath:
            cfg = get_config()
            root = cfg.materials_dir.resolve()
            target = (root / Path(doc.storage_relpath)).resolve()
            try:
                if target.is_file() and target.relative_to(root):
                    target.unlink()
            except (ValueError, OSError):
                logger.warning("Could not delete material file %s", target, exc_info=True)
        await session.delete(doc)

    await session.commit()
    return {"ok": True}


class InstructorProblemOut(BaseModel):
    id: str
    kind: str
    title: str
    published: bool
    ordinal: int
    max_score: float
    difficulty: int | None = None
    max_attempts: int | None = None
    score_policy: str = "best"


class InstructorProblemDetailOut(BaseModel):
    """Полные поля задачи для редактирования преподавателем."""

    id: str
    kind: str
    title: str
    statement: str
    reference_answer: str | None = None
    grading_rubric: str | None = None
    starter_code: str | None = None
    mcq_options: list[str] | None = None
    mcq_correct_index: int | None = None
    coding_tests: list[CodingTestSpec] = Field(default_factory=list)
    draft_id: str | None = None
    published: bool
    max_score: float
    difficulty: int | None = None
    max_attempts: int | None = None
    score_policy: str = "best"


class InstructorProblemPatch(BaseModel):
    difficulty: int | None = Field(None, ge=1, le=10)
    max_attempts: int | None = Field(None, ge=1, le=9999)
    score_policy: Literal["best", "last"] | None = None
    title: str | None = None
    statement: str | None = None
    reference_answer: str | None = None
    grading_rubric: str | None = None
    starter_code: str | None = None
    mcq_options: list[str] | None = None
    mcq_correct_index: int | None = Field(default=None, ge=0)
    coding_tests: list[CodingTestSpec] | None = None


async def _sync_linked_draft_from_problem(session: AsyncSession, prob: Problem) -> None:
    """Обновляет payload связанного черновика, чтобы ревью черновика не расходилось с опубликованной задачей."""
    if not prob.draft_id:
        return
    d = await session.get(ProblemDraft, prob.draft_id)
    if not d:
        return
    tests: list[dict[str, object]] = []
    for t in sorted(prob.testcases, key=lambda x: x.order_idx):
        tests.append(
            {
                "stdin_data": str(t.stdin_data or ""),
                "expected_stdout": str(t.expected_stdout or ""),
                "is_public": bool(t.is_public),
            }
        )
    payload: dict[str, object] = {
        "kind": prob.kind,
        "title": prob.title,
        "statement": prob.statement,
        "starter_code": prob.starter_code,
        "reference_answer": prob.reference_answer,
        "grading_rubric": prob.grading_rubric,
        "mcq_options": prob.mcq_options,
        "mcq_correct_index": prob.mcq_correct_index,
        "difficulty": prob.difficulty,
    }
    if prob.kind == ProblemKind.coding.value:
        payload["coding_tests"] = tests
    DraftItem.model_validate(payload)
    d.payload = payload
    d.title = prob.title


@platform_router.get("/courses/{course_id}/problems-instructor", response_model=list[InstructorProblemOut])
async def instructor_list_course_problems(
    course_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    await _course_owned(session, inst, course_id)
    res = await session.execute(
        select(Problem)
        .where(Problem.course_id == course_id)
        .order_by(Problem.ordinal, Problem.created_at)
    )
    probs = []
    for p in res.scalars():
        probs.append(
            InstructorProblemOut(
                id=str(p.id),
                kind=p.kind,
                title=p.title,
                published=bool(p.published),
                ordinal=int(p.ordinal),
                max_score=float(p.max_score),
                difficulty=getattr(p, "difficulty", None),
                max_attempts=getattr(p, "max_attempts", None),
                score_policy=(getattr(p, "score_policy", None) or "best"),
            )
        )
    return probs


@platform_router.get(
    "/courses/{course_id}/problems/{problem_id}/instructor-detail",
    response_model=InstructorProblemDetailOut,
)
async def instructor_get_problem_detail(
    course_id: uuid.UUID,
    problem_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    await _course_owned(session, inst, course_id)
    prob = await session.scalar(
        select(Problem)
        .where(Problem.id == problem_id, Problem.course_id == course_id)
        .options(selectinload(Problem.testcases))
    )
    if not prob:
        raise HTTPException(status_code=404)
    tests = [
        CodingTestSpec(
            stdin_data=str(t.stdin_data or ""),
            expected_stdout=str(t.expected_stdout or ""),
            is_public=bool(t.is_public),
        )
        for t in sorted(prob.testcases, key=lambda x: x.order_idx)
    ]
    return InstructorProblemDetailOut(
        id=str(prob.id),
        kind=prob.kind,
        title=prob.title,
        statement=prob.statement,
        reference_answer=prob.reference_answer,
        grading_rubric=prob.grading_rubric,
        starter_code=prob.starter_code,
        mcq_options=list(prob.mcq_options) if prob.mcq_options is not None else None,
        mcq_correct_index=prob.mcq_correct_index,
        coding_tests=tests,
        draft_id=str(prob.draft_id) if prob.draft_id else None,
        published=bool(prob.published),
        max_score=float(prob.max_score),
        difficulty=getattr(prob, "difficulty", None),
        max_attempts=getattr(prob, "max_attempts", None),
        score_policy=(getattr(prob, "score_policy", None) or "best"),
    )


@platform_router.patch("/courses/{course_id}/problems/{problem_id}")
async def patch_course_problem(
    course_id: uuid.UUID,
    problem_id: uuid.UUID,
    body: InstructorProblemPatch,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    await _course_owned(session, inst, course_id)
    prob = await session.scalar(
        select(Problem)
        .where(Problem.id == problem_id, Problem.course_id == course_id)
        .options(selectinload(Problem.testcases))
    )
    if not prob:
        raise HTTPException(status_code=404)

    data = body.model_dump(exclude_unset=True)
    reindex_qdrant = "title" in data or "statement" in data
    if "mcq_options" in data and data["mcq_options"] is not None:
        prob.mcq_options = list(data["mcq_options"])
    if "mcq_correct_index" in data:
        prob.mcq_correct_index = data["mcq_correct_index"]

    if "coding_tests" in data:
        if prob.kind != ProblemKind.coding.value:
            raise HTTPException(status_code=400, detail="coding_tests only for coding problems")
        ct = data["coding_tests"]
        await session.execute(delete(ProblemTestCase).where(ProblemTestCase.problem_id == prob.id))
        await session.flush()
        if ct:
            for idx, raw in enumerate(ct):
                s = CodingTestSpec.model_validate(raw)
                session.add(
                    ProblemTestCase(
                        problem_id=prob.id,
                        stdin_data=str(s.stdin_data),
                        expected_stdout=str(s.expected_stdout),
                        is_public=bool(s.is_public),
                        order_idx=idx,
                    )
                )

    if "difficulty" in data:
        prob.difficulty = data["difficulty"]
    if "max_attempts" in data:
        prob.max_attempts = data["max_attempts"]
    if "score_policy" in data:
        prob.score_policy = data["score_policy"]
    if "title" in data:
        prob.title = data["title"] or ""
    if "statement" in data:
        prob.statement = data["statement"] or ""
    if "reference_answer" in data:
        prob.reference_answer = data["reference_answer"]
    if "grading_rubric" in data:
        prob.grading_rubric = data["grading_rubric"]
    if "starter_code" in data:
        prob.starter_code = data["starter_code"]

    if prob.kind == ProblemKind.mcq.value and prob.mcq_options and prob.mcq_correct_index is not None:
        if prob.mcq_correct_index >= len(prob.mcq_options):
            raise HTTPException(status_code=400, detail="mcq_correct_index out of range")

    await session.flush()
    prob = await session.scalar(
        select(Problem)
        .where(Problem.id == problem_id)
        .options(selectinload(Problem.testcases))
    )
    assert prob is not None
    try:
        _ = DraftItem.model_validate(
            {
                "kind": prob.kind,
                "title": prob.title,
                "statement": prob.statement,
                "starter_code": prob.starter_code,
                "reference_answer": prob.reference_answer,
                "grading_rubric": prob.grading_rubric,
                "mcq_options": prob.mcq_options,
                "mcq_correct_index": prob.mcq_correct_index,
                "difficulty": prob.difficulty,
                "coding_tests": [
                    {
                        "stdin_data": t.stdin_data,
                        "expected_stdout": t.expected_stdout,
                        "is_public": t.is_public,
                    }
                    for t in sorted(prob.testcases, key=lambda x: x.order_idx)
                ]
                if prob.kind == ProblemKind.coding.value
                else None,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid problem content: {e}") from e

    await _sync_linked_draft_from_problem(session, prob)
    await session.commit()

    if reindex_qdrant and prob.published:
        course = await session.get(Pcourse, course_id)
        if course:
            try:
                await asyncio.to_thread(
                    upsert_published_problem_to_qdrant,
                    problem_id=prob.id,
                    title=prob.title,
                    statement=prob.statement,
                    course_slug=course.slug,
                )
            except Exception:
                logger.exception("Failed to re-index problem %s in Qdrant", prob.id)

    return {"ok": True}


@platform_router.delete("/courses/{course_id}/problems/{problem_id}")
async def delete_course_problem(
    course_id: uuid.UUID,
    problem_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    """Удалить задание курса вместе с попытками студентов и точкой в Qdrant."""
    course = await _course_owned(session, inst, course_id)
    prob = await session.scalar(
        select(Problem).where(Problem.id == problem_id, Problem.course_id == course_id)
    )
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found")

    if prob.published:
        client = getattr(request.app.state, "qdrant_client", None)
        if client is not None:
            try:
                await asyncio.to_thread(
                    delete_published_problem_from_qdrant,
                    problem_id=prob.id,
                    course_slug=course.slug,
                    client=client,
                )
            except Exception:
                logger.exception("Qdrant problem delete failed for %s", problem_id)

    await session.delete(prob)
    await session.commit()
    return {"ok": True}


class DraftJobIn(BaseModel):
    topic_queries: list[str] = Field(default_factory=list)
    max_items: int = Field(default=3, ge=1, le=15)


class DraftAgentJobIn(BaseModel):
    """Выбранные лекции (catalog_document_id), квоты сложности 1–10 и типов задач."""

    document_ids: list[str] = Field(min_length=1)
    difficulty_quota: dict[str, int] = Field(
        ...,
        description='Ключи "1".."10", значения — число задач на уровне; сумма 1..25',
    )
    kind_quota: dict[str, int] = Field(
        ...,
        description='Ключи coding, mcq, free_text — число задач каждого типа; сумма = сумме по сложности',
    )

    @field_validator("difficulty_quota")
    @classmethod
    def quota_bounds(cls, v: dict[str, int]) -> dict[str, int]:
        total = sum(v.values())
        if total < 1 or total > 25:
            raise ValueError("Суммарное число задач должно быть от 1 до 25.")
        for key in v:
            ik = int(key)
            if ik < 1 or ik > 10:
                raise ValueError(f"Уровень сложности должен быть 1..10, получено {key!r}")
        return v

    @field_validator("kind_quota")
    @classmethod
    def kind_bounds(cls, v: dict[str, int]) -> dict[str, int]:
        allowed = {"coding", "mcq", "free_text"}
        for key, val in v.items():
            if key not in allowed:
                raise ValueError(f"Неизвестный тип задачи: {key!r} (допустимо: coding, mcq, free_text)")
            if val < 0:
                raise ValueError(f"Квота типа {key!r} не может быть отрицательной.")
        return v

    @model_validator(mode="after")
    def quotas_match(self) -> "DraftAgentJobIn":
        d_total = sum(self.difficulty_quota.values())
        k_total = sum(self.kind_quota.get(k, 0) for k in ("coding", "mcq", "free_text"))
        if k_total < 1:
            raise ValueError("Укажите хотя бы одну задачу по типам (coding / mcq / free_text).")
        if d_total != k_total:
            raise ValueError(
                f"Сумма по сложности ({d_total}) должна совпадать с суммой по типам ({k_total}).",
            )
        return self


@platform_router.post("/courses/{course_id}/draft-jobs")
async def enqueue_drafts(
    course_id: uuid.UUID,
    body: DraftJobIn,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    course = await _course_owned(session, inst, course_id)
    from services.ingestion_service.tasks_platform import generate_course_drafts

    async_result = generate_course_drafts.delay(
        str(course.id),
        str(inst.id),
        body.topic_queries,
        body.max_items,
    )
    return {"job_id": async_result.id}


@platform_router.post("/courses/{course_id}/draft-agent-jobs")
async def enqueue_agent_drafts(
    course_id: uuid.UUID,
    body: DraftAgentJobIn,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    """Фоновая генерация черновиков по выбранным лекциям и квотам сложности (агент, structured output)."""
    course = await _course_owned(session, inst, course_id)
    from services.ingestion_service.tasks_platform import generate_agent_drafts

    try:
        async_result = generate_agent_drafts.delay(
            str(course.id),
            str(inst.id),
            body.document_ids,
            dict(body.difficulty_quota),
            dict(body.kind_quota),
        )
    except NotRegistered:
        raise HTTPException(
            status_code=503,
            detail=(
                "Celery-воркер не зарегистрировал задачу генерации (устаревший образ или воркер без актуального кода). "
                "Перезапустите сервис celery-worker; в docker-compose у него должен быть том ./:/app, как у ingestion-service."
            ),
        )
    return {"job_id": async_result.id}


@platform_router.get("/jobs/{job_id}")
async def platform_job(job_id: str):
    """Стат Celery — подходит для upload и генерации черновиков."""
    result = AsyncResult(job_id, app=celery_app)
    resp: dict[str, Any] = {"job_id": job_id, "status": result.status}
    if result.successful():
        resp["result"] = result.result
    elif result.failed():
        resp["error"] = str(result.result)
    elif result.status == "PROGRESS":
        info = result.info
        if isinstance(info, dict):
            resp["meta"] = info
    elif result.status == "STARTED":
        resp["meta"] = {"phase": "started", "label": "Воркер выполняет задачу…"}
    return resp


@platform_router.get("/courses/{course_id}/drafts")
async def list_drafts(course_id: uuid.UUID, session: SessionDep, inst: Pinst = Depends(instructor_dep)):
    await _course_owned(session, inst, course_id)
    rows = (
        (
            await session.execute(
                select(ProblemDraft).where(ProblemDraft.course_id == course_id).order_by(ProblemDraft.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    out = []
    for d in rows:
        pay = d.payload if isinstance(d.payload, dict) else {}
        diff = pay.get("difficulty")
        out.append(
            {
                "id": str(d.id),
                "status": d.status,
                "kind": d.kind,
                "title": d.title,
                "difficulty": diff if isinstance(diff, int) else None,
            }
        )
    return out


@platform_router.get("/drafts/{draft_id}")
async def get_draft_detail(
    draft_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    """Полный черновик для экрана ревью (payload как JSON задачи)."""
    d = await session.get(ProblemDraft, draft_id)
    if not d or d.instructor_id != inst.id:
        raise HTTPException(status_code=404)
    course = await session.get(Pcourse, d.course_id)
    pay = d.payload if isinstance(d.payload, dict) else {}
    return {
        "id": str(d.id),
        "course_id": str(d.course_id),
        "course_slug": course.slug if course else "",
        "course_title": course.title if course else "",
        "status": d.status,
        "kind": d.kind,
        "title": d.title,
        "payload": pay,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


class DraftPatch(BaseModel):
    title: str | None = None
    payload: dict | None = None


@platform_router.patch("/drafts/{draft_id}")
async def patch_draft(
    draft_id: uuid.UUID,
    body: DraftPatch,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    d = await session.get(ProblemDraft, draft_id)
    if not d or d.instructor_id != inst.id:
        raise HTTPException(status_code=404)
    if body.title is not None:
        d.title = body.title
    if body.payload is not None:
        merged = dict(d.payload or {})
        merged.update(body.payload)
        merged["kind"] = d.kind
        DraftItem.model_validate(merged)
        d.payload = merged
    await session.commit()
    return {"ok": True}


@platform_router.delete("/drafts/{draft_id}")
async def delete_draft(
    draft_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    """Удалить черновик (опубликованное задание при этом остаётся)."""
    d = await session.get(ProblemDraft, draft_id)
    if not d or d.instructor_id != inst.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    await session.delete(d)
    await session.commit()
    return {"ok": True}


@platform_router.post("/drafts/{draft_id}/publish")
async def publish_draft(
    draft_id: uuid.UUID,
    session: SessionDep,
    inst: Pinst = Depends(instructor_dep),
):
    d = await session.get(ProblemDraft, draft_id)
    if not d or d.instructor_id != inst.id:
        raise HTTPException(status_code=404)
    if d.status != DraftStatus.pending_review.value:
        raise HTTPException(status_code=409, detail="Draft not editable state")

    try:
        item = DraftItem.model_validate(dict(d.payload) | {"kind": d.kind})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid draft payload: {e}")

    m = await session.scalar(
        select(func.coalesce(func.max(Problem.ordinal), -1)).where(Problem.course_id == d.course_id)
    )
    next_ord = int(m if m is not None else -1) + 1

    prob = Problem(
        course_id=d.course_id,
        draft_id=d.id,
        kind=item.kind,
        title=item.title,
        statement=item.statement,
        starter_code=item.starter_code,
        reference_answer=item.reference_answer,
        grading_rubric=item.grading_rubric,
        mcq_options=item.mcq_options,
        mcq_correct_index=item.mcq_correct_index,
        ordinal=next_ord,
        difficulty=int(item.difficulty) if item.difficulty is not None else None,
        max_attempts=None,
        score_policy="best",
    )
    session.add(prob)
    await session.flush()

    if item.kind == ProblemKind.coding.value:
        tests = item.coding_tests or []
        for idx, t in enumerate(tests):
            session.add(
                ProblemTestCase(
                    problem_id=prob.id,
                    stdin_data=str(t.stdin_data),
                    expected_stdout=str(t.expected_stdout),
                    is_public=bool(t.is_public),
                    order_idx=idx,
                )
            )

    d.status = DraftStatus.published.value
    await session.commit()

    course = await session.get(Pcourse, d.course_id)
    if course:
        try:
            await asyncio.to_thread(
                upsert_published_problem_to_qdrant,
                problem_id=prob.id,
                title=prob.title,
                statement=prob.statement,
                course_slug=course.slug,
            )
        except Exception:
            logger.exception("Failed to index published problem %s in Qdrant", prob.id)

    return {"problem_id": str(prob.id)}


# ── Platform admin: группы и студенты (глобально) ─────────────────────────


async def _admin_group_rows(session: AsyncSession) -> list[StudyGroupOut]:
    res = await session.execute(select(StudyGroup).order_by(StudyGroup.title))
    return [StudyGroupOut(id=str(g.id), title=g.title) for g in res.scalars()]


async def _admin_create_group_commit(session: AsyncSession, title: str) -> StudyGroupOut:
    g = StudyGroup(title=title.strip(), instructor_id=None)
    session.add(g)
    await session.commit()
    await session.refresh(g)
    return StudyGroupOut(id=str(g.id), title=g.title)


async def _admin_patch_group_commit(
    session: AsyncSession,
    group_id: uuid.UUID,
    body: StudyGroupPatch,
) -> StudyGroupOut:
    g = await session.get(StudyGroup, group_id)
    if not g:
        raise HTTPException(status_code=404)
    if body.title is None:
        return StudyGroupOut(id=str(g.id), title=g.title)
    g.title = body.title.strip()
    await session.commit()
    await session.refresh(g)
    return StudyGroupOut(id=str(g.id), title=g.title)


async def _admin_delete_group_commit(session: AsyncSession, group_id: uuid.UUID) -> dict[str, bool]:
    g = await session.get(StudyGroup, group_id)
    if not g:
        raise HTTPException(status_code=404)
    await session.delete(g)
    await session.commit()
    return {"ok": True}


@platform_router.get("/admin/study-groups", response_model=list[StudyGroupOut], tags=["platform-admin"])
async def admin_list_study_groups(session: SessionDep, _adm: PlatformAdminDep):
    return await _admin_group_rows(session)


@platform_router.get("/admin/groups", response_model=list[StudyGroupOut], tags=["platform-admin"])
async def admin_list_groups_alias(session: SessionDep, _adm: PlatformAdminDep):
    """Тот же список, что ``/admin/study-groups`` (старое или укороченное имя)."""
    return await _admin_group_rows(session)


@platform_router.post("/admin/study-groups", response_model=StudyGroupOut, tags=["platform-admin"])
async def admin_create_study_group(body: StudyGroupCreate, session: SessionDep, _adm: PlatformAdminDep):
    return await _admin_create_group_commit(session, body.title)


@platform_router.post("/admin/groups", response_model=StudyGroupOut, tags=["platform-admin"])
async def admin_create_group_alias(body: StudyGroupCreate, session: SessionDep, _adm: PlatformAdminDep):
    return await _admin_create_group_commit(session, body.title)


@platform_router.patch("/admin/study-groups/{group_id}", response_model=StudyGroupOut, tags=["platform-admin"])
async def admin_patch_study_group(
    group_id: uuid.UUID,
    body: StudyGroupPatch,
    session: SessionDep,
    _adm: PlatformAdminDep,
):
    return await _admin_patch_group_commit(session, group_id, body)


@platform_router.patch("/admin/groups/{group_id}", response_model=StudyGroupOut, tags=["platform-admin"])
async def admin_patch_group_alias(
    group_id: uuid.UUID,
    body: StudyGroupPatch,
    session: SessionDep,
    _adm: PlatformAdminDep,
):
    return await _admin_patch_group_commit(session, group_id, body)


@platform_router.delete("/admin/study-groups/{group_id}", tags=["platform-admin"])
async def admin_delete_study_group(group_id: uuid.UUID, session: SessionDep, _adm: PlatformAdminDep):
    return await _admin_delete_group_commit(session, group_id)


@platform_router.delete("/admin/groups/{group_id}", tags=["platform-admin"])
async def admin_delete_group_alias(group_id: uuid.UUID, session: SessionDep, _adm: PlatformAdminDep):
    return await _admin_delete_group_commit(session, group_id)


async def _student_row_out(session: AsyncSession, st: PlatformStudent) -> StudentOut:
    gt = None
    gid = None
    if st.study_group_id:
        grp = await session.get(StudyGroup, st.study_group_id)
        if grp:
            gid = str(grp.id)
            gt = grp.title
    un = getattr(st, "username", None)
    un = un.strip().lower() if isinstance(un, str) and un.strip() else None
    return StudentOut(
        id=str(st.id),
        full_name=st.full_name,
        username=un,
        study_group_id=gid,
        study_group_title=gt,
        access_key=st.access_key,
    )


@platform_router.get("/admin/students", response_model=list[StudentOut], tags=["platform-admin"])
async def admin_list_students(session: SessionDep, _adm: PlatformAdminDep):
    res = await session.execute(select(PlatformStudent))
    items = [await _student_row_out(session, st) for st in res.scalars()]
    items.sort(key=lambda x: x.full_name.lower())
    return items


@platform_router.post("/admin/students", response_model=StudentCreatedOut, tags=["platform-admin"])
async def admin_create_student(body: StudentCreate, session: SessionDep, _adm: PlatformAdminDep):
    gid = None
    grp_title = None
    if body.study_group_id is not None:
        g = await session.get(StudyGroup, body.study_group_id)
        if not g:
            raise HTTPException(status_code=400, detail="Invalid study_group_id")
        gid = g.id
        grp_title = g.title

    sk = _new_student_access_key()
    # Одноразовый пароль для входа на /student/login (показывается только в ответе создания).
    plain_pw = secrets.token_urlsafe(10)
    unm = await _allocate_student_login_group_fullname(session, grp_title, body.full_name.strip(), body.username)
    st = PlatformStudent(
        instructor_id=None,
        study_group_id=gid,
        full_name=body.full_name.strip(),
        username=unm,
        password_hash=hash_password(plain_pw),
        access_key=sk,
    )
    session.add(st)
    await session.commit()
    await session.refresh(st)
    base = await _student_row_out(session, st)
    return StudentCreatedOut(**base.model_dump(), initial_password_plain=plain_pw)


@platform_router.patch("/admin/students/{student_id}", response_model=StudentOut, tags=["platform-admin"])
async def admin_patch_student(
    student_id: uuid.UUID,
    body: StudentPatch,
    session: SessionDep,
    _adm: PlatformAdminDep,
):
    st = await session.get(PlatformStudent, student_id)
    if not st:
        raise HTTPException(status_code=404)
    upd = body.model_dump(exclude_unset=True)
    if not upd:
        return await _student_row_out(session, st)
    if "full_name" in upd and upd["full_name"] is not None:
        st.full_name = str(upd["full_name"]).strip()
    if "study_group_id" in upd:
        sgid = upd["study_group_id"]
        if sgid is None:
            st.study_group_id = None
        else:
            g = await session.get(StudyGroup, sgid)
            if not g:
                raise HTTPException(status_code=400, detail="Invalid study_group_id")
            st.study_group_id = g.id
    if "username" in upd:
        raw = upd.get("username")
        if raw is None or not str(raw).strip():
            raise HTTPException(status_code=400, detail="Некорректный username")
        eu = str(raw).lower()
        if not _username_re.match(eu):
            raise HTTPException(status_code=400, detail="Некорректный username")
        other_id = await session.scalar(
            select(PlatformStudent.id).where(
                func.lower(PlatformStudent.username) == eu,
                PlatformStudent.id != st.id,
            )
        )
        if other_id is not None:
            raise HTTPException(status_code=400, detail="Такой логин уже занят")
        st.username = eu
    await session.commit()
    await session.refresh(st)
    return await _student_row_out(session, st)


@platform_router.delete("/admin/students/{student_id}", tags=["platform-admin"])
async def admin_delete_student(student_id: uuid.UUID, session: SessionDep, _adm: PlatformAdminDep):
    st = await session.get(PlatformStudent, student_id)
    if not st:
        raise HTTPException(status_code=404)
    await session.delete(st)
    await session.commit()
    return {"ok": True}


@platform_router.post("/admin/students/{student_id}/rotate-access-key", tags=["platform-admin"])
async def admin_rotate_student_key(student_id: uuid.UUID, session: SessionDep, _adm: PlatformAdminDep):
    st = await session.get(PlatformStudent, student_id)
    if not st:
        raise HTTPException(status_code=404)
    st.access_key = _new_student_access_key()
    session.add(st)
    await session.commit()
    await session.refresh(st)
    return {"access_key": st.access_key}


@platform_router.post(
    "/admin/students/{student_id}/reset-password",
    response_model=StudentPasswordResetOut,
    tags=["platform-admin"],
)
async def admin_reset_student_password(student_id: uuid.UUID, session: SessionDep, _adm: PlatformAdminDep):
    st = await session.get(PlatformStudent, student_id)
    if not st:
        raise HTTPException(status_code=404)
    unm = getattr(st, "username", None)
    if unm is None or not str(unm).strip():
        raise HTTPException(
            status_code=400,
            detail="Сначала задайте логин студента (PATCH username) — без логина войти по паролю нельзя.",
        )
    plain = secrets.token_urlsafe(10)
    st.password_hash = hash_password(plain)
    session.add(st)
    await session.commit()
    await session.refresh(st)
    return StudentPasswordResetOut(initial_password_plain=plain)


# --- Student public routes ---


@public_router.post("/session/login", response_model=UnifiedLoginOut, tags=["public"])
async def unified_public_session_login(body: LoginIn, session: SessionDep):
    """Один экран входа: по порядку проверяются администратор (.env или БД), преподаватель, студент."""
    cfg = get_config()
    secret = getattr(cfg, "platform_jwt_secret", None)
    if not secret:
        raise HTTPException(status_code=503, detail="platform_jwt_secret не задан.")
    hrs = int(getattr(cfg, "platform_jwt_expire_hours", 168) or 168)

    bn = body.username
    pw = body.password

    eu = (getattr(cfg, "platform_admin_username", None) or "").strip()
    ep_raw = getattr(cfg, "platform_admin_password", None)
    epstr = "" if ep_raw is None else str(ep_raw)
    if epstr != "" and eu and bn == eu.strip().lower() and pw == epstr:
        return UnifiedLoginOut(
            role="platform_admin",
            access_token=encode_platform_admin_jwt(PLATFORM_ENV_ADMIN_JWT_SUB, secret, hrs),
        )

    adm = await session.scalar(select(PlatformAdmin).where(func.lower(PlatformAdmin.username) == bn))
    if adm is not None and getattr(adm, "password_hash", None) and verify_password(pw, adm.password_hash):
        return UnifiedLoginOut(
            role="platform_admin",
            access_token=encode_platform_admin_jwt(adm.id, secret, hrs),
        )

    inst = await session.scalar(select(Pinst).where(Pinst.username == bn))
    if inst is not None and inst.password_hash and verify_password(pw, inst.password_hash):
        return UnifiedLoginOut(role="instructor", access_token=encode_instructor_jwt(inst.id, secret, hrs))

    st = await session.scalar(select(PlatformStudent).where(func.lower(PlatformStudent.username) == bn))
    if st is not None and getattr(st, "password_hash", None) and verify_password(pw, st.password_hash):
        un_st = getattr(st, "username", None)
        if not isinstance(un_st, str) or not un_st.strip():
            raise HTTPException(
                status_code=403,
                detail="У записи студента не задан логин для входа. Обратитесь к администратору платформы.",
            )
        return UnifiedLoginOut(
            role="student",
            access_token=encode_student_jwt(st.id, secret, hrs),
            student_access_key=st.access_key,
        )

    raise HTTPException(status_code=401, detail="Неверный логин или пароль")


class StudentSelfPatch(BaseModel):
    """Редактирование своего профиля студентом (БД только full_name)."""

    model_config = ConfigDict(str_strip_whitespace=True)
    full_name: str | None = Field(None, min_length=1, max_length=255)


class StudentMeOut(BaseModel):
    """Профиль без секретных полей — ключ отправок живёт только в браузере после входа."""

    id: str
    username: str
    full_name: str
    study_group_id: str | None
    study_group_title: str | None
    has_avatar: bool = False


async def _student_me_response(student: PlatformStudent, session: AsyncSession) -> StudentMeOut:
    await session.refresh(student)
    un = student.username or ""
    if not un.strip():
        raise HTTPException(
            status_code=403,
            detail="Для этого профиля ещё не задан логин — выпустите студента заново из админки.",
        )
    gid = gt = None
    if student.study_group_id:
        grp = await session.get(StudyGroup, student.study_group_id)
        if grp:
            gid = str(grp.id)
            gt = grp.title
    av_raw = getattr(student, "avatar_ext", None)
    has_avatar = False
    if av_raw and str(av_raw).strip():
        pth = _stu_avatar_phys_path(student.id, str(av_raw).strip())
        has_avatar = pth.is_file()
    return StudentMeOut(
        id=str(student.id),
        username=un.strip().lower(),
        full_name=student.full_name,
        study_group_id=gid,
        study_group_title=gt,
        has_avatar=has_avatar,
    )


@public_router.post("/auth/login", response_model=LoginOut)
async def student_auth_login(body: LoginIn, session: SessionDep):
    cfg = get_config()
    secret = getattr(cfg, "platform_jwt_secret", None)
    if not secret:
        raise HTTPException(status_code=500, detail="platform_jwt_secret not configured")
    uname = body.username
    st = await session.scalar(select(PlatformStudent).where(func.lower(PlatformStudent.username) == uname))
    if not st:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    ph = getattr(st, "password_hash", None)
    if not ph or not verify_password(body.password, ph):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    hrs = int(getattr(cfg, "platform_jwt_expire_hours", 168) or 168)
    return LoginOut(access_token=encode_student_jwt(st.id, secret, hrs))


@public_router.get("/me", response_model=StudentMeOut)
async def student_me(student: StudentJWTDep, session: SessionDep):
    return await _student_me_response(student, session)


@public_router.patch("/me", response_model=StudentMeOut, tags=["public"])
async def student_patch_me(body: StudentSelfPatch, student: StudentJWTDep, session: SessionDep):
    data = body.model_dump(exclude_unset=True)
    if not data:
        return await _student_me_response(student, session)
    if "full_name" in data and data["full_name"] is not None:
        student.full_name = str(data["full_name"]).strip()
        session.add(student)
        await session.commit()
    return await _student_me_response(student, session)


class StudentPasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@public_router.post("/me/password", tags=["public"])
async def student_change_password(
    body: StudentPasswordChangeIn,
    student: StudentJWTDep,
    session: SessionDep,
):
    ph = getattr(student, "password_hash", None)
    if not ph:
        raise HTTPException(status_code=400, detail="Для аккаунта не задан пароль — обратитесь к администратору.")
    if not verify_password(body.current_password, ph):
        raise HTTPException(status_code=401, detail="Неверный текущий пароль")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="Новый пароль должен отличаться от текущего.")
    student.password_hash = hash_password(body.new_password)
    session.add(student)
    await session.commit()
    return {"ok": True}


@public_router.post("/me/avatar", response_model=StudentMeOut, tags=["public"])
async def student_upload_avatar(student: StudentJWTDep, session: SessionDep, file: UploadFile = File(...)):
    await session.refresh(student)
    prev = getattr(student, "avatar_ext", None)
    raw = await file.read()
    if len(raw) > _STUDENT_AVATAR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Файл аватара больше допустимого размера (1.2 МБ).")
    mime = _sniff_image_mime_magic(raw)
    if mime is None:
        raise HTTPException(status_code=400, detail="Нужно изображение PNG, JPEG или WebP.")
    ext = _mime_to_avatar_ext_from_sniff(mime)
    if ext is None:
        raise HTTPException(status_code=400, detail="Нужно изображение PNG, JPEG или WebP.")
    _stu_unlink_avatar_disk(student.id, prev)
    dest = _stu_avatar_phys_path(student.id, ext)
    dest.write_bytes(raw)
    student.avatar_ext = ext
    session.add(student)
    await session.commit()
    return await _student_me_response(student, session)


@public_router.delete("/me/avatar", response_model=StudentMeOut, tags=["public"])
async def student_remove_avatar(student: StudentJWTDep, session: SessionDep):
    await session.refresh(student)
    prev = getattr(student, "avatar_ext", None)
    _stu_unlink_avatar_disk(student.id, prev)
    student.avatar_ext = None
    session.add(student)
    await session.commit()
    return await _student_me_response(student, session)


@public_router.get("/me/avatar")
async def student_download_avatar(student: StudentJWTDep, session: SessionDep):
    await session.refresh(student)
    av = getattr(student, "avatar_ext", None)
    if not av or not str(av).strip():
        raise HTTPException(status_code=404, detail="Аватара нет.")
    path = _stu_avatar_phys_path(student.id, str(av).strip())
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Аватара нет.")
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=mime)


def _catalog_instructor_label(instr_row: Pinst | None) -> str:
    """Подпись в каталоге курсов: предпочтительно full_name (ФИО), иначе display_name."""
    if instr_row is None:
        return ""
    fn = getattr(instr_row, "full_name", None)
    if fn and str(fn).strip():
        return str(fn).strip()
    dn = getattr(instr_row, "display_name", None)
    return str(dn).strip() if dn else ""


def _normalize_student_catalog_title(title: str) -> str:
    """Без регистра и лишних пробелов — два slug с «одним именем» попадают в один bucket."""
    return " ".join(title.strip().split()).lower()


def _strip_internal_catalog_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if not str(k).startswith("_")}


def _is_student_catalog_public_catalog_only(row: dict[str, Any]) -> bool:
    """Строка только из общего каталога (нет доступа через политику группы для этого студента)."""
    return (
        bool(row.get("via_catalog"))
        and not row.get("via_group_policy")
        and str(row.get("visibility_mode") or "").lower() == "public"
    )


def _dedupe_student_course_catalog(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Дубликаты с разными slug после смены видимости курса («публичный» + «только группы»):

    Строки с одним и тем же нормализованным названием группируются. Если среди них есть хотя бы
    одна с ``via_group_policy``, и все такие строки принадлежат **одному** преподавателю
    (по ``_instructor_id`` на групповых записях), то из корзины убираются **все**
    записи только из общего каталога («public · каталог» без групповой строки).

    Если по одному названию видны групповые курсы у **разных** преподавателей, ничего не выкидываем —
    возможны разные курсы с совпадающим именем.

    Пустые названия разводим по ключу ``slug:…``, чтобы не сливать случайные курсы без title.
    """
    by_bucket: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ttl = row.get("title") or ""
        if ttl.strip():
            key = _normalize_student_catalog_title(ttl)
        else:
            key = f"slug:{row.get('slug') or '?'}"

        by_bucket[key].append(row)

    merged: list[dict[str, Any]] = []
    for bucket in by_bucket.values():
        gated = [b for b in bucket if b.get("via_group_policy")]
        if not gated:
            merged.extend(bucket)
            continue
        gated_instr_ids = {
            str(b.get("_instructor_id") or "").strip()
            for b in gated
            if str(b.get("_instructor_id") or "").strip()
        }
        # Несколько преподов с групповым доступом к одному заголовку — не трогаем.
        if len(gated_instr_ids) > 1:
            merged.extend(bucket)
            continue
        # 0 gated препод id (аномалия) или ровно 1 препод: убираем «лишний» общий каталог с тем же названием,
        # даже если у публичной к строки указан другой instructor_id в БД (старый дубликат аккаунта курса).
        if len(gated_instr_ids) == 1:
            survivors = [b for b in bucket if not _is_student_catalog_public_catalog_only(b)]
            merged.extend(survivors if survivors else bucket)
        else:
            merged.extend(bucket)

    merged.sort(key=lambda r: (str(r.get("title") or "").lower(), str(r.get("slug") or "")))
    return [_strip_internal_catalog_row(r) for r in merged]


async def _student_course_catalog(session: AsyncSession, st: PlatformStudent) -> list[dict[str, Any]]:
    by_slug: dict[str, dict[str, Any]] = {}
    pubs = (
        (
            await session.execute(
                select(Pcourse)
                .options(selectinload(Pcourse.instructor))
                .where(func.coalesce(Pcourse.visibility_mode, "public") == "public")
                .order_by(Pcourse.title)
            )
        )
        .unique()
        .scalars()
        .all()
    )
    for c in pubs:
        instr = str(c.instructor_id)
        by_slug[c.slug] = {
            "id": str(c.id),
            "slug": c.slug,
            "title": c.title,
            "visibility_mode": "public",
            "chat_assistant_enabled": bool(getattr(c, "chat_assistant_enabled", True)),
            "via_catalog": True,
            "_instructor_id": instr,
            "instructor_name": _catalog_instructor_label(getattr(c, "instructor", None)),
        }

    if st.study_group_id:
        gated = (
            (
                await session.execute(
                    select(Pcourse)
                    .options(selectinload(Pcourse.instructor))
                    .join(CourseGroupAccess, CourseGroupAccess.course_id == Pcourse.id)
                    .where(
                        CourseGroupAccess.study_group_id == st.study_group_id,
                        CourseGroupAccess.problems_visible.is_(True),
                    )
                    .order_by(Pcourse.title)
                )
            )
            .unique()
            .scalars()
            .all()
        )
        for c in gated:
            vm = getattr(c, "visibility_mode", None) or "groups"
            if vm not in ("public", "groups"):
                vm = "groups"
            instr = str(c.instructor_id)
            by_slug[c.slug] = {
                "id": str(c.id),
                "slug": c.slug,
                "title": c.title,
                "visibility_mode": vm,
                "chat_assistant_enabled": bool(getattr(c, "chat_assistant_enabled", True)),
                "via_group_policy": True,
                "_instructor_id": instr,
                "instructor_name": _catalog_instructor_label(getattr(c, "instructor", None)),
            }
    return _dedupe_student_course_catalog(list(by_slug.values()))


@public_router.get("/my/courses")
async def student_my_courses(student: StudentJWTDep, session: SessionDep):
    await session.refresh(student)
    return {"courses": await _student_course_catalog(session, student)}


async def _student_learning_stats(session: AsyncSession, st: PlatformStudent) -> dict[str, Any]:
    pid = st.access_key
    rows = (
        (
            await session.execute(
                select(Submission, Problem, Pcourse)
                .join(Problem, Submission.problem_id == Problem.id)
                .join(Pcourse, Problem.course_id == Pcourse.id)
                .where(Submission.participant_id == pid)
                .order_by(Submission.created_at.desc())
            )
        )
        .all()
    )

    totals = {"submissions": len(rows), "courses_touched": 0}
    by_kind: dict[str, dict[str, float | int]] = defaultdict(lambda: {"attempts": 0, "success_weight": 0.0})
    courses: dict[str, dict[str, Any]] = {}

    for sub, prob, crs in rows:
        mx = float(prob.max_score or 10.0) or 10.0
        ratio = _submission_success_ratio(sub.score, mx)
        k = prob.kind or "?"
        bk = by_kind[k]
        bk["attempts"] = int(bk["attempts"]) + 1
        bk["success_weight"] = float(bk["success_weight"]) + ratio

        ck = crs.slug
        if ck not in courses:
            courses[ck] = {"slug": ck, "title": crs.title, "attempts": 0, "success_weight": 0.0}
        courses[ck]["attempts"] += 1
        courses[ck]["success_weight"] += ratio

    totals["courses_touched"] = len(courses)

    by_kind_out: list[dict[str, Any]] = []
    weak_kind = None
    weakest = 1.0
    for kind, agg in sorted(by_kind.items(), key=lambda x: x[0]):
        attempts = int(agg["attempts"])
        avg = float(agg["success_weight"]) / attempts if attempts else 0.0
        by_kind_out.append({"kind": kind, "attempts": attempts, "avg_score_ratio": round(avg, 3)})
        if attempts >= 2 and avg < weakest:
            weakest = avg
            weak_kind = kind

    hints_ru: list[str] = []
    if weak_kind == ProblemKind.coding.value:
        hints_ru.append("Частые потери баллов по заданиям с кодом — прогоняйте публичные тесты и проверяйте краевые случаи.")
    elif weak_kind == ProblemKind.mcq.value:
        hints_ru.append("Тестовые вопросы: перечитайте формулировки и ключевые определения по темам, где ошиблись.")
    elif weak_kind == ProblemKind.free_text.value:
        hints_ru.append("Развёрнутые ответы — структурируйте рассуждение и проверьте совпадение с критериями задачи.")
    if not rows:
        hints_ru.append("Отправок пока нет — откройте курс со страницы ниже и попробуйте первую задачу.")

    course_out = [
        {
            "slug": v["slug"],
            "title": v["title"],
            "attempts": v["attempts"],
            "avg_score_ratio": round(v["success_weight"] / v["attempts"], 3) if v["attempts"] else 0.0,
        }
        for v in sorted(courses.values(), key=lambda x: x["title"])
    ]

    return {
        "totals": totals,
        "by_kind": by_kind_out,
        "by_course": course_out,
        "weak_skill_kind": weak_kind,
        "hints_ru": hints_ru,
    }


@public_router.get("/my/stats")
async def student_learning_stats(student: StudentJWTDep, session: SessionDep):
    await session.refresh(student)
    return await _student_learning_stats(session, student)


@public_router.get("/my/progress")
async def student_my_progress(
    student: StudentJWTDep,
    session: SessionDep,
    limit: int = Query(80, ge=1, le=200),
):
    """История попыток и решённые задачи с условным Elo по хронологии отправок."""
    await session.refresh(student)
    pid = (student.access_key or "").strip()
    if not pid:
        raise HTTPException(status_code=503, detail="У профиля нет ключа отправок.")

    rows = (
        (
            await session.execute(
                select(Submission, Problem, Pcourse)
                .join(Problem, Submission.problem_id == Problem.id)
                .join(Pcourse, Problem.course_id == Pcourse.id)
                .where(Submission.participant_id == pid)
                .order_by(Submission.created_at.asc())
            )
        )
        .all()
    )

    elo = 1500.0
    best_by_prob: dict[uuid.UUID, float] = {}
    meta_by_prob: dict[uuid.UUID, dict[str, Any]] = {}
    solved_rows: list[dict[str, Any]] = []

    for sub, prob, crs in rows:
        if prob.id not in meta_by_prob:
            meta_by_prob[prob.id] = {
                "problem_id": str(prob.id),
                "title": prob.title,
                "course_slug": crs.slug,
                "kind": prob.kind,
                "max_score": float(prob.max_score or 10.0) or 10.0,
                "difficulty": getattr(prob, "difficulty", None),
            }
        mx = float(meta_by_prob[prob.id]["max_score"])
        sc = float(sub.score) if sub.score is not None else 0.0
        prev_best = best_by_prob.get(prob.id, -1.0)
        best_by_prob[prob.id] = max(prev_best, sc)

        ratio = sc / mx if mx else 0.0
        r_opp = _problem_rating_from_difficulty(getattr(prob, "difficulty", None))
        if ratio >= 0.99:
            oc = 1.0
        elif ratio <= 0.0:
            oc = 0.0
        else:
            oc = 0.5
        elo = _elo_update(elo, r_opp, oc)

        was_solved = prev_best >= mx * 0.99 - 1e-9
        now_solved = best_by_prob[prob.id] >= mx * 0.99 - 1e-9
        if now_solved and not was_solved:
            solved_rows.append({**meta_by_prob[prob.id], "solved_at": sub.created_at.isoformat() if sub.created_at else None, "elo_after": round(elo, 1), "best_score": best_by_prob[prob.id]})

    tail = rows[-limit:] if len(rows) > limit else rows
    attempt_out: list[dict[str, Any]] = []
    for sub, prob, crs in reversed(tail):
        mx = float(prob.max_score or 10.0) or 10.0
        sc_raw = float(sub.score) if sub.score is not None else None
        vj = sub.verdict_json if isinstance(sub.verdict_json, dict) else None
        reason = _verdict_scoring_reason(prob.kind, vj, mx, sc_raw)
        attempt_out.append(
            {
                "id": str(sub.id),
                "problem_id": str(prob.id),
                "title": prob.title,
                "course_slug": crs.slug,
                "kind": prob.kind,
                "score": sc_raw,
                "max_score": mx,
                "passed": bool(sc_raw is not None and mx > 0 and sc_raw >= mx * 0.99 - 1e-9),
                "scoring_reason": _truncate_reason(reason) if (reason or "").strip() else None,
                "created_at": sub.created_at.isoformat() if sub.created_at else None,
            }
        )

    solved_rows.sort(key=lambda x: x.get("solved_at") or "", reverse=True)
    return {"elo_rating": round(elo, 1), "attempts": attempt_out, "solved": solved_rows}


@public_router.get("/my/exam-prospect")
async def student_exam_prospect(student: StudentJWTDep, session: SessionDep):
    await session.refresh(student)
    cats = await _student_course_catalog(session, student)
    return {
        "note": "Прогноз сдачи экзамена пока не считается (заглушка). После появления модели сюда подставится оценка.",
        "courses": [
            {
                "slug": row["slug"],
                "title": row["title"],
                "exam_pass_probability": None,
                "forecast_stub": "нет данных модели",
            }
            for row in sorted(cats, key=lambda x: x["title"])
        ],
    }


async def _require_student_problem_access(
    session: AsyncSession,
    course: Pcourse,
    pst: PlatformStudent | None,
) -> PlatformStudent | None:
    """Для режима ``groups`` — JWT или ключ + политика ``course_group_access``."""
    mode = getattr(course, "visibility_mode", None) or "public"
    if mode != "groups":
        return None
    if pst is None:
        raise HTTPException(
            status_code=403,
            detail="Курс ограничен по группам: войдите через «Вход студента» или сохраните X-Student-Access-Key.",
        )

    sg = pst.study_group_id
    if sg is None:
        raise HTTPException(status_code=403, detail="Профиль без группы — обратитесь к администратору.")
    pol = await session.scalar(
        select(CourseGroupAccess).where(
            CourseGroupAccess.course_id == course.id,
            CourseGroupAccess.study_group_id == sg,
            CourseGroupAccess.problems_visible.is_(True),
        )
    )
    if pol is None:
        raise HTTPException(status_code=403, detail="Для вашей группы нет доступа к заданиям этого курса.")
    return pst


async def _submission_count(session: AsyncSession, problem_id: uuid.UUID, participant_id: str) -> int:
    n = await session.scalar(
        select(func.count()).select_from(Submission).where(
            Submission.problem_id == problem_id,
            Submission.participant_id == participant_id,
        )
    )
    return int(n or 0)


def _participant_for_course_detail(
    participant_query: str | None,
    crs: Pcourse,
    pst: PlatformStudent | None,
) -> str:
    """Идентификатор отправок: для групп — ключ из JWT; для публичного курса — query или ключ залогиненного студента."""
    crs_vm = getattr(crs, "visibility_mode", None) or "public"
    if crs_vm == "groups":
        return pst.access_key.strip() if pst and (pst.access_key or "").strip() else "anon"
    raw = (participant_query or "").strip()
    if raw and raw not in ("anon", "web-ui"):
        return raw[:128]
    if pst is not None and (pst.access_key or "").strip():
        return pst.access_key.strip()[:128]
    return raw[:128] if raw else "anon"


def _problem_rating_from_difficulty(d: int | None) -> float:
    if isinstance(d, int) and 1 <= d <= 10:
        return 700.0 + float(d) * 110.0
    return 1200.0


def _elo_expected(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def _elo_update(r_student: float, r_opp: float, outcome: float, k: float = 24.0) -> float:
    """outcome ∈ [0, 1] — фактический результат против «рейтинга задачи»."""
    return r_student + k * (outcome - _elo_expected(r_student, r_opp))


def _verdict_scoring_reason(
    kind: str,
    verdict_json: dict[str, Any] | None,
    max_score: float,
    score: float | None,
) -> str:
    """Краткое обоснование оценки для UI (без сырых agent_logs)."""
    if verdict_json:
        v = verdict_json
        if kind == ProblemKind.free_text.value:
            fb = (v.get("feedback_ru") or "").strip()
            if fb:
                return fb
        if kind == ProblemKind.coding.value:
            msg = (v.get("message") or "").strip()
            if msg:
                return msg
            ver = (v.get("verdict") or "").strip()
            if ver == "AC":
                return "Все тесты пройдены."
            if ver:
                return f"Вердикт: {ver}."
        if kind == ProblemKind.mcq.value:
            return "Верный ответ." if v.get("verdict") == "AC" else "Неверный вариант."
    if score is not None and max_score > 0:
        return f"Балл {float(score):g} из {float(max_score):g}."
    return ""


def _truncate_reason(s: str, n: int = 280) -> str:
    t = (s or "").strip()
    if len(t) <= n:
        return t
    return t[: n - 1] + "…"


def _difficulty_band(d: int | None) -> str | None:
    if d is None:
        return None
    if d <= 3:
        return "easy"
    if d <= 7:
        return "medium"
    return "hard"


@public_router.get("/courses/{slug}")
async def public_course(slug: str, session: SessionDep):
    c = await session.scalar(select(Pcourse).where(Pcourse.slug == slug))
    if not c:
        raise HTTPException(status_code=404)
    vm = getattr(c, "visibility_mode", None) or "public"
    return {
        "slug": c.slug,
        "title": c.title,
        "visibility_mode": vm,
        "requires_student_access_key": vm == "groups",
    }


@public_router.get("/courses/{slug}/problems")
async def public_problems(
    slug: str,
    session: SessionDep,
    pst: PublicStudentDep,
    participant_id: str | None = Query(None, description="Идентификатор отправок (ключ; на публичном курсе можно опустить при JWT)."),
):
    c = await session.scalar(select(Pcourse).where(Pcourse.slug == slug))
    if not c:
        raise HTTPException(status_code=404)
    await _require_student_problem_access(session, c, pst)
    res = await session.execute(
        select(Problem)
        .where(Problem.course_id == c.id, Problem.published.is_(True))
        .order_by(Problem.ordinal, Problem.created_at)
    )
    problem_rows = list(res.scalars())
    eff_pid = _participant_for_course_detail(participant_id, c, pst)
    by_pid: dict[uuid.UUID, list[tuple[float | None, dict[str, Any] | None, datetime]]] = defaultdict(list)
    if problem_rows and eff_pid and eff_pid != "anon":
        pids = [p.id for p in problem_rows]
        srows = (
            (
                await session.execute(
                    select(Submission.problem_id, Submission.score, Submission.verdict_json, Submission.created_at)
                    .where(Submission.participant_id == eff_pid, Submission.problem_id.in_(pids))
                    .order_by(Submission.created_at)
                )
            )
            .all()
        )
        for pid, sc, vj, ca in srows:
            vdict = vj if isinstance(vj, dict) else None
            by_pid[pid].append((float(sc) if sc is not None else None, vdict, ca))

    probs = []
    for p in problem_rows:
        diff = getattr(p, "difficulty", None)
        mx = float(p.max_score or 10.0) or 10.0
        pol = (getattr(p, "score_policy", None) or "best").strip().lower()
        hist = by_pid.get(p.id, [])
        scores: list[float] = []
        for sc, _, _ in hist:
            if sc is not None:
                scores.append(sc)
        attempts_used = len(hist)
        best_score = max(scores) if scores else None
        last_score = scores[-1] if scores else None
        recorded_score = last_score if pol == "last" else best_score
        max_att = getattr(p, "max_attempts", None)
        attempts_left = None if max_att is None else max(0, int(max_att) - attempts_used)
        last_reason: str | None = None
        if hist:
            last_sc, last_vj, _ = hist[-1]
            last_reason = _truncate_reason(
                _verdict_scoring_reason(p.kind, last_vj, mx, last_sc),
            ) or None
        probs.append(
            {
                "id": str(p.id),
                "kind": p.kind,
                "title": p.title,
                "max_score": mx,
                "difficulty": diff if isinstance(diff, int) else None,
                "difficulty_band": _difficulty_band(diff if isinstance(diff, int) else None),
                "score_policy": pol,
                "attempts_used": attempts_used,
                "attempts_left": attempts_left,
                "best_score": best_score,
                "last_score": last_score,
                "recorded_score": recorded_score,
                "last_scoring_reason": last_reason,
            }
        )
    return probs


@public_router.get("/problems/{problem_id}")
async def public_problem_detail(
    problem_id: uuid.UUID,
    session: SessionDep,
    pst: PublicStudentDep,
    participant_id: str | None = Query(None, description="Идентификатор отправок (ключ студента в открытом курсе)."),
):
    p = await session.get(Problem, problem_id)
    if not p or not p.published:
        raise HTTPException(status_code=404)

    crs = await session.get(Pcourse, p.course_id)
    if crs is None:
        raise HTTPException(status_code=404)
    await _require_student_problem_access(session, crs, pst)

    pub_tests = []
    if p.kind == ProblemKind.coding.value:
        trows = (
            (
                await session.execute(
                    select(ProblemTestCase)
                    .where(ProblemTestCase.problem_id == p.id, ProblemTestCase.is_public.is_(True))
                    .order_by(ProblemTestCase.order_idx)
                )
            )
            .scalars()
            .all()
        )
        for t in trows:
            pub_tests.append({"stdin": t.stdin_data, "expected_stdout": t.expected_stdout})

    eff_pid = _participant_for_course_detail(participant_id, crs, pst)
    subs = (
        (
            await session.execute(
                select(Submission.score, Submission.created_at, Submission.verdict_json)
                .where(Submission.problem_id == p.id, Submission.participant_id == eff_pid)
                .order_by(Submission.created_at)
            )
        )
        .all()
    )
    scores: list[float] = []
    for row in subs:
        s = row[0]
        if s is not None:
            try:
                scores.append(float(s))
            except (TypeError, ValueError):
                pass
    attempts_used = len(subs)
    best_score = max(scores) if scores else None
    last_score = scores[-1] if scores else None
    pol = (getattr(p, "score_policy", None) or "best").strip().lower()
    recorded_score = last_score if pol == "last" else best_score
    max_att = getattr(p, "max_attempts", None)
    attempts_left = None if max_att is None else max(0, int(max_att) - attempts_used)
    diff = getattr(p, "difficulty", None)
    mx = float(p.max_score or 10.0) or 10.0
    last_scoring_reason: str | None = None
    last_submission_at: str | None = None
    if subs:
        _ls, last_at, last_vj = subs[-1]
        last_submission_at = last_at.isoformat() if last_at else None
        vdict = last_vj if isinstance(last_vj, dict) else None
        rsn = _verdict_scoring_reason(p.kind, vdict, mx, float(_ls) if _ls is not None else None)
        last_scoring_reason = _truncate_reason(rsn) if rsn.strip() else None
    return {
        "id": str(p.id),
        "kind": p.kind,
        "title": p.title,
        "statement": p.statement,
        "starter_code": p.starter_code,
        "mcq_options": p.mcq_options,
        "max_score": p.max_score,
        "difficulty": diff if isinstance(diff, int) else None,
        "difficulty_band": _difficulty_band(diff if isinstance(diff, int) else None),
        "max_attempts": max_att,
        "score_policy": pol,
        "attempts_used": attempts_used,
        "attempts_left": attempts_left,
        "best_score": best_score,
        "last_score": last_score,
        "recorded_score": recorded_score,
        "last_scoring_reason": last_scoring_reason,
        "last_submission_at": last_submission_at,
        "examples": pub_tests if p.kind == ProblemKind.coding.value else None,
    }


class SubmitPayload(BaseModel):
    participant_id: str = Field(default="anon", max_length=128)
    source_code: str | None = None
    choice_index: int | None = None
    text: str | None = None


@public_router.post("/problems/{problem_id}/submit")
async def submit_problem(
    problem_id: uuid.UUID,
    session: SessionDep,
    body: SubmitPayload,
    pst: PublicStudentDep,
    public_only: bool = Query(
        False,
        description="Для coding: прогон только публичных тест-кейсов (без финальной оценки по скрытым)",
    ),
):
    p = await session.get(Problem, problem_id)
    if not p or not p.published:
        raise HTTPException(status_code=404)

    crs = await session.get(Pcourse, p.course_id)
    if crs is None:
        raise HTTPException(status_code=404)

    eff_pid_raw = (body.participant_id or "").strip()
    crs_vm = getattr(crs, "visibility_mode", None) or "public"
    if crs_vm == "groups":
        if pst is None:
            raise HTTPException(
                status_code=403,
                detail="Курс ограничен по группам — войдите как студент (Bearer JWT) или укажите X-Student-Access-Key.",
            )
        await _require_student_problem_access(session, crs, pst)
        expected = pst.access_key.strip()
        anonish = eff_pid_raw in ("", "anon", "web-ui")
        if not anonish and eff_pid_raw and eff_pid_raw != expected:
            raise HTTPException(
                status_code=400,
                detail="participant_id должен совпадать с ключом студента или оставаться пустым при входе по JWT.",
            )
        participant_id_eff = expected
    else:
        if eff_pid_raw.strip() in ("", "anon", "web-ui") and pst is not None and (pst.access_key or "").strip():
            participant_id_eff = pst.access_key.strip()[:128]
        else:
            participant_id_eff = (eff_pid_raw.strip() or "anon")[:128]

    pid_short = participant_id_eff[:128]
    used = await _submission_count(session, p.id, pid_short)
    max_att = getattr(p, "max_attempts", None)
    if max_att is not None and used >= int(max_att):
        raise HTTPException(status_code=429, detail="Исчерпан лимит попыток для этой задачи.")

    if p.kind == ProblemKind.coding.value:
        code = body.source_code
        if not code:
            raise HTTPException(status_code=400, detail="source_code required")
        trows = (
            (
                await session.execute(
                    select(ProblemTestCase).where(ProblemTestCase.problem_id == p.id).order_by(ProblemTestCase.order_idx)
                )
            )
            .scalars()
            .all()
        )
        tests = [
            {"stdin_data": r.stdin_data, "expected_stdout": r.expected_stdout, "is_public": r.is_public}
            for r in trows
        ]
        if public_only:
            tests = [t for t in tests if t["is_public"]]
        if not tests:
            raise HTTPException(status_code=400, detail="No tests configured for run")

        verdict, verdict_json = run_python_tests(
            code,
            tests,
            timeout_sec=float(get_config().code_judge_timeout_sec),
        )
        scored = verdict == "AC" and not public_only
        sub = Submission(
            problem_id=p.id,
            participant_id=pid_short,
            source_code=code,
            verdict_json=verdict_json | {"evaluation_mode": "public_only" if public_only else "full"},
            score=float(p.max_score if scored else 0.0),
        )
        session.add(sub)
        await session.commit()
        return verdict_json | {"stored_submission_id": str(sub.id)}

    if p.kind == ProblemKind.mcq.value:
        if body.choice_index is None:
            raise HTTPException(status_code=400, detail="choice_index required")
        opts = p.mcq_options or []
        if body.choice_index < 0 or body.choice_index >= len(opts):
            raise HTTPException(status_code=400, detail="Invalid choice")
        ok = body.choice_index == (p.mcq_correct_index or -1)
        verdict = {"verdict": "AC" if ok else "WA", "correct_index": p.mcq_correct_index, "chosen": body.choice_index}
        score = float(p.max_score if ok else 0.0)
        sub = Submission(
            problem_id=p.id,
            participant_id=pid_short,
            mcq_index=body.choice_index,
            verdict_json=verdict,
            score=score,
        )
        session.add(sub)
        await session.commit()
        return verdict | {"stored_submission_id": str(sub.id)}

    if p.kind != ProblemKind.free_text.value:
        raise HTTPException(status_code=400, detail="Unknown problem kind")
    txt = body.text or ""
    if not txt.strip():
        raise HTTPException(status_code=400, detail="text required")
    if not (p.reference_answer or "").strip():
        raise HTTPException(status_code=500, detail="Problem missing reference_answer")

    from services.ingestion_service.tasks_platform import grade_free_text_submission

    try:
        async_result = grade_free_text_submission.delay(str(p.id), pid_short, txt)
    except NotRegistered:
        raise HTTPException(
            status_code=503,
            detail="Фоновый оценщик недоступен. Обновите celery-worker и перезапустите сервис.",
        )
    return {"async": True, "job_id": async_result.id}
