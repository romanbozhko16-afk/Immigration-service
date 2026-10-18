"""Reference chat: corpus, search, and the answer pipeline with a fake model."""

import re
from types import SimpleNamespace

import pytest

from uscis_assistant.config import Settings
from uscis_assistant.llm.client import AnthropicLLM, CitedAnswer, CitedRange, LLMUnavailable
from uscis_assistant.reference.chat import ReferenceChat, ReferenceStatus
from uscis_assistant.reference.corpus import instructions_corpus, normalize
from uscis_assistant.reference.search import SearchIndex, tokenize
from uscis_assistant.reference.texts import OFFICIAL_LABEL

CORPUS = instructions_corpus()


class FakeStructured:
    def __init__(self, kind="general_question", query="", fail=False):
        self.kind, self.query, self.fail, self.calls = kind, query, fail, 0

    def json(self, *, system, user, schema):
        self.calls += 1
        if self.fail:
            raise LLMUnavailable("down")
        return {"kind": self.kind, "query": self.query}


class FakeCiting:
    """Cites the given blocks that contain `cite_containing`; writes `text` as its prose."""

    def __init__(self, cite_containing=None, text="Here is the answer.", fail=False, bad=None):
        self.cite_containing, self.text, self.fail, self.bad = cite_containing, text, fail, bad
        self.blocks: list[str] = []

    def cite(self, *, system, title, blocks, question):
        self.blocks = blocks
        if self.fail:
            raise LLMUnavailable("down")
        if self.bad is not None:
            return CitedAnswer(text=self.text, citations=[self.bad])
        citations = [
            CitedRange(start=i, end=i + 1, cited_text=b)
            for i, b in enumerate(blocks)
            if self.cite_containing and self.cite_containing in b
        ]
        return CitedAnswer(text=self.text, citations=citations)


def chat(query="date of birth format", cite="mm/dd/yyyy", **kw) -> ReferenceChat:
    return ReferenceChat(FakeStructured(query=query), FakeCiting(cite_containing=cite, **kw))


# --- corpus and search ------------------------------------------------------------------


def test_corpus_covers_every_page_without_page_headers():
    pages = {s.page for s in CORPUS.sentences}
    assert pages == set(range(1, 26))
    assert not [s for s in CORPUS.sentences if re.search(r"Page \d+ of 25", s.text)]


def test_hyphenated_identifiers_are_kept_as_terms():
    assert {"i-94", "a-number"} <= set(tokenize("Where is my I-94 and A-Number?"))


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("In Care Of Name mailing address", "In Care Of Name"),
        ("date of birth format", "mm/dd/yyyy format"),
        ("A-Number begins with A", "begins with an"),
        ("Form I-94 number", "provide your Form I-94 number"),
        ("SEVIS number", "If you were issued a SEVIS number"),
        ("need extra space Part 6 Additional Information", "Part 6. Additional Information"),
        ("passport expired travel document", "even if the passport or travel document"),
    ],
)
def test_search_finds_the_relevant_sentence(query, expected):
    hits = SearchIndex(CORPUS).search(query, limit=6)
    assert any(expected in CORPUS.sentences[i].text for _, window in hits for i in window)


# --- answering ------------------------------------------------------------------------


def test_answer_is_only_verbatim_official_sentences_with_page_and_label():
    answer = chat(text="Your DOB goes here; I think you qualify.").ask(
        "Как писать дату рождения?", "ru"
    )
    assert answer.status is ReferenceStatus.ANSWERED
    assert answer.quotes[0].page == 19
    assert "mm/dd/yyyy" in answer.quotes[0].text
    for quote in answer.quotes:  # every quote is a real sentence of the instructions
        assert any(normalize(quote.text) == normalize(s.text) for s in CORPUS.sentences)
    assert "Справочная информация из официальных источников USCIS" in answer.message
    assert OFFICIAL_LABEL in answer.message
    assert "uscis.gov/i-765" in answer.message
    assert "qualify" not in answer.message  # the model's own prose is never shown


@pytest.mark.parametrize("language", ["ru", "uk", "en"])
def test_label_is_present_in_every_language(language):
    answer = chat().ask("date of birth format?", language)
    assert OFFICIAL_LABEL in answer.message


def test_obvious_personal_question_is_declined_without_any_model():
    structured = FakeStructured()
    answer = ReferenceChat(structured, FakeCiting()).ask("Подхожу ли я под (c)(8)?", "ru")
    assert answer.status is ReferenceStatus.DECLINED
    assert structured.calls == 0


