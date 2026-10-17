"""Per-case data keys, kept apart from case data.

Keys live in their own database (KEYSTORE_URL), not next to the data they protect. That
separation is what makes deletion by key destruction meaningful: a backup of the case
database alone cannot be decrypted once the key is destroyed. In production this class is
the place to plug in a managed KMS with its own retention policy.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Engine, LargeBinary, String, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from uscis_assistant.storage import crypto


class KeyBase(DeclarativeBase):
    pass


class CaseKey(KeyBase):
    __tablename__ = "case_keys"

    case_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    wrapped_key: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CaseKeyDestroyed(Exception):
    """The case key no longer exists: the case was deleted."""


class KeyStore:
    def __init__(self, engine: Engine, master_key: bytes):
        self._engine = engine
        self._master_key = master_key
        KeyBase.metadata.create_all(engine)

    def _context(self, case_id: str) -> str:
        return f"case-key:{case_id}"

    def create_case_key(self, case_id: str) -> bytes:
        key = crypto.generate_key()
        wrapped = crypto.encrypt(self._master_key, key, self._context(case_id))
        with Session(self._engine) as session, session.begin():
            session.add(CaseKey(case_id=case_id, wrapped_key=wrapped, created_at=datetime.now(UTC)))
        return key

    def get_case_key(self, case_id: str) -> bytes:
        with Session(self._engine) as session:
            row = session.scalar(select(CaseKey).where(CaseKey.case_id == case_id))
        if row is None:
            raise CaseKeyDestroyed(case_id)
        return crypto.decrypt(self._master_key, row.wrapped_key, self._context(case_id))

    def destroy_case_key(self, case_id: str) -> None:
        with Session(self._engine) as session, session.begin():
            session.execute(delete(CaseKey).where(CaseKey.case_id == case_id))
