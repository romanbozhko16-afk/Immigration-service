"""FastAPI application: interview, reference chat, and attorney mode.

Privacy rules for this layer:
- Request and response bodies are never logged; error responses never echo user input.
- API responses are `Cache-Control: no-store`.
- Role is taken from the token only; it is never a request field.
"""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from uscis_assistant.api.auth import InsecureConfiguration, require_roles, validate_tokens
from uscis_assistant.config import Settings, get_settings
from uscis_assistant.forms.i765.filler import FillError
from uscis_assistant.interview.engine import InterviewSession, load_active_bank
from uscis_assistant.lawyer.review import assemble_application
from uscis_assistant.lawyer.session import LawyerSession
from uscis_assistant.llm.client import AnthropicLLM, CitingLLM, LLMUnavailable, StructuredLLM
from uscis_assistant.logging_utils import configure_logging
from uscis_assistant.reference.chat import ReferenceChat
from uscis_assistant.storage.store import (
    ActorRole,
    CaseDeleted,
    CaseNotFound,
    CaseStore,
    open_case_store,
)
from uscis_assistant.validation.i765 import validate_i765

log = logging.getLogger("uscis_assistant.api")
STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "static"
CASE_ID = Annotated[str, PathParam(pattern=r"^[0-9a-f]{32}$")]
Language = Literal["ru", "uk", "en"]
MAX_MESSAGE = 2000

AnyRole = Annotated[ActorRole, Depends(require_roles(ActorRole.APPLICANT, ActorRole.LAWYER))]
ApplicantOnly = Annotated[ActorRole, Depends(require_roles(ActorRole.APPLICANT))]
LawyerOnly = Annotated[ActorRole, Depends(require_roles(ActorRole.LAWYER))]


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: Language
    message: Annotated[str, Field(max_length=MAX_MESSAGE)]


class AttorneyData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: Annotated[str, Field(max_length=200)]
    value: Annotated[str, Field(max_length=500)] | bool
    item: Annotated[str, Field(max_length=20)] = "attorney"


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["complete", "not_required"]
    note: Annotated[str, Field(max_length=MAX_MESSAGE)] = ""


def _headers(response: Response, path: str) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'"
    )
    if path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"


