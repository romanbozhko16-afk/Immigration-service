"""Case store: the only code that reads or writes case data.

- Every answer keeps the user's original text, its language, and the English value for the
  form, with how the English value was produced.
- Every change is appended to a hash-chained audit log with a UTC timestamp.
- Deleting a case destroys its key first (so any copy of the ciphertext becomes unreadable),
  then removes its rows, leaving a tombstone event without personal data.
- Nothing here logs case content.
"""

import hashlib
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from uscis_assistant.config import Settings
from uscis_assistant.storage import crypto
from uscis_assistant.storage.db import make_engine
from uscis_assistant.storage.keystore import KeyStore
from uscis_assistant.storage.models import Answer, AuditEvent, Base, Case, Document

GENESIS_HASH = "0" * 64


class ActorRole(StrEnum):
    APPLICANT = "applicant"
    LAWYER = "lawyer"
    SYSTEM = "system"


class EventType(StrEnum):
    CASE_CREATED = "case_created"
    ANSWER_RECORDED = "answer_recorded"
    ANSWER_CHANGED = "answer_changed"
    DOCUMENT_ADDED = "document_added"
    DOCUMENT_DELETED = "document_deleted"
    CASE_DELETED = "case_deleted"


class CaseNotFound(Exception):
    pass


class CaseDeleted(Exception):
    pass


class AnswerRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    item: str
    original: str | None  # what the user typed, in their language
    original_language: str | None  # "ru" | "uk" | "en"
    english: Any  # JSON value that goes onto the form
    # How `english` was produced: "same" (already English or not text), "user" (typed by
    # the user), "machine" (translated by the model; shown to the user and lawyer to check)
    translation_method: Literal["same", "user", "machine"]
    updated_at: datetime


class AuditEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    occurred_at: datetime
    actor_role: ActorRole
    event_type: EventType
    path: str | None
    details: dict[str, Any] | None


class StoredDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    filename: str
    content_type: str
    data: bytes


