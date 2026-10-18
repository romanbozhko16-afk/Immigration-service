"""HTTP API: access control, privacy properties, and the three flows end to end.
All data is fictitious."""

import logging
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_interview_flow import RU_ANSWERS
from test_llm_guard import FakeLLM

from uscis_assistant.api.app import create_app
from uscis_assistant.api.auth import InsecureConfiguration, role_from_header, validate_tokens
from uscis_assistant.config import Settings
from uscis_assistant.storage import crypto
from uscis_assistant.storage.db import make_engine
from uscis_assistant.storage.keystore import KeyStore
from uscis_assistant.storage.store import ActorRole, CaseStore

APPLICANT = "applicant-token-0123456789abcdef"
LAWYER = "lawyer-token-0123456789abcdefgh"
A = {"Authorization": f"Bearer {APPLICANT}"}
L = {"Authorization": f"Bearer {LAWYER}"}


def make_settings(**kw) -> Settings:
    return Settings(applicant_token=APPLICANT, lawyer_token=LAWYER, **kw)


@pytest.fixture
def store(tmp_path):
    keys = KeyStore(make_engine(f"sqlite:///{tmp_path}/k.db"), crypto.generate_key())
    return CaseStore(make_engine(f"sqlite:///{tmp_path}/c.db"), keys)


@pytest.fixture
def client(store):
    app = create_app(make_settings(), store, today=lambda: date(2026, 10, 18))
    return TestClient(app, raise_server_exceptions=False)


def new_case(client) -> str:
    return client.post("/api/cases", headers=A).json()["case_id"]


def answer_until(client, case_id, stop_id, script=None):
    """Answer by following the prompts' questions until `stop_id` would be asked next."""
    from uscis_assistant.interview.engine import load_active_bank

    bank = {q.id: q for q in load_active_bank().questions}
    answers = {**RU_ANSWERS, **(script or {})}
    asked = []
    while True:
        prompt = client.get(
            f"/api/cases/{case_id}/interview", params={"language": "ru"}, headers=A
        ).json()
        if prompt["done"]:
            return asked
        current = next(q for q in bank.values() if q.prompt["ru"] in prompt["prompt"])
        if current.id == stop_id:
            return asked
        reply = client.post(
            f"/api/cases/{case_id}/interview",
            json={"language": "ru", "message": answers[current.id]},
            headers=A,
        ).json()
        assert reply["accepted"], (current.id, reply["message"])
        asked.append(current.id)
        assert len(asked) < 200


# --- tokens and startup ---------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"applicant_token": "x" * 30},
        {"applicant_token": "short", "lawyer_token": "y" * 30},
        {"applicant_token": "z" * 30, "lawyer_token": "z" * 30},
    ],
)
def test_app_refuses_to_start_with_missing_weak_or_equal_tokens(store, kwargs):
    with pytest.raises(InsecureConfiguration):
        create_app(Settings(**kwargs), store)