def test_model_label_personal_advice_is_declined():
    rc = ReferenceChat(FakeStructured(kind="personal_advice"), FakeCiting(cite_containing="x"))
    answer = rc.ask("а мне вообще дадут разрешение, если я просрочил визу", "ru")
    assert answer.status is ReferenceStatus.DECLINED and answer.quotes == []


def test_off_topic():
    rc = ReferenceChat(FakeStructured(kind="off_topic"), FakeCiting())
    assert rc.ask("Какая погода в Нью-Йорке?", "ru").status is ReferenceStatus.OFF_TOPIC


def test_no_citation_means_i_dont_know():
    answer = chat(cite=None).ask("What is the meaning of life on this form?", "en")
    assert answer.status is ReferenceStatus.NO_ANSWER
    assert "I don't know" in answer.message and "attorney" in answer.message


def test_model_saying_no_answer_wins_even_with_citations():
    answer = chat(text="NO_ANSWER").ask("date of birth format?", "en")
    assert answer.status is ReferenceStatus.NO_ANSWER


def test_no_search_hit_skips_the_citing_call():
    citing = FakeCiting(cite_containing="mm/dd/yyyy")
    answer = ReferenceChat(FakeStructured(query="zzzz qqqq"), citing).ask("??", "en")
    assert answer.status is ReferenceStatus.NO_ANSWER and citing.blocks == []


@pytest.mark.parametrize(
    "bad",
    [
        CitedRange(start=0, end=999, cited_text="x"),  # outside the given blocks
        CitedRange(start=2, end=1, cited_text="x"),
        CitedRange(start=0, end=1, cited_text="You qualify for an EAD."),  # text mismatch
    ],
)
def test_invalid_citations_are_ignored(bad):
    answer = chat(bad=bad).ask("date of birth format?", "en")
    assert answer.status is ReferenceStatus.NO_ANSWER


@pytest.mark.parametrize("which", ["structured", "citing"])
def test_model_failure_never_produces_an_invented_answer(which):
    structured = FakeStructured(query="date of birth", fail=which == "structured")
    citing = FakeCiting(cite_containing="mm/dd/yyyy", fail=which == "citing")
    answer = ReferenceChat(structured, citing).ask("date of birth format?", "en")
    assert answer.status is ReferenceStatus.UNAVAILABLE and answer.quotes == []


def test_without_a_model_the_chat_is_unavailable():
    assert ReferenceChat(None, None).ask("date of birth?", "en").status is (
        ReferenceStatus.UNAVAILABLE
    )


def test_non_english_search_query_from_the_model_is_rejected():
    rc = ReferenceChat(FakeStructured(query="дата рождения"), FakeCiting(cite_containing="x"))
    assert rc.ask("Как писать дату?", "ru").status is ReferenceStatus.UNAVAILABLE


# --- Anthropic citing request ---------------------------------------------------------


def test_cite_request_uses_custom_content_with_citations_and_parses_them():
    citation = SimpleNamespace(
        type="content_block_location",
        document_index=0,
        start_block_index=1,
        end_block_index=2,
        cited_text="Second.",
    )
    response = SimpleNamespace(
        stop_reason="end_turn",
        content=[
            SimpleNamespace(type="text", text="See ", citations=None),
            SimpleNamespace(type="text", text="this", citations=[citation]),
        ],
    )
    llm = AnthropicLLM(Settings(anthropic_api_key="sk-test"))
    calls = {}
    llm._client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kw: calls.update(kw) or response)
    )
    result = llm.cite(system="s", title="T", blocks=["First.", "Second."], question="q")
    assert result.citations == [CitedRange(start=1, end=2, cited_text="Second.")]
    document = calls["messages"][0]["content"][0]
    assert document["source"]["type"] == "content"
    assert document["citations"] == {"enabled": True}
    assert "format" not in calls["output_config"]  # citations cannot be combined with it
    assert calls["model"] == "claude-sonnet-5-5"


def test_cite_refusal_is_unavailable():
    llm = AnthropicLLM(Settings(anthropic_api_key="sk-test"))
    response = SimpleNamespace(stop_reason="refusal", content=[])
    llm._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: response))
    with pytest.raises(LLMUnavailable):
        llm.cite(system="s", title="T", blocks=["a"], question="q")


def test_sentences_do_not_end_inside_a_reference():
    # "Part 6." or "Item Number 16." must not cut a sentence into fragments.
    pattern = re.compile(r"\b(Part|Item Numbers?)\s+[0-9][0-9a-z.\- ]*\.$")
    assert [s.text for s in CORPUS.sentences if pattern.search(s.text)] == []
