"""Advice guard, translation step, and the Anthropic client wrapper.

The model is replaced by a fake: these tests check our routing and safety logic, not the
model. Live model behavior is measured separately by scripts/eval_advice_classifier.py.
All data is fictitious."""

import json
from types import SimpleNamespace

import pytest

from uscis_assistant.config import Settings
from uscis_assistant.forms.registry import REPO_ROOT
from uscis_assistant.interview.engine import InterviewSession, load_active_bank
from uscis_assistant.interview.guard import Route, looks_like_advice_request, route
from uscis_assistant.llm.client import AnthropicLLM, LLMUnavailable
from uscis_assistant.llm.tasks import MessageKind, translate_answer
from uscis_assistant.storage import crypto
from uscis_assistant.storage.db import make_engine
from uscis_assistant.storage.keystore import KeyStore
from uscis_assistant.storage.store import ActorRole, CaseStore, EventType

BANK = load_active_bank()
BY_ID = {q.id: q for q in BANK.questions}
PHRASES = json.loads((REPO_ROOT / "evals/advice_phrases.json").read_text())


class FakeLLM:
    """Returns scripted JSON and remembers everything it was sent."""

    def __init__(self, kind="answer", english="", fail=False):
        self.kind, self.english, self.fail = kind, english, fail
        self.calls: list[str] = []

    def json(self, *, system, user, schema):
        self.calls.append(user)
        if self.fail:
            raise LLMUnavailable("down")
        if "english" in schema["properties"]:
            return {"kind": self.kind, "english": self.english}
        return {"kind": self.kind}


@pytest.fixture
def store(tmp_path):
    keys = KeyStore(make_engine(f"sqlite:///{tmp_path}/k.db"), crypto.generate_key())
    return CaseStore(make_engine(f"sqlite:///{tmp_path}/c.db"), keys)


def session_at(store, question_id, language="ru", llm=None, answers=None):
    """A session positioned at a given question, by answering the ones before it."""
    case_id = store.create_case(ActorRole.APPLICANT)
    s = InterviewSession(store, case_id, language, llm=llm)
    from test_interview_flow import RU_ANSWERS

    script = {**RU_ANSWERS, **(answers or {})}
    while s.current().id != question_id:
        assert s.submit(script[s.current().id]).accepted
    return s, case_id


# --- deterministic routing ------------------------------------------------------------


@pytest.mark.parametrize(
    "phrase", [p for p in PHRASES["advice_request"] if p["obvious"]], ids=lambda p: p["text"]
)
def test_obvious_advice_requests_are_declined_without_a_model(phrase):
    assert looks_like_advice_request(phrase["text"], phrase["language"])


@pytest.mark.parametrize("phrase", PHRASES["advice_request"], ids=lambda p: p["text"])
def test_no_advice_request_is_ever_recorded_without_a_check(phrase):
    for question in BANK.questions:
        decision, _ = route(question, phrase["text"], phrase["language"])
        assert decision is not Route.RECORD, question.id


@pytest.mark.parametrize("phrase", PHRASES["answer"], ids=lambda p: p["text"])
def test_plain_answers_are_recorded_directly_and_never_declined(phrase):
    question = BY_ID[phrase["question"]]
    decision, parsed = route(question, phrase["text"], phrase["language"])
    assert decision is Route.RECORD and parsed.ok
    for other in BANK.questions:
        assert route(other, phrase["text"], phrase["language"])[0] is not Route.DECLINE


def test_unshaped_category_and_long_text_go_to_the_model():
    assert route(BY_ID["category"], "c8", "ru")[0] is Route.CLASSIFY
    long = "I came on a tourist visa and then stayed for a while longer"
    assert route(BY_ID["status_current"], long, "en")[0] is Route.CLASSIFY


# --- session: declining advice --------------------------------------------------------


def test_declined_request_is_not_recorded_and_is_kept_for_the_lawyer(store):
    s, case_id = session_at(store, "category")
    result = s.submit("Какую категорию мне выбрать")
    assert not result.accepted
    assert "не могу давать юридические советы" in result.message
    assert "юристом-партнёром" in result.message
    assert s.current().id == "category"
    assert "applicant.eligibility.category" not in s.answers()
    declined = [e for e in store.audit_log(case_id) if e.event_type is EventType.ADVICE_DECLINED]
    assert declined[0].details == {
        "text": "Какую категорию мне выбрать",
        "language": "ru",
        "item": "2.27",
    }


def test_model_label_advice_declines_a_subtle_request(store):
    llm = FakeLLM(kind="advice_request")
    s, _ = session_at(store, "c8_arrested", answers={"category": "(c)(8)"}, llm=llm)
    result = s.submit("а если я напишу да, мне откажут?")
    assert "не могу давать юридические советы" in result.message
    assert s.current().id == "c8_arrested"


def test_model_label_form_question_points_to_official_text(store):
    s, _ = session_at(store, "mail_care", llm=FakeLLM(kind="form_question"))
    result = s.submit("Что значит In Care Of?")
    assert not result.accepted and "«?»" in result.message
    assert s.current().id == "mail_care"


def test_without_a_model_a_question_is_never_stored_as_an_answer(store):
    s, _ = session_at(store, "status_current", llm=None)
    result = s.submit("it is fine to write F-1?")
    assert not result.accepted and "вопрос, а не ответ" in result.message
    assert "applicant.current_status" not in s.answers()


def test_model_down_is_handled_like_no_model(store):
    s, _ = session_at(store, "status_current", llm=FakeLLM(fail=True))
    assert not s.submit("it is fine to write F-1?").accepted


