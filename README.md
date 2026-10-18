# USCIS Form Assistant (MVP)

> **This service is not a law firm and does not provide legal advice.** It helps people
> enter their own information into official USCIS forms. Using it does not create an
> attorney-client relationship.

An AI-assisted intake tool for **Form I-765, Application for Employment Authorization**,
edition **08/21/25**. It interviews the applicant in Russian, Ukrainian, or English, records
the answers, checks them for formal errors, and fills in the official PDF as a draft for an
attorney to review.

Audiences:

- **Law firms (B2B):** a client intake tool. A licensed attorney reviews and is responsible
  for every case.
- **Individuals (B2C):** self-preparation of the form, with optional paid review by a
  partner attorney.

**Status:** MVP, all 11 planned steps done. It has not been reviewed by an attorney and has not
been used with real applicants. See [Questions for Attorney Review](#questions-for-attorney-review)
and [Known Limitations](#known-limitations) before any external use.

Contents: [Legal Principles](#legal-principles-of-the-product) ·
[How the Principles Are Enforced](#how-the-principles-are-enforced) ·
[Data Protection](#data-protection) · [Questions for Attorney Review](#questions-for-attorney-review) ·
[Known Limitations](#known-limitations) · [Architecture](#architecture) ·
[Getting Started](#getting-started)

---

## Legal Principles of the Product

*Draft. To be reviewed by a U.S.-licensed immigration attorney before external use.*

The product is designed so that it does not engage in the practice of law. Where possible
these principles are enforced by code and tests, not only by instructions to an AI model.
The next section lists the mechanism behind each one.

### 1. No legal advice

The system does not:

- assess eligibility or the chances of approval;
- choose a case type, an eligibility category, or a filing strategy;
- tell a user that an option "applies to them" or that they "should" file anything;
- interpret the user's facts against the law.

### 2. What the system does

- Asks the questions that the form asks, one at a time, in plain language. The questions,
  their order and the conditions under which they are asked are fixed data, reviewed in
  advance. The AI model does not decide what to ask.
- Explains what a form question means **only** by showing the verbatim text of the official
  USCIS form instructions or the form's own help text, with its page number and a link to
  the USCIS form page. It never paraphrases.
- Records the user's answers as typed, in the original language, together with the English
  text that goes on the form and how that English text was produced.
- Checks for formal errors (missing required answers, date and number formats, internally
  inconsistent answers, entries that do not fit on the form) and **flags** them. It never
  corrects an answer on its own. Each check cites the page of the instructions or the form
  help text it is based on.
- Fills in the official PDF of the edition in use, as a draft for review.

### 3. Requests for advice are declined

If a user asks for advice ("Am I eligible?", "What should I file?", "What are my chances?"),
the system politely declines, says that it cannot give legal advice, and offers review by a
partner attorney. The request is not answered and is not stored as an answer. An encrypted
record of it is kept for the reviewing attorney.

The AI model never writes the text the user sees. It only labels a message (an answer, a
request for advice, a general question about the form, unclear) or proposes an English
rendering of a short answer, which the user must confirm or replace. Every refusal and every
other message is fixed text written in advance. Obvious requests for advice are recognized
without the AI model at all.

### 4. The eligibility category comes from the user

The system never determines the eligibility category and does not offer a list to choose
from. The user enters the category from their own documents. If the user does not know it,
the case is marked **"Requires attorney review"**. The system checks only the shape of the
entry (for example `(c)(8)`), never whether it is the right category.

### 5. Reference chat: official text only

The reference chat answers general questions about the form (for example, "What do the
instructions say about Form I-94?"):

- The answer consists only of verbatim sentences from the official instructions, each with
  its page number and a link. The AI model selects the passages through citations; its own
  wording is never shown.
- If no passage answers the question, the user is told that the system does not know and is
  referred to an attorney. It does not guess.
- Questions about the user's personal situation (eligibility, chances, what to file) are
  declined as in principle 3.
- Every answer carries the label *"Reference information from official USCIS sources. Not
  legal advice."*
- Current source: the Form I-765 instructions of the edition in use. The USCIS Policy Manual
  is not included yet (see [Known Limitations](#known-limitations)).

### 6. Sections reserved for an attorney's decision

Whether and how to complete the **Interpreter** (Part 4) and **Preparer** (Part 5) sections
of Form I-765 is a legal question when the interview is conducted by software in a language
other than English. The system does not decide it. These sections are always flagged
**"Requires attorney decision"**. The interview never asks them, and the PDF leaves them
blank until an attorney records a decision. The same applies to the applicant's statement
(Part 3, items 1-2).

### 7. Answers that always go to an attorney

Some answers are flagged **"Requires attorney review"** whatever their content, because
their consequences are legal rather than formal:

- no eligibility category entered;
- "Yes" to the questions about arrests and convictions (Part 2, items 30 and 31.B);
- the ABC settlement box (Part 3, item 6).

### 8. Signatures are never filled

The applicant's, interpreter's and preparer's signatures and signature dates are never
filled in. The applicant signs in ink.

### 9. Clear disclaimer

Every page shows the disclaimer in English, Russian and Ukrainian, with a short reminder that
stays visible while scrolling.

### 10. Same quality for every user

Free and paid users are served by the same AI model with the same settings. Paid review adds
a human attorney; it does not unlock a "better" AI.

---

## How the Principles Are Enforced

| Principle | Mechanism | Tests |
|---|---|---|
| 1, 3 No advice; requests declined | Fixed patterns in RU/UK/EN catch obvious requests without a model call (`interview/guard.py`). Messages with a "?", unparseable answers, odd categories or long text are labelled by the model first; without a model, or on any model error, they are never recorded as answers. | `test_llm_guard.py` (34 advice phrases, 20 plain answers that must not be refused) |
| 1 Model does not write user text | The model returns only a label (structured JSON) or a short Latin translation proposal. Proposals that are not short Latin text, are much longer than the answer, or read like advice are discarded. | `test_llm_guard.py` |
| 2 Questions are data | 81 questions with conditions in `forms/i765/interview/08-21-25.json`. | `test_interview_bank.py`, `test_interview_flow.py` |
| 2, 5 Verbatim official text | Each help quote and each chat sentence is compared with the official PDF, on the stated page. | `test_interview_bank.py`, `test_reference_chat.py` |
| 2 Flags, no silent fixes | Validation rules only produce flags; a test checks that they never change data. Each rule cites its source. | `test_i765_validation.py` |
| 4 Category from the user | The interview stores the user's text exactly or "unknown" (attorney review). It offers no list. | `test_interview_flow.py`, `test_i765_validation.py` |
| 5 "I don't know" | No citation, an invalid citation, or "no answer" from the model gives a fixed "I don't know, ask an attorney". Any model failure gives "unavailable". | `test_reference_chat.py` |
| 6, 8 Reserved sections, signatures | The field map marks attorney-decision items and leaves signatures unmapped. The filler skips those items until an attorney decides; the interview never asks them. | `test_i765_field_map.py`, `test_i765_filler.py`, `test_lawyer_mode.py` |
| 9 Disclaimer | Static page text in three languages. | `test_api.py` |
| 10 Same model | One model setting for the whole service; only `claude-sonnet-5-5` (default) and `claude-opus-5-5` are accepted. | `test_config.py` |

After each development step the safeguards were deliberately weakened one at a time (for
example: show the model's own wording in the chat, skip the advice check, fill reserved
sections without a decision). Every such change made the tests fail. This shows the tests
detect these failures; it does not prove the absence of others.

---

## Data Protection

- **Encryption.** All personal data (answers in the original language and in English,
  documents and their file names, audit details, declined requests) is encrypted with
  AES-256-GCM using a separate key for each case. Each value is bound to its case and field,
  so it cannot be moved to another record. Case keys are encrypted with a master key and kept
  in a separate key store, not next to the data. Database columns that are not encrypted
  hold no personal data (ids, timestamps, status, event types, question numbers).
- **Audit log.** Every change to a case is recorded in an append-only log with a UTC
  timestamp and the role that made it (applicant, lawyer, system). The log is hash-chained
  and its latest hash is kept on the case record, so edits and removed entries are detected.
  Limitation: someone with full write access to the database could rewrite both.
- **Deletion on request.** The case key is destroyed first, so every copy of the encrypted
  data becomes unreadable, including copies in backups of the case database, as long as
  key-store backups are kept separately and for a shorter time. Then the records are
  removed; SQLite overwrites the freed space. Only a record that a deletion took place
  remains, with no personal data.
- **No personal data in logs.** The code never logs answers, documents, prompts, model
  output or request bodies. Error responses never repeat what the user typed. A redaction
  filter removes identifiers (A-Numbers, SSNs, document and receipt numbers, phone numbers,
  emails) that reach a log line by mistake.
- **Data sent to the AI provider (Anthropic).** Only messages that need it: answers typed in
  Cyrillic that need an English version, messages that may be questions rather than answers,
  and reference-chat questions with the matching instruction sentences. Plain answers
  (names, numbers, addresses, dates) are not sent. This must be disclosed in the privacy
  policy. Claude Fable 5.1 is not used because it requires 30-day data retention.
- **Translations.** Every machine translation is shown to the applicant and confirmed before
  it can be used. The attorney sees which answers were machine-translated.
- **Filled PDF.** The draft contains personal data. It is stored encrypted like any other
  document and only the attorney role can download it.
- **Secrets** live only in `.env`, which is never committed. Development and tests use
  fictitious data only.

---

## Questions for Attorney Review

These are open legal or product questions. The software does not answer them; current
behavior is stated so that it can be confirmed or changed.

1. **The Legal Principles above.** Are they sufficient to keep the product, in both the B2B
   and the B2C setting, from engaging in the unauthorized practice of law?
2. **Paid B2C service.** Does a paid self-preparation service fit within the limits on
   form-completion assistance in the definitions of "practice" and "preparation" in
   8 CFR 1.2 (and any state rules that apply)? The regulation's text was not re-checked for
   this README because the official sites are not reachable from the build environment.
3. **Interpreter and Preparer sections.** Should they be completed when the interview is
   conducted by software in Russian or Ukrainian, and by whom? *Current behavior:* always
   flagged; left blank until the attorney records "complete" or "not required".
4. **Draft PDF for individuals.** May B2C users receive the filled draft directly?
   *Current behavior:* only the attorney role can create and download it.
5. **"(if any)" questions.** Should a question the person has no answer for print "N/A" (the
   general rule on instructions page 17) or stay blank? *Current behavior:* blank, except the
   A-Number, which prints "N/A" because the instructions say so explicitly (page 18).
6. **AcroForm-only PDF.** The official PDF has two layers (Adobe XFA and AcroForm). The
   software fills the AcroForm layer, removes the XFA layer and Adobe's usage-rights
   signature (which any change invalidates), and leaves the barcodes as they are (they
   contain only the form number, edition and page). Does USCIS accept a copy produced this
   way? A web search found no USCIS statement either way.
7. **Answers that always go to an attorney** (principle 7). Is the list complete?
8. **Reference sources.** Which USCIS Policy Manual chapters, if any, should be added to the
   reference chat?

---

## Known Limitations

- **One form, one edition.** Only Form I-765, edition 08/21/25 (OMB expiry 08/31/2027). The
  product owner confirmed it on the USCIS form page on 2026-10-17; uscis.gov blocks automated
  requests, so the software cannot check it itself. A new edition requires a new field list,
  field map and interview data.
- **Not tested with the live AI model.** The advice classifier and the reference chat are
  tested with scripted model responses. The evaluation against the real model
  (`scripts/eval_advice_classifier.py`) has not been run yet; it needs an API key and costs
  money. Without an API key the service still works: plain answers are recorded, the user
  types English translations, uncertain messages are not recorded, and the chat says it is
  unavailable.
- **Reference corpus.** Only the I-765 instructions (693 sentences, keyword search). The USCIS
  Policy Manual is not included.
- **Translations of the interface.** The Russian and Ukrainian texts were written with AI
  assistance and need review by native speakers.
- **Access control.** Two shared secret tokens, one per role (applicant, attorney), not
  personal accounts. A token identifies a role, not a person; an applicant reaches a case
  with the token plus a random case id. Real accounts are needed before production.
- **Deployment.** No built-in HTTPS and no rate limiting: run it behind a TLS proxy that
  adds them. The demo stores keys in a local SQLite file; production should use a managed
  key service. The database layer is written for SQLAlchemy and should work with Postgres,
  but only SQLite is tested.
- **Attorney view.** The case summary is shown as Markdown text, not formatted.
- **Out of scope for this version:** other forms, document photo recognition, a Telegram bot,
  several organizations in one installation.

---

## Architecture

```
web page ── HTTP API (role token) ──┬─ interview ── guard ── AI model (labels, translations)
                                    ├─ reference chat ── search ── AI model (citations)
                                    ├─ validation (flags)
                                    ├─ attorney mode ── PDF filler
                                    └─ encrypted case store + separate key store
```

| Module (`src/uscis_assistant/`) | Responsibility |
|---|---|
| `config.py` | Settings from `.env`; one model for all users, other models rejected at startup |
| `logging_utils.py` | Log formatter that redacts personal identifiers |
| `forms/registry.py` | Active edition, source URL, SHA-256 of the official PDFs (verified on use) |
| `forms/i765/schema.py`, `forms/field_map.py` | I-765 data model and its link to each of the 154 fillable PDF fields, matched by the field's own tooltip (Part and item), not by its internal name |
| `forms/i765/filler.py` | Fills the PDF, then reads it back and compares every field |
| `validation/` | Formal checks that only raise flags, each with its official source |
| `interview/` | Question flow, answer parsing (dates, names, addresses), RU/UK/EN texts, advice guard |
| `llm/` | Narrow AI tasks through the Anthropic API: label a message, propose a translation, select cited passages |
| `reference/` | Reference chat: sentence corpus from the instructions, keyword (BM25) search, citations |
| `lawyer/` | Attorney mode: case summary in English, audit log, attorney data and decisions, draft PDF |
| `storage/` | Encrypted case store, key store, audit log, deletion |
| `api/`, `web/static/` | FastAPI endpoints and the web page |

Data files (`forms/i765/`): the official PDFs (`source/`), the edition registry
(`editions.json`), the list of PDF fields (`fields/`), the field map (`mappings/`), and the
interview questions (`interview/`). Each is tied to the edition.

HTTP API. Either role: `GET /api/health`, `GET /api/me`, `POST /api/cases`,
`GET /api/cases/{id}/interview`, `GET /api/cases/{id}/flags`, `DELETE /api/cases/{id}`,
`POST /api/chat`. Applicant role only: `POST /api/cases/{id}/interview` (answering). Attorney
role only: `GET /api/lawyer/cases`, `GET /api/lawyer/cases/{id}/review`,
`POST .../attorney-data`, `POST .../decision`, `POST .../fill`, `GET .../documents/{doc}`.
The role comes only from the `Authorization: Bearer` token.

Project documents: [`docs/STATUS.md`](docs/STATUS.md) (state and open items),
[`docs/DECISIONS.md`](docs/DECISIONS.md) (decisions and reasons),
[`docs/LOG.md`](docs/LOG.md) (history), [`AGENTS.md`](AGENTS.md) (rules for AI coding agents).

---

## Getting Started

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env      # then fill in MASTER_KEY, APPLICANT_TOKEN, LAWYER_TOKEN, ANTHROPIC_API_KEY
uv sync                   # install dependencies
uv run pytest             # run tests
uv run ruff check .       # lint
```

Generate each secret with `uv run python scripts/generate_master_key.py`. The app refuses to
start if a token is missing, shorter than 24 characters, or if both tokens are the same.
`ANTHROPIC_API_KEY` is optional; `LLM_MODEL` selects `claude-sonnet-5-5` (default) or
`claude-opus-5-5`.

Start the server:

```bash
uv run uvicorn --factory uscis_assistant.api.app:app_factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and enter the applicant token (interview and reference chat) or
the lawyer token (also opens the attorney tab). This is a demo setup: serve it only behind
HTTPS.

Other scripts: `scripts/list_pdf_fields.py` (regenerate the PDF field list),
`scripts/eval_advice_classifier.py` (live test of the advice classifier; calls the paid API).
