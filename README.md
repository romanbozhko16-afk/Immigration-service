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

**Status:** under construction. Step 0 of 11 (project skeleton) is done.

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

- Sensitive fields (passport data, A-Number, personal history) are encrypted in the database.
- No personal data in logs. Code never logs answers, documents, prompts, or model output;
  an additional redaction filter removes identifiers (A-Numbers, SSNs, document numbers,
  receipt numbers, phone numbers, emails) that slip into log lines by mistake.
- A user can have their case deleted on request.
- API keys and secrets live only in `.env`, which is never committed.
- Development and tests use fictitious data only.
- Answers are sent to the Anthropic API for processing; this must be disclosed in the
  privacy policy. Claude Fable 5.1 is not used because it requires 30-day data retention.

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

---

## Getting Started

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env      # then fill in ANTHROPIC_API_KEY
uv sync                   # install dependencies
uv run pytest             # run tests
uv run ruff check .       # lint
```
