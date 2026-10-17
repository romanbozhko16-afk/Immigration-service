"""Encrypted storage, audit log, and deletion. All data here is fictitious."""

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from uscis_assistant.config import Settings
from uscis_assistant.storage import crypto
from uscis_assistant.storage.db import make_engine
from uscis_assistant.storage.keystore import CaseKey, CaseKeyDestroyed, KeyStore
from uscis_assistant.storage.models import AuditEvent, AuditLogIsAppendOnly
from uscis_assistant.storage.store import (
    ActorRole,
    CaseDeleted,
    CaseNotFound,
    CaseStore,
    EventType,
    MasterKeyMissing,
    open_case_store,
)

A_NUMBER = "A987654321"
ORIGINAL_RU = "Киев, Украина"
FILENAME = "Passport-Testova-Olena.jpg"
APPLICANT = ActorRole.APPLICANT


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(minutes=1)
        return self.now


@pytest.fixture
def paths(tmp_path) -> dict[str, Path]:
    return {"cases": tmp_path / "cases.db", "keys": tmp_path / "keys.db"}


@pytest.fixture
def master_key() -> bytes:
    return crypto.generate_key()


@pytest.fixture
def store(paths, master_key) -> CaseStore:
    keys = KeyStore(make_engine(f"sqlite:///{paths['keys']}"), master_key)
    return CaseStore(make_engine(f"sqlite:///{paths['cases']}"), keys, clock=FakeClock())


def record_sample(store: CaseStore, case_id: str) -> None:
    store.record_answer(
        case_id,
        path="applicant.a_number",
        item="2.8",
        original=A_NUMBER,
        original_language="ru",
        english=A_NUMBER,
        translation_method="same",
        actor=APPLICANT,
    )
    store.record_answer(
        case_id,
        path="applicant.birth_city",
        item="2.15.A",
        original=ORIGINAL_RU,
        original_language="ru",
        english="Kyiv",
        translation_method="machine",
        actor=APPLICANT,
    )


def raw(path: Path) -> bytes:
    return path.read_bytes()


# --- crypto ---------------------------------------------------------------------------


def test_crypto_round_trip_and_binding():
    key = crypto.generate_key()
    blob = crypto.encrypt(key, b"secret", "case:1:answer:x")
    assert crypto.decrypt(key, blob, "case:1:answer:x") == b"secret"
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(key, blob, "case:2:answer:x")  # other case
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(crypto.generate_key(), blob, "case:1:answer:x")  # other key
    tampered = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(key, tampered, "case:1:answer:x")


def test_same_plaintext_encrypts_differently_each_time():
    key = crypto.generate_key()
    assert crypto.encrypt(key, b"x", "c") != crypto.encrypt(key, b"x", "c")


# --- answers --------------------------------------------------------------------------


def test_answer_keeps_original_and_translation(store):
    case_id = store.create_case(APPLICANT)
    record_sample(store, case_id)
    answer = store.answers(case_id)["applicant.birth_city"]
    assert (answer.original, answer.original_language) == (ORIGINAL_RU, "ru")
    assert (answer.english, answer.translation_method) == ("Kyiv", "machine")


def test_personal_data_never_reaches_disk_in_plain_text(store, paths):
    case_id = store.create_case(APPLICANT)
    record_sample(store, case_id)
    store.add_document(
        case_id,
        kind="passport",
        filename=FILENAME,
        content_type="image/jpeg",
        data=b"FAKE-IMAGE-" + A_NUMBER.encode(),
        actor=APPLICANT,
    )
    for path in paths.values():
        data = raw(path)
        for secret in (A_NUMBER, ORIGINAL_RU, "Kyiv", FILENAME):
            assert secret.encode() not in data, (path.name, secret)


def test_keys_are_not_stored_with_the_data(store, paths):
    case_id = store.create_case(APPLICANT)
    engine = make_engine(f"sqlite:///{paths['keys']}")
    with Session(engine) as session:
        wrapped = session.get(CaseKey, case_id).wrapped_key
    assert wrapped not in raw(paths["cases"])
    assert wrapped in raw(paths["keys"])