def create_app(
    settings: Settings,
    store: CaseStore,
    *,
    structured_llm: StructuredLLM | None = None,
    citing_llm: CitingLLM | None = None,
    today: Callable[[], date] = lambda: datetime.now(UTC).date(),
) -> FastAPI:
    tokens = validate_tokens(settings)  # refuses to start with missing or weak tokens
    app = FastAPI(title="USCIS Form Assistant", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.tokens = tokens
    bank = load_active_bank()
    reference = ReferenceChat(structured_llm, citing_llm)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        _headers(response, request.url.path)
        return response

    @app.exception_handler(CaseNotFound)
    async def _not_found(_: Request, __: CaseNotFound):
        return JSONResponse({"detail": "case not found"}, status_code=404)

    @app.exception_handler(CaseDeleted)
    async def _gone(_: Request, __: CaseDeleted):
        return JSONResponse({"detail": "case was deleted"}, status_code=410)

    @app.exception_handler(FillError)
    async def _cannot_fill(_: Request, exc: FillError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def _bad_value(_: Request, __: ValueError):
        return JSONResponse({"detail": "invalid value"}, status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        # Log only the exception type: messages may contain user data.
        log.error("unhandled error: %s", type(exc).__name__)
        return JSONResponse({"detail": "internal error"}, status_code=500)

    def interview(case_id: str, language: Language, role: ActorRole) -> InterviewSession:
        return InterviewSession(store, case_id, language, bank, actor=role, llm=structured_llm)

    # --- public ----------------------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/me")
    def me(role: AnyRole) -> dict[str, str]:
        return {"role": role.value}

    # --- cases and interview ---------------------------------------------------------------

    @app.post("/api/cases", status_code=201)
    def create_case(role: AnyRole) -> dict[str, str]:
        return {"case_id": store.create_case(role)}

    @app.get("/api/cases/{case_id}/interview")
    def interview_prompt(
        case_id: CASE_ID,
        language: Language,
        role: AnyRole,
    ) -> dict[str, Any]:
        session = interview(case_id, language, role)
        return {"prompt": session.prompt(), "done": session.current() is None}

    @app.post("/api/cases/{case_id}/interview")
    def interview_submit(
        case_id: CASE_ID,
        body: Message,
        role: ApplicantOnly,
    ) -> dict[str, Any]:
        session = interview(case_id, body.language, role)
        result = session.submit(body.message)
        return {
            "accepted": result.accepted,
            "message": result.message,
            "next_prompt": session.prompt(),
            "done": session.current() is None,
        }

    @app.get("/api/cases/{case_id}/flags")
    def flags(case_id: CASE_ID, role: AnyRole) -> dict[str, Any]:
        built = assemble_application(store, case_id, bank)
        found = validate_i765(built.application, today()) if built.application else []
        return {
            "application_built": built.application is not None,
            "awaiting_translation": built.pending_translation,
            "flags": [
                {
                    "code": f.code.value,
                    "severity": f.severity.value,
                    "item": f.item,
                    "message": f.message,
                    "source": f.source,
                }
                for f in found
            ],
        }

    @app.delete("/api/cases/{case_id}", status_code=204)
    def delete_case(case_id: CASE_ID, role: AnyRole) -> Response:
        store.delete_case(case_id, role)
        return Response(status_code=204)

    # --- reference chat --------------------------------------------------------------------

    @app.post("/api/chat")
    def chat(body: Message, role: AnyRole) -> dict[str, Any]:
        answer = reference.ask(body.message, body.language)
        return {
            "status": answer.status.value,
            "message": answer.message,
            "quotes": [{"text": q.text, "page": q.page} for q in answer.quotes],
        }

    # --- attorney mode ---------------------------------------------------------------------

    def lawyer(case_id: str) -> LawyerSession:
        return LawyerSession(store, case_id, ActorRole.LAWYER, bank)

    @app.get("/api/lawyer/cases")
    def lawyer_cases(role: LawyerOnly) -> list[dict[str, str]]:
        return [
            {
                "case_id": c.id,
                "status": c.status,
                "form": c.form,
                "edition": c.edition,
                "created_at": c.created_at.isoformat(),
            }
            for c in store.list_cases()
        ]

    @app.get("/api/lawyer/cases/{case_id}/review")
    def lawyer_review(case_id: CASE_ID, role: LawyerOnly) -> dict[str, str]:
        session = lawyer(case_id)
        return {"summary": session.summary(today()), "audit_log": session.audit_log(today())}

    @app.post("/api/lawyer/cases/{case_id}/attorney-data", status_code=204)
    def lawyer_data(case_id: CASE_ID, body: AttorneyData, role: LawyerOnly) -> Response:
        lawyer(case_id).enter_attorney_data(body.path, body.value, body.item)
        return Response(status_code=204)

    @app.post("/api/lawyer/cases/{case_id}/decision", status_code=204)
    def lawyer_decision(case_id: CASE_ID, body: Decision, role: LawyerOnly) -> Response:
        lawyer(case_id).record_decision(body.decision, body.note)
        return Response(status_code=204)

    @app.post("/api/lawyer/cases/{case_id}/fill")
    def lawyer_fill(case_id: CASE_ID, role: LawyerOnly) -> dict[str, Any]:
        doc_id, report = lawyer(case_id).fill_pdf()
        return {
            "document_id": doc_id,
            "filled_fields": report.filled_fields,
            "skipped": len(report.skipped),
            "moved_to_part_6": report.moved_to_part_6,
            "not_placed": report.not_placed,
        }

    @app.get("/api/lawyer/cases/{case_id}/documents/{doc_id}")
    def lawyer_document(
        case_id: CASE_ID,
        doc_id: Annotated[str, PathParam(pattern=r"^[0-9a-f]{32}$")],
        role: LawyerOnly,
    ) -> Response:
        try:
            document = store.document(case_id, doc_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="document not found") from None
        return Response(
            content=document.data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
        )

    # --- web page --------------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def app_factory() -> FastAPI:
    """For `uvicorn --factory uscis_assistant.api.app:app_factory`."""
    configure_logging()
    settings = get_settings()
    try:
        llm = AnthropicLLM(settings)
    except LLMUnavailable:
        llm = None
        log.warning("no ANTHROPIC_API_KEY: the model features run in their safe fallback mode")
    return create_app(settings, open_case_store(settings), structured_llm=llm, citing_llm=llm)


__all__ = ["InsecureConfiguration", "app_factory", "create_app"]