def test_role_from_header():
    assert role_from_header(f"Bearer {LAWYER}", APPLICANT, LAWYER) is ActorRole.LAWYER
    assert role_from_header(f"Bearer {APPLICANT}", APPLICANT, LAWYER) is ActorRole.APPLICANT
    for bad in (None, "", "Bearer ", "Bearer nope", f"Basic {LAWYER}", LAWYER):
        assert role_from_header(bad, APPLICANT, LAWYER) is None
    assert validate_tokens(make_settings()) == (APPLICANT, LAWYER)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/me"),
        ("POST", "/api/cases"),
        ("POST", "/api/chat"),
        ("GET", "/api/lawyer/cases"),
        ("GET", f"/api/cases/{'a' * 32}/flags"),
        ("DELETE", f"/api/cases/{'a' * 32}"),
    ],
)
def test_every_endpoint_requires_a_valid_token(client, method, path):
    assert client.request(method, path).status_code == 401
    assert (
        client.request(method, path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    )


def test_roles_are_enforced(client):
    case_id = new_case(client)
    for path in (
        "/api/lawyer/cases",
        f"/api/lawyer/cases/{case_id}/review",
    ):
        assert client.get(path, headers=A).status_code == 403
    assert client.post(f"/api/lawyer/cases/{case_id}/fill", headers=A).status_code == 403
    assert (
        client.post(
            f"/api/lawyer/cases/{case_id}/decision", json={"decision": "complete"}, headers=A
        ).status_code
        == 403
    )
    # The lawyer does not answer the interview in the applicant's place.
    body = {"language": "ru", "message": "1"}
    assert client.post(f"/api/cases/{case_id}/interview", json=body, headers=L).status_code == 403
    assert client.get("/api/me", headers=A).json() == {"role": "applicant"}
    assert client.get("/api/me", headers=L).json() == {"role": "lawyer"}


def test_role_cannot_be_chosen_in_the_request(client):
    case_id = new_case(client)
    r = client.post(
        f"/api/cases/{case_id}/interview",
        json={"language": "ru", "message": "1", "role": "lawyer"},
        headers=A,
    )
    assert r.status_code == 422  # unknown fields are rejected


# --- web page and headers -------------------------------------------------------------


def test_page_shows_the_disclaimer_in_all_three_languages(client):
    page = client.get("/").text
    assert "This service is not a law firm and does not provide legal advice." in page
    assert "не является юридической фирмой и не даёт юридических консультаций" in page
    assert "не є юридичною фірмою і не надає юридичних консультацій" in page


def test_a_short_disclaimer_strip_stays_visible_in_all_three_languages(client):
    page = client.get("/").text
    assert "Not legal advice · Не юридична консультація · Не юридическая консультация" in page
    css = client.get("/static/style.css").text
    assert re.search(r"#strip\s*\{[^}]*position:\s*sticky", css)


def test_security_headers_and_no_inline_scripts(client):
    r = client.get("/")
    assert r.headers["content-security-policy"].startswith("default-src 'self'")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", r.text)  # no inline script
    assert client.get("/api/health").headers["cache-control"] == "no-store"
    assert client.get("/static/app.js").status_code == 200


def test_javascript_never_inserts_server_text_as_html():
    from uscis_assistant.api.app import STATIC_DIR

    js = (STATIC_DIR / "app.js").read_text()
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", js)


def test_no_api_documentation_is_exposed(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


# --- interview ------------------------------------------------------------------------


def test_interview_over_http_in_russian(client):
    case_id = new_case(client)
    first = client.get(
        f"/api/cases/{case_id}/interview", params={"language": "ru"}, headers=A
    ).json()
    assert "Почему вы подаёте форму I-765?" in first["prompt"] and not first["done"]

    bad = client.post(
        f"/api/cases/{case_id}/interview", json={"language": "ru", "message": "9"}, headers=A
    ).json()
    assert not bad["accepted"] and "выберите номер" in bad["message"]

    good = client.post(
        f"/api/cases/{case_id}/interview", json={"language": "ru", "message": "1"}, headers=A
    ).json()
    assert good["accepted"] and "фамилия" in good["next_prompt"]


def test_advice_request_is_declined_over_http(client):
    case_id = new_case(client)
    reply = client.post(
        f"/api/cases/{case_id}/interview",
        json={"language": "ru", "message": "Какие у меня шансы?"},
        headers=A,
    ).json()
    assert not reply["accepted"]
    assert "не могу давать юридические советы" in reply["message"]


def test_whole_flow_from_interview_to_attorney_pdf(client):
    case_id = new_case(client)
    answer_until(client, case_id, stop_id="never")  # runs to the end
    done = client.get(
        f"/api/cases/{case_id}/interview", params={"language": "ru"}, headers=A
    ).json()
    assert done["done"]

    flags = client.get(f"/api/cases/{case_id}/flags", headers=A).json()
    assert flags["application_built"]
    assert any(f["severity"] == "attorney" for f in flags["flags"])
    assert all("Form I-765" in f["source"] for f in flags["flags"])

    assert client.get("/api/lawyer/cases", headers=L).json()[0]["case_id"] == case_id
    review = client.get(f"/api/lawyer/cases/{case_id}/review", headers=L).json()
    assert review["summary"].startswith("# Case review: Form I-765")
    assert "case_created" in review["audit_log"]

    assert (
        client.post(
            f"/api/lawyer/cases/{case_id}/decision",
            json={"decision": "not_required", "note": "Applicant reads English."},
            headers=L,
        ).status_code
        == 204
    )
    fill = client.post(f"/api/lawyer/cases/{case_id}/fill", headers=L)
    assert fill.status_code == 200 and fill.json()["filled_fields"] > 30
    pdf = client.get(
        f"/api/lawyer/cases/{case_id}/documents/{fill.json()['document_id']}", headers=L
    )
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"] == "application/pdf"
    # Applicants cannot download the draft.
    url = f"/api/lawyer/cases/{case_id}/documents/{fill.json()['document_id']}"
    assert client.get(url, headers=A).status_code == 403


def test_fill_is_refused_while_the_interview_is_unfinished(client):
    case_id = new_case(client)
    r = client.post(f"/api/lawyer/cases/{case_id}/fill", headers=L)
    assert r.status_code == 409


def test_attorney_data_validation(client):
    case_id = new_case(client)
    ok = client.post(
        f"/api/lawyer/cases/{case_id}/attorney-data",
        json={"path": "interpreter.name.family_name", "value": "Interp"},
        headers=L,
    )
    assert ok.status_code == 204
    bad = client.post(
        f"/api/lawyer/cases/{case_id}/attorney-data",
        json={"path": "applicant.sex", "value": "male"},
        headers=L,
    )
    assert bad.status_code == 422


# --- reference chat -------------------------------------------------------------------


def test_chat_declines_personal_questions_and_labels_answers(store):
    from test_reference_chat import FakeCiting, FakeStructured

    app = create_app(
        make_settings(),
        store,
        structured_llm=FakeStructured(query="date of birth format"),
        citing_llm=FakeCiting(cite_containing="mm/dd/yyyy"),
    )
    c = TestClient(app)
    declined = c.post(
        "/api/chat", json={"language": "en", "message": "Do I qualify for (c)(8)?"}, headers=A
    ).json()
    assert declined["status"] == "declined" and declined["quotes"] == []
    answered = c.post(
        "/api/chat", json={"language": "en", "message": "date of birth format?"}, headers=A
    ).json()
    assert answered["status"] == "answered"
    assert (
        "Reference information from official USCIS sources. Not legal advice."
        in (answered["message"])
    )
    assert answered["quotes"][0]["page"] == 19


def test_chat_without_a_model_is_unavailable_not_invented(client):
    r = client.post(
        "/api/chat", json={"language": "en", "message": "date of birth format?"}, headers=A
    ).json()
    assert r["status"] == "unavailable" and r["quotes"] == []


def test_message_length_is_limited(client):
    r = client.post("/api/chat", json={"language": "en", "message": "x" * 2001}, headers=A)
    assert r.status_code == 422


# --- deletion and ids -----------------------------------------------------------------


def test_delete_case_on_request(client, store):
    case_id = new_case(client)
    client.post(
        f"/api/cases/{case_id}/interview", json={"language": "ru", "message": "1"}, headers=A
    )
    assert client.delete(f"/api/cases/{case_id}", headers=A).status_code == 204
    assert client.get(f"/api/cases/{case_id}/flags", headers=A).status_code == 410
    assert client.delete(f"/api/cases/{case_id}", headers=A).status_code == 410
    assert store.case_status(case_id) == "deleted"


def test_unknown_and_malformed_case_ids(client):
    assert client.get(f"/api/cases/{'f' * 32}/flags", headers=A).status_code == 404
    assert client.get("/api/cases/not-an-id/flags", headers=A).status_code == 422


# --- privacy --------------------------------------------------------------------------


def test_errors_do_not_echo_user_input_or_leak_details(store, caplog):
    leaked_text = "A987654321-secret-answer"

    class Boom(FakeLLM):
        def json(self, **kw):
            raise RuntimeError(f"failure with {leaked_text}")

    app = create_app(make_settings(), store, structured_llm=Boom())
    c = TestClient(app, raise_server_exceptions=False)
    caplog.set_level(logging.DEBUG)
    case_id = c.post("/api/cases", headers=A).json()["case_id"]
    r = c.post(
        f"/api/cases/{case_id}/interview",
        json={"language": "ru", "message": f"{leaked_text}?"},
        headers=A,
    )
    assert r.status_code == 500 and leaked_text not in r.text
    assert r.json() == {"detail": "internal error"}
    assert leaked_text not in caplog.text


def test_no_personal_data_in_logs_during_a_full_flow(client, caplog):
    caplog.set_level(logging.DEBUG)
    case_id = new_case(client)
    answer_until(client, case_id, stop_id="never")
    client.get(f"/api/lawyer/cases/{case_id}/review", headers=L)
    for secret in ("Testova", "100 Example St", "12345678901", "FX0000000", "5555550100"):
        assert secret not in caplog.text