def test_ciphertext_moved_to_another_case_cannot_be_read(store, paths):
    a, b = store.create_case(APPLICANT), store.create_case(APPLICANT)
    record_sample(store, a)
    record_sample(store, b)
    engine = make_engine(f"sqlite:///{paths['cases']}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE answers SET ciphertext = (SELECT ciphertext FROM answers "
                "WHERE case_id = :a AND path = 'applicant.a_number') "
                "WHERE case_id = :b AND path = 'applicant.a_number'"
            ),
            {"a": a, "b": b},
        )
    with pytest.raises(crypto.DecryptionError):
        store.answers(b)


def test_ciphertext_moved_to_another_question_cannot_be_read(store, paths):
    # Each ciphertext is bound to its question, so answers cannot be swapped between
    # fields of the same case (cross-case moves already fail on the per-case key).
    case_id = store.create_case(APPLICANT)
    record_sample(store, case_id)
    with make_engine(f"sqlite:///{paths['cases']}").begin() as conn:
        conn.execute(
            text(
                "UPDATE answers SET ciphertext = (SELECT ciphertext FROM answers "
                "WHERE case_id = :c AND path = 'applicant.birth_city') "
                "WHERE case_id = :c AND path = 'applicant.a_number'"
            ),
            {"c": case_id},
        )
    with pytest.raises(crypto.DecryptionError):
        store.answers(case_id)


def test_wrong_master_key_cannot_open_cases(store, paths):
    case_id = store.create_case(APPLICANT)
    other = KeyStore(make_engine(f"sqlite:///{paths['keys']}"), crypto.generate_key())
    with pytest.raises(crypto.DecryptionError):
        other.get_case_key(case_id)


def test_unknown_case(store):
    with pytest.raises(CaseNotFound):
        store.answers("0" * 32)


# --- audit log ------------------------------------------------------------------------


def test_audit_log_records_every_version_with_time_and_actor(store):
    case_id = store.create_case(APPLICANT)
    record_sample(store, case_id)
    store.record_answer(
        case_id,
        path="applicant.birth_city",
        item="2.15.A",
        original="Київ",
        original_language="uk",
        english="Kyiv",
        translation_method="user",
        actor=ActorRole.LAWYER,
    )
    log = store.audit_log(case_id)
    assert [e.event_type for e in log] == [
        EventType.CASE_CREATED,
        EventType.ANSWER_RECORDED,
        EventType.ANSWER_RECORDED,
        EventType.ANSWER_CHANGED,
    ]
    assert [e.seq for e in log] == [1, 2, 3, 4]
    assert all(a.occurred_at < b.occurred_at for a, b in zip(log, log[1:], strict=False))
    first, last = log[2], log[3]
    assert first.details["original"] == ORIGINAL_RU  # the earlier version is kept
    assert (last.details["original"], last.actor_role) == ("Київ", ActorRole.LAWYER)
    assert store.answers(case_id)["applicant.birth_city"].original == "Київ"
    assert store.verify_audit_log(case_id)


def test_audit_events_cannot_be_modified_or_deleted_through_the_code(store, paths):
    case_id = store.create_case(APPLICANT)
    engine = make_engine(f"sqlite:///{paths['cases']}")
    with Session(engine) as session:
        event = session.query(AuditEvent).filter_by(case_id=case_id).one()
        event.event_type = "answer_changed"
        with pytest.raises(AuditLogIsAppendOnly):
            session.flush()
    with Session(engine) as session:
        session.delete(session.query(AuditEvent).filter_by(case_id=case_id).one())
        with pytest.raises(AuditLogIsAppendOnly):
            session.flush()


@pytest.mark.parametrize(
    "tamper",
    [
        "UPDATE audit_events SET actor_role = 'lawyer' WHERE seq = 2",
        "UPDATE audit_events SET occurred_at = '2020-01-01 00:00:00' WHERE seq = 1",
        "DELETE FROM audit_events WHERE seq = 2",
        "DELETE FROM audit_events WHERE seq = 3",  # the newest event
    ],
)
def test_direct_database_tampering_is_detected(store, paths, tamper):
    case_id = store.create_case(APPLICANT)
    record_sample(store, case_id)
    assert store.verify_audit_log(case_id)
    with make_engine(f"sqlite:///{paths['cases']}").begin() as conn:
        conn.execute(text(tamper + " AND case_id = :c"), {"c": case_id})
    assert not store.verify_audit_log(case_id)