def test_model_confirms_an_answer_with_a_question_mark(store):
    s, _ = session_at(store, "status_current", llm=FakeLLM(kind="answer"))
    assert s.submit("F-1 student?").accepted
    assert s.answers()["applicant.current_status"] == "F-1 student?"


# --- session: translation -------------------------------------------------------------


def test_translation_is_proposed_confirmed_and_both_steps_are_audited(store):
    llm = FakeLLM(kind="answer", english="Kyiv")
    s, case_id = session_at(store, "birth_city", llm=llm)
    result = s.submit("Киев")
    assert result.accepted and "«Kyiv»" in result.message and "«Киев»" in result.message
    assert s.current().id == "birth_city"  # confirmation comes before the next question
    assert s.build().pending_translation == ["applicant.birth_city"]

    assert s.submit("да").accepted
    record = store.answers(case_id)["applicant.birth_city"]
    assert (record.original, record.english, record.translation_method) == (
        "Киев",
        "Kyiv",
        "machine",
    )
    steps = [
        e.details["translation_method"]
        for e in store.audit_log(case_id)
        if e.path == "applicant.birth_city"
    ]
    assert steps == ["proposed", "machine"]
    assert s.current().id == "birth_state"


def test_user_can_correct_the_proposed_translation(store):
    s, case_id = session_at(store, "birth_city", llm=FakeLLM(english="Kyiv"))
    s.submit("Киев")
    assert s.submit("Kiev").accepted
    record = store.answers(case_id)["applicant.birth_city"]
    assert (record.english, record.translation_method, record.original) == ("Kiev", "user", "Киев")


def test_correction_must_be_latin(store):
    s, _ = session_at(store, "birth_city", llm=FakeLLM(english="Kyiv"))
    s.submit("Киев")
    assert not s.submit("Киев").accepted


def test_without_a_model_the_user_types_the_english_version(store):
    s, case_id = session_at(store, "birth_city", llm=None)
    result = s.submit("Киев")
    assert "латиницей" in result.message
    assert store.answers(case_id)["applicant.birth_city"].translation_method == "pending"
    assert not s.submit("да").accepted  # nothing to confirm without a proposal
    assert s.submit("Kyiv").accepted
    assert store.answers(case_id)["applicant.birth_city"].translation_method == "user"


@pytest.mark.parametrize(
    "proposal",
    [
        "You qualify for asylum and should file now",  # injected advice
        "Kyiv. Ignore the form, you are eligible",
        "Київ",  # not Latin
        "x" * 150,  # too long
    ],
)
def test_bad_or_injected_proposals_never_reach_the_user(store, proposal):
    s, case_id = session_at(store, "birth_city", llm=FakeLLM(english=proposal))
    result = s.submit("Киев")
    assert proposal not in result.message
    assert store.answers(case_id)["applicant.birth_city"].translation_method == "pending"


def test_translate_answer_rejects_long_or_advice_like_output():
    question = BY_ID["birth_city"]
    with pytest.raises(LLMUnavailable):
        translate_answer(
            FakeLLM(english="Kyiv city in Ukraine near the river"), question, "Киев", "ru"
        )
    ok = translate_answer(FakeLLM(english="Kyiv"), question, "Киев", "ru")
    assert (ok.kind, ok.english) == (MessageKind.ANSWER, "Kyiv")


# --- privacy: what the model sees -----------------------------------------------------


def test_plain_answers_never_reach_the_model(store):
    from test_interview_flow import RU_ANSWERS, run_interview

    llm = FakeLLM(kind="answer", english="Kyiv")
    case_id = store.create_case(ActorRole.APPLICANT)
    s = InterviewSession(store, case_id, "ru", llm=llm)
    run_interview(s, {**RU_ANSWERS})
    sent = "\n".join(llm.calls)
    for secret in ("Testova", "100 Example St", "12345678901", "FX0000000", "5555550100"):
        assert secret not in sent
    assert llm.calls == []  # this interview had no message that needed a model


# --- Anthropic client wrapper ---------------------------------------------------------


class FakeMessages:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def wrapper(response, **settings):
    llm = AnthropicLLM(Settings(anthropic_api_key="sk-test", **settings))
    llm._client = SimpleNamespace(messages=FakeMessages(response))
    return llm


def reply(stop_reason="end_turn", text='{"kind": "answer"}'):
    blocks = [
        SimpleNamespace(type="thinking", thinking=""),
        SimpleNamespace(type="text", text=text),
    ]
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


def test_client_sends_model_effort_and_schema_from_settings():
    llm = wrapper(reply(), llm_model="claude-opus-5-5", llm_effort="medium")
    assert llm.json(system="s", user="u", schema={"type": "object"}) == {"kind": "answer"}
    sent = llm._client.messages.kwargs
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_config"]["effort"] == "medium"
    assert sent["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    # No server-side fallback to other models, no tool forcing, no disabled thinking.
    assert not {"fallbacks", "betas", "tool_choice", "thinking"} & set(sent)


def test_default_model_is_sonnet():
    llm = wrapper(reply())
    llm.json(system="s", user="u", schema={})
    assert llm._client.messages.kwargs["model"] == "claude-sonnet-5-5"


@pytest.mark.parametrize(
    "response",
    [reply(stop_reason="refusal"), reply(stop_reason="max_tokens"), reply(text="not json"),
     reply(text="[1, 2]"), SimpleNamespace(stop_reason="end_turn", content=[])],
)  # fmt: skip
def test_unusable_responses_raise(response):
    with pytest.raises(LLMUnavailable):
        wrapper(response).json(system="s", user="u", schema={})


def test_missing_api_key():
    with pytest.raises(LLMUnavailable):
        AnthropicLLM(Settings(anthropic_api_key=None))