def _event_hash(row: AuditEvent) -> str:
    payload = json.dumps(
        [
            row.case_id,
            row.seq,
            _as_utc(row.occurred_at).isoformat(),
            row.actor_role,
            row.event_type,
            row.path,
            row.details_ciphertext.hex() if row.details_ciphertext else None,
            row.prev_hash,
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _as_utc(moment: datetime) -> datetime:
    # SQLite returns naive datetimes; they were written as UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


class CaseStore:
    def __init__(
        self,
        engine: Engine,
        keystore: KeyStore,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._engine = engine
        self._keys = keystore
        self._clock = clock
        Base.metadata.create_all(engine)

    # --- helpers -------------------------------------------------------------------------

    def _active_case(self, session: Session, case_id: str) -> Case:
        # FOR UPDATE serializes writers per case on Postgres; SQLite serializes all writers.
        case = session.scalar(select(Case).where(Case.id == case_id).with_for_update())
        if case is None:
            raise CaseNotFound(case_id)
        if case.status == "deleted":
            raise CaseDeleted(case_id)
        return case

    def _key_for_active_case(self, case_id: str) -> bytes:
        with Session(self._engine) as session:
            self._active_case(session, case_id)
        return self._keys.get_case_key(case_id)

    def _encrypt_json(self, key: bytes, value: object, context: str) -> bytes:
        return crypto.encrypt(key, json.dumps(value, ensure_ascii=False).encode(), context)

    def _decrypt_json(self, key: bytes, blob: bytes, context: str) -> Any:
        return json.loads(crypto.decrypt(key, blob, context))

    def _append_event(
        self,
        session: Session,
        key: bytes | None,
        case_id: str,
        actor: ActorRole,
        event_type: EventType,
        path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        last = session.scalar(
            select(AuditEvent)
            .where(AuditEvent.case_id == case_id)
            .order_by(AuditEvent.seq.desc())
            .limit(1)
        )
        seq = last.seq + 1 if last else 1
        row = AuditEvent(
            case_id=case_id,
            seq=seq,
            occurred_at=self._clock(),
            actor_role=actor.value,
            event_type=event_type.value,
            path=path,
            details_ciphertext=(
                self._encrypt_json(key, details, f"case:{case_id}:audit:{seq}")
                if details is not None and key is not None
                else None
            ),
            prev_hash=last.hash if last else GENESIS_HASH,
            hash="",
        )
        row.hash = _event_hash(row)
        session.add(row)
        case = session.get(Case, case_id)
        case.audit_head_seq, case.audit_head_hash = seq, row.hash

    # --- cases -----------------------------------------------------------------------------

    def create_case(self, actor: ActorRole, form: str = "I-765", edition: str = "08/21/25") -> str:
        case_id = uuid.uuid4().hex
        key = self._keys.create_case_key(case_id)
        with Session(self._engine) as session, session.begin():
            session.add(
                Case(
                    id=case_id,
                    form=form,
                    edition=edition,
                    status="active",
                    created_at=self._clock(),
                    deleted_at=None,
                )
            )
            session.flush()
            self._append_event(session, key, case_id, actor, EventType.CASE_CREATED)
        return case_id

    def delete_case(self, case_id: str, actor: ActorRole) -> None:
        """Delete everything about a case at the person's request. Irreversible."""
        with Session(self._engine) as session:
            self._active_case(session, case_id)
        # 1. Destroy the key first: from now on every copy of this case's ciphertext,
        #    including copies in database backups, is unreadable.
        self._keys.destroy_case_key(case_id)
        # 2. Remove the rows and leave a tombstone that holds no personal data.
        with Session(self._engine) as session, session.begin():
            case = self._active_case(session, case_id)
            for table in (Answer, Document, AuditEvent):
                session.execute(delete(table).where(table.case_id == case_id))
            case.status = "deleted"
            case.deleted_at = self._clock()
            self._append_event(session, None, case_id, actor, EventType.CASE_DELETED)

    def case_status(self, case_id: str) -> str:
        with Session(self._engine) as session:
            case = session.get(Case, case_id)
        if case is None:
            raise CaseNotFound(case_id)
        return case.status

    # --- answers ---------------------------------------------------------------------------

    def record_answer(
        self,
        case_id: str,
        *,
        path: str,
        item: str,
        original: str | None,
        original_language: str | None,
        english: Any,
        translation_method: Literal["same", "user", "machine"],
        actor: ActorRole,
    ) -> None:
        key = self._key_for_active_case(case_id)
        value = {
            "original": original,
            "original_language": original_language,
            "english": english,
            "translation_method": translation_method,
        }
        with Session(self._engine) as session, session.begin():
            self._active_case(session, case_id)
            now = self._clock()
            ciphertext = self._encrypt_json(key, value, f"case:{case_id}:answer:{path}")
            existing = session.scalar(
                select(Answer).where(Answer.case_id == case_id, Answer.path == path)
            )
            if existing is None:
                session.add(
                    Answer(
                        case_id=case_id,
                        path=path,
                        item=item,
                        ciphertext=ciphertext,
                        updated_at=now,
                    )
                )
                event_type = EventType.ANSWER_RECORDED
            else:
                existing.ciphertext, existing.item, existing.updated_at = ciphertext, item, now
                event_type = EventType.ANSWER_CHANGED
            self._append_event(
                session, key, case_id, actor, event_type, path, {"item": item, **value}
            )

    def answers(self, case_id: str) -> dict[str, AnswerRecord]:
        with Session(self._engine) as session:
            self._active_case(session, case_id)
            rows = session.scalars(select(Answer).where(Answer.case_id == case_id)).all()
        key = self._keys.get_case_key(case_id)
        result = {}
        for row in rows:
            value = self._decrypt_json(key, row.ciphertext, f"case:{case_id}:answer:{row.path}")
            result[row.path] = AnswerRecord(
                path=row.path, item=row.item, updated_at=_as_utc(row.updated_at), **value
            )
        return result

    # --- documents -------------------------------------------------------------------------

    def add_document(
        self,
        case_id: str,
        *,
        kind: str,
        filename: str,
        content_type: str,
        data: bytes,
        actor: ActorRole,
    ) -> str:
        key = self._key_for_active_case(case_id)
        doc_id = uuid.uuid4().hex
        context = f"case:{case_id}:document:{doc_id}"
        with Session(self._engine) as session, session.begin():
            self._active_case(session, case_id)
            session.add(
                Document(
                    id=doc_id,
                    case_id=case_id,
                    kind=kind,
                    content_type=content_type,
                    size=len(data),
                    name_ciphertext=crypto.encrypt(key, filename.encode(), f"{context}:name"),
                    content_ciphertext=crypto.encrypt(key, data, f"{context}:content"),
                    created_at=self._clock(),
                )
            )
            self._append_event(
                session,
                key,
                case_id,
                actor,
                EventType.DOCUMENT_ADDED,
                details={"document_id": doc_id, "kind": kind, "filename": filename},
            )
        return doc_id

    def document(self, case_id: str, doc_id: str) -> StoredDocument:
        with Session(self._engine) as session:
            self._active_case(session, case_id)
            row = session.scalar(
                select(Document).where(Document.case_id == case_id, Document.id == doc_id)
            )
        if row is None:
            raise KeyError(doc_id)
        key = self._keys.get_case_key(case_id)
        context = f"case:{case_id}:document:{doc_id}"
        return StoredDocument(
            id=row.id,
            kind=row.kind,
            content_type=row.content_type,
            filename=crypto.decrypt(key, row.name_ciphertext, f"{context}:name").decode(),
            data=crypto.decrypt(key, row.content_ciphertext, f"{context}:content"),
        )

    def delete_document(self, case_id: str, doc_id: str, actor: ActorRole) -> None:
        key = self._key_for_active_case(case_id)
        with Session(self._engine) as session, session.begin():
            self._active_case(session, case_id)
            removed = session.execute(
                delete(Document).where(Document.case_id == case_id, Document.id == doc_id)
            )
            if removed.rowcount == 0:
                raise KeyError(doc_id)
            self._append_event(
                session,
                key,
                case_id,
                actor,
                EventType.DOCUMENT_DELETED,
                details={"document_id": doc_id},
            )

    # --- audit log -------------------------------------------------------------------------

    def audit_log(self, case_id: str) -> list[AuditEntry]:
        with Session(self._engine) as session:
            case = session.get(Case, case_id)
            if case is None:
                raise CaseNotFound(case_id)
            rows = session.scalars(
                select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.seq)
            ).all()
        key = None if case.status == "deleted" else self._keys.get_case_key(case_id)
        return [
            AuditEntry(
                seq=row.seq,
                occurred_at=_as_utc(row.occurred_at),
                actor_role=ActorRole(row.actor_role),
                event_type=EventType(row.event_type),
                path=row.path,
                details=(
                    self._decrypt_json(
                        key, row.details_ciphertext, f"case:{case_id}:audit:{row.seq}"
                    )
                    if row.details_ciphertext is not None and key is not None
                    else None
                ),
            )
            for row in rows
        ]

    def verify_audit_log(self, case_id: str) -> bool:
        """True when no audit event was altered, removed, or reordered."""
        with Session(self._engine) as session:
            case = session.get(Case, case_id)
            if case is None:
                raise CaseNotFound(case_id)
            rows = session.scalars(
                select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.seq)
            ).all()
        prev = GENESIS_HASH
        for expected_seq, row in enumerate(rows, start=1):
            if row.seq != expected_seq or row.prev_hash != prev or row.hash != _event_hash(row):
                return False
            prev = row.hash
        return (len(rows), prev) == (case.audit_head_seq, case.audit_head_hash)


class MasterKeyMissing(Exception):
    pass


def open_case_store(settings: Settings) -> CaseStore:
    if settings.master_key is None:
        raise MasterKeyMissing("MASTER_KEY is not set; see .env.example")
    master_key = crypto.decode_key(settings.master_key.get_secret_value())
    keystore = KeyStore(make_engine(settings.keystore_url), master_key)
    return CaseStore(make_engine(settings.database_url), keystore)