# --- documents ------------------------------------------------------------------------


def test_document_round_trip_and_removal(store):
    case_id = store.create_case(APPLICANT)
    doc_id = store.add_document(
        case_id,
        kind="passport",
        filename=FILENAME,
        content_type="image/jpeg",
        data=b"FAKE",
        actor=APPLICANT,
    )
    doc = store.document(case_id, doc_id)
    assert (doc.filename, doc.data, doc.kind) == (FILENAME, b"FAKE", "passport")
    store.delete_document(case_id, doc_id, APPLICANT)
    with pytest.raises(KeyError):
        store.document(case_id, doc_id)
    assert store.audit_log(case_id)[-1].event_type is EventType.DOCUMENT_DELETED


# --- deletion on request --------------------------------------------------------------


def test_delete_case_destroys_key_data_and_leaves_tombstone(store, paths):
    case_id = store.create_case(APPLICANT)
    record_sample(store, case_id)
    store.add_document(
        case_id,
        kind="passport",
        filename=FILENAME,
        content_type="image/jpeg",
        data=b"FAKE",
        actor=APPLICANT,
    )
    keys_engine = make_engine(f"sqlite:///{paths['keys']}")
    with Session(keys_engine) as session:
        wrapped = session.get(CaseKey, case_id).wrapped_key
    with make_engine(f"sqlite:///{paths['cases']}").connect() as conn:
        answer_blob = conn.execute(text("SELECT ciphertext FROM answers LIMIT 1")).scalar()

    store.delete_case(case_id, APPLICANT)

    assert store.case_status(case_id) == "deleted"
    with pytest.raises(CaseKeyDestroyed):
        KeyStore(keys_engine, b"\0" * 32).get_case_key(case_id)
    for read in (lambda: store.answers(case_id), lambda: store.document(case_id, "x")):
        with pytest.raises(CaseDeleted):
            read()
    with pytest.raises(CaseDeleted):
        record_sample(store, case_id)
    with pytest.raises(CaseDeleted):
        store.delete_case(case_id, APPLICANT)

    log = store.audit_log(case_id)
    assert [(e.event_type, e.details) for e in log] == [(EventType.CASE_DELETED, None)]
    assert store.verify_audit_log(case_id)
    # secure_delete: the destroyed key and the removed ciphertext are gone from the files.
    assert wrapped not in raw(paths["keys"])
    assert answer_blob not in raw(paths["cases"])


def test_deleting_one_case_leaves_others_intact(store):
    keep, drop = store.create_case(APPLICANT), store.create_case(APPLICANT)
    record_sample(store, keep)
    record_sample(store, drop)
    store.delete_case(drop, APPLICANT)
    assert store.answers(keep)["applicant.a_number"].english == A_NUMBER
    assert store.verify_audit_log(keep)


# --- logging and configuration --------------------------------------------------------


def test_storage_writes_no_personal_data_to_logs(store, caplog):
    caplog.set_level(logging.DEBUG)
    case_id = store.create_case(APPLICANT)
    record_sample(store, case_id)
    store.answers(case_id)
    store.audit_log(case_id)
    store.delete_case(case_id, APPLICANT)
    for secret in (A_NUMBER, ORIGINAL_RU, "Kyiv"):
        assert secret not in caplog.text


def test_open_case_store_requires_master_key(tmp_path, monkeypatch):
    monkeypatch.delenv("MASTER_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    urls = {
        "database_url": f"sqlite:///{tmp_path}/c.db",
        "keystore_url": f"sqlite:///{tmp_path}/k.db",
    }
    with pytest.raises(MasterKeyMissing):
        open_case_store(Settings(**urls))
    key = crypto.encode_key(crypto.generate_key())
    store = open_case_store(Settings(master_key=key, **urls))
    assert store.case_status(store.create_case(APPLICANT)) == "active"


def test_master_key_must_be_32_bytes():
    with pytest.raises(ValueError):
        crypto.decode_key(crypto.encode_key(b"short"))
