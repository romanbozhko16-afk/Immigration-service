# USCIS Form Assistant (MVP)

> **This service is not a law firm and does not provide legal advice.** It helps people
> enter their own information into official USCIS forms. Using it does not create an
> attorney-client relationship.

An AI-assisted intake tool for **Form I-765, Application for Employment Authorization**.
It interviews the applicant in Russian, Ukrainian, or English, records the answers,
checks them for formal errors, and fills in the official PDF for review.

Audiences:

- **Law firms (B2B):** a client intake tool. A licensed attorney reviews and is responsible
  for every case.
- **Individuals (B2C):** self-preparation of the form, with optional paid review by a
  partner attorney.

**Status:** under construction. Steps 0-8 of 11 are done (skeleton; form edition registry and PDF field list; data schema and PDF field map; validation; encrypted storage; PDF filling; interview; AI safeguards and translation; reference chat).

---

## Legal Principles of the Product

*Draft. To be reviewed by a U.S.-licensed immigration attorney before external use.*

The product is designed so that it does not engage in the practice of law. These principles
are enforced in code where possible, not only in model instructions.

### 1. No legal advice

The system does not:

- assess eligibility or the chances of approval;
- choose a case type, an eligibility category, or a filing strategy;
- tell a user that a particular option "applies to them" or that they "should" file anything.

### 2. What the system does

- Asks the questions that the form asks, one at a time, in plain language.
- Explains what a form question means, **only** by quoting the official USCIS form
  instructions or the USCIS Policy Manual, with a link to the source.
- Records the user's answers verbatim, together with an English translation for the form.
- Checks for formal errors (missing required fields, date formats, A-Number format,
  internally inconsistent answers) and **flags** them. It never silently corrects them.
- Fills in the official PDF edition currently accepted by USCIS.

### 3. Requests for advice are declined

If a user asks for advice ("Am I eligible?", "What should I file?", "What are my chances?"),
the system politely declines, explains why, and offers review by a partner attorney.

The AI model never writes the text the user sees. It only classifies a message (an answer,
a request for advice, a general question about the form) or proposes an English rendering
of an answer, which the user must confirm. Every refusal and every other message is fixed,
reviewed text. Obvious requests for advice are recognized without the AI model at all. A
record of each declined request is kept, encrypted, for the reviewing attorney.

### 4. Eligibility category comes from the user

The system never determines the eligibility category. The user enters it from their own
documents. If the user does not know it, the case is marked
**"Requires attorney review"**.

### 5. Reference chat: official sources only

The reference chat answers general questions about the form and the process (for example,
"What does category (c)(8) mean?" or "Which documents do the instructions list?"):

- Every answer cites an official USCIS source (form instructions or Policy Manual) with a link.
- If the sources do not answer the question, the system says so and refers the user to an
  attorney. It does not guess.
- Questions about the user's personal situation (eligibility, chances, what to file) are
  declined as in principle 3.
- Every answer carries the label: *"Reference information from official USCIS sources.
  Not legal advice."*
- The answer consists only of verbatim sentences from the official instructions, each with
  its page number and a link. The AI model selects the passages through citations; its own
  wording is never shown. If no passage answers the question, the user is told so and is
  referred to an attorney.
- Current source: the Form I-765 instructions of the edition in use. Additional official
  sources (USCIS Policy Manual chapters) will be added after attorney review.

### 6. Sections reserved for an attorney's decision

Whether and how to complete the **Interpreter** and **Preparer** sections of Form I-765 when
the interview is conducted by this software in a language other than English is a legal
question. The system does not decide it: these fields are always flagged
**"Requires attorney decision"**.

### 7. Same quality for every user

Free and paid users are served by the same AI model with the same settings. Paid review adds
a human attorney; it does not unlock a "better" AI.

---

## Data Protection

- All personal data (answers in the original language and in English, documents and their
  file names, audit details) is encrypted with AES-256-GCM using a separate key for each
  case. Case keys are themselves encrypted with a master key and kept in a separate key
  store, not next to the data.
- Every change to a case is recorded in an append-only audit log with a UTC timestamp and
  the role of the person who made it (applicant, lawyer, system); the log is hash-chained
  so alterations are detectable.
- No personal data in logs. Code never logs answers, documents, prompts, or model output;
  an additional redaction filter removes identifiers (A-Numbers, SSNs, document numbers,
  receipt numbers, phone numbers, emails) that slip into log lines by mistake.
- A user can have their case deleted on request: the case key is destroyed first, so every
  copy of the encrypted data becomes unreadable, then the records are removed. Only a
  record that a deletion took place remains, with no personal data.
- API keys and secrets live only in `.env`, which is never committed.
- Development and tests use fictitious data only.
- Only messages that need it are sent to the Anthropic API: answers typed in Cyrillic that
  need an English version, and messages that may be questions rather than answers. Plain
  answers (names, numbers, addresses, dates) are not sent. This must be disclosed in the
  privacy policy. Claude Fable 5.1 is not used because it requires 30-day data retention.
- Every machine translation is shown to the applicant and confirmed before it can be used,
  and the attorney sees which answers were machine-translated.

---

## Architecture

Planned modules (implemented step by step):

| Module | Responsibility |
|---|---|
| `forms/i765/` | Edition registry (edition date, source URL, SHA-256), official PDF, field map |
| `schema/` | Pydantic models; every field is linked to a PDF field and an instruction item |
| `interview/` | Deterministic question flow (data-driven, RU/UK/EN). The AI model does not decide what to ask |
| `llm/` | Narrow model tasks: parse an answer, translate, detect advice requests, explain with citations |
| `rag/` | Retrieval over official USCIS documents with citations |
| `validation/` | Rules that produce flags; nothing is corrected silently |
| `pdf/` | Reading and filling the official PDF |
| `storage/` | Database, field-level encryption, append-only audit log, deletion |
| `api/` | FastAPI endpoints and a minimal web page |

Implemented so far:

- `config.py`: settings from `.env`. One model for all users: `claude-sonnet-5-5` by default,
  switchable to `claude-opus-5-5`; other models are rejected at startup.
- `logging_utils.py`: log formatter that redacts personal identifiers.
- `forms/registry.py`: pins the active form edition and verifies SHA-256 of the official PDFs.
- `forms/i765/schema.py` + `forms/i765/mappings/08-21-25.json`: the I-765 data schema and its
  link to every PDF field, verified against the official PDF by tests. Signatures are never
  filled; interpreter and preparer items are marked for an attorney's decision.
- `forms/i765/filler.py`: fills the official PDF from the collected answers, then reads it
  back and compares every field. It writes only what the user answered, never leaves a
  signature filled, and skips items reserved for an attorney's decision until one decides.
- `interview/`: the interview in Russian, Ukrainian and English. Questions, their order and
  conditions are data, not decisions of the AI model. Help shows the verbatim official
  USCIS text with page and link. The eligibility category is only ever the applicant's
  own answer; "I don't know" sends the case to an attorney.
- `llm/` and `interview/guard.py`: the AI layer and the advice guard described in the
  Legal Principles above.
- `reference/`: the reference chat (search over the official instructions, citations).
- `storage/`: encrypted case store, separate key store, audit log, deletion on request.
- `validation/`: formal checks that only raise flags (missing, inconsistent, format,
  attorney review, attorney decision, Part 6 overflow). Each rule cites the official
  instructions or the form's own help text; no rule judges eligibility.

---

## Getting Started

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env      # then fill in ANTHROPIC_API_KEY
uv sync                   # install dependencies
uv run pytest             # run tests
uv run ruff check .       # lint
```
