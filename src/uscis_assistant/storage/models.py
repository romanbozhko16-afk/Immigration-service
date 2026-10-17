"""Case database tables. Personal data is stored only as ciphertext columns.

Plain columns hold only what is not personal: random ids, timestamps, status, form edition,
event types, and schema paths such as "applicant.a_number" (the name of a question, not
the answer).
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    form: Mapped[str] = mapped_column(String(20))
    edition: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))  # "active" | "deleted"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Head of the audit hash chain: detects removal of the newest events, which a chain
    # alone cannot. Someone with full write access to the database can still rewrite both;
    # exporting the head elsewhere (production) closes that gap.
    audit_head_seq: Mapped[int] = mapped_column(Integer, default=0)
    audit_head_hash: Mapped[str] = mapped_column(String(64), default="0" * 64)


class Answer(Base):
    """Current answer per question. Its full history is in the audit log."""

    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("case_id", "path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    path: Mapped[str] = mapped_column(String(200))
    item: Mapped[str] = mapped_column(String(20))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50))  # e.g. "passport"; not personal data
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    name_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)  # file names can be personal
    content_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    """Append-only, hash-chained log of everything that happened in a case."""

    __tablename__ = "audit_events"
    __table_args__ = (UniqueConstraint("case_id", "seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_role: Mapped[str] = mapped_column(String(20))
    event_type: Mapped[str] = mapped_column(String(40))
    path: Mapped[str | None] = mapped_column(String(200))
    details_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class AuditLogIsAppendOnly(Exception):
    pass


@event.listens_for(AuditEvent, "before_update")
def _forbid_update(_mapper, _connection, _target):
    raise AuditLogIsAppendOnly("audit events cannot be modified")


@event.listens_for(AuditEvent, "before_delete")
def _forbid_delete(_mapper, _connection, _target):
    # The only removal path is CaseStore.delete_case (deletion on the person's request).
    raise AuditLogIsAppendOnly("audit events cannot be deleted one by one")
