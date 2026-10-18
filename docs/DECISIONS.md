# Decisions

Format: date — decision — why. Newest last. Owner = the product owner.

- **2026-10-17 — One form only: I-765.** MVP scope.
- **2026-10-17 — Interview flow is deterministic (data-driven), not chosen by the model.**
  Reduces UPL risk technically: the model cannot decide what to ask or which category applies.
- **2026-10-17 — Single global model for all users; default `claude-sonnet-5-5`, switchable to
  `claude-opus-5-5` via `.env`.** Owner requirement: free and paid accuracy must be identical.
  `claude-fable-5-1` excluded because it requires 30-day data retention (unacceptable for
  passport data). Config rejects other model IDs; a test checks there are no per-tier settings.
- **2026-10-17 — Reference chat = official sources only, with citations (option A).** Owner
  asked for a chat that answers anything, including "what are my chances". Research showed a
  disclaimer does not cure UPL (it depends on what the service does; 8 CFR 1.2 treats study of
  facts + law + advice as "practice"; FTC v. DoNotPay final order Jan 2025; NY S7263 pending).
  Owner chose "the safest option": general questions answered from official sources with
  citations; personal-situation questions declined with an offer of lawyer review.
  Not done: a lawyer-only analytic chat (option C) and a "chances" chat (option B).
- **2026-10-17 — Interpreter / Preparer sections are always flagged "requires attorney
  decision".** Owner agreed; owner will ask their attorney.
- **2026-10-17 — Edition handling: registry with one active edition, mechanism to change it
  later, no support for older editions.** Which edition is active is unresolved (see
  `STATUS.md`, Blockers).
- **2026-10-17 — Interface: API + minimal web page; Telegram bot in v2.** Documents: encrypted
  storage only in v1; vision extraction in v2. One organization, two roles (applicant, lawyer).
- **2026-10-17 — Storage plan: SQLite for the demo, Postgres-ready; per-case encryption keys
  (crypto-shredding) so deleting a key makes a case unreadable even in backups.**
  *Corrected 2026-10-17 (step 4): this holds only if the keys are stored apart from the
  data; a backup holding both the wrapped key and the data stays readable while the master
  key exists. Keys are therefore kept in a separate key store (see below).*
- **2026-10-17 — RAG without embeddings (BM25), citations via the Anthropic Citations API.**
  Small corpus (form instructions + Policy Manual chapters); simpler to audit.
- **2026-10-17 — Logging: never log answers/documents/prompts/model output; regex redaction
  is only a safety net.** Phone regexes kept narrow so timestamps are not redacted.
- **2026-10-17 — Handoff files: `AGENTS.md` (read automatically by Codex), `CLAUDE.md`
  importing it, and `docs/` for state.** Source: OpenAI Codex docs, "Custom instructions with
  AGENTS.md".
- **2026-10-17 — Active edition set to 08/21/25 provisionally.** It is the edition printed in
  both official files the owner supplied; secondary web sources say USCIS currently accepts it
  after the 2026-09-14 court order. The owner believes 09/15/26 is required, so this stays
  unverified until the owner reads the edition notice on uscis.gov/i-765. Registry flag
  `verified_against_uscis_page` is false until then.
- **2026-10-17 — Map PDF fields by tooltip (Part + item number), never by field name.** Names
  are misleading (see `STATUS.md` traps).
- **2026-10-17 — Official PDFs are committed to the repo** (public government forms) with
  SHA-256 pins checked by a test, so any change to the files is caught.
- **2026-10-17 — Edition 08/21/25 confirmed by the owner** ("nothing newer found, work with
  this; we will add or change later"). Registry `verified_against_uscis_page: true`.
- **2026-10-17 — Signatures and signature dates are never filled.** The form states it cannot
  be signed electronically; dates are written at signing so they are true.
- **2026-10-17 — Part 3 items 1 and 2 are "attorney decision" too**, not only Parts 4-5:
  they say whether an interpreter read the form and whether a preparer prepared it, which is
  the same open legal question.
- **2026-10-17 — Unit checkboxes in Parts 4-5 follow the printed label, not the on-value.**
  What USCIS sees is the ticked box next to the printed word; the on-values there are
  scrambled in the official PDF.
- **2026-10-17 — Schema rejects only wrong shapes; content rules become flags in step 3.**
- **2026-10-17 — Attorney review for "Yes" to P2.30 / P2.31.B and for P3.6 ABC settlement.**
  Owner: "do the safest". Both answers carry legal consequences described in the instructions
  (court dispositions; ABC class membership).
- **2026-10-17 — Validation rules must cite official text**; rules without a source (e.g. ZIP
  or email shape) were left out rather than invented.
- **2026-10-17 — Category-specific checks compare categories case- and space-insensitively**
  only to decide which checks apply; the stored answer is never normalized, and a wrong shape
  gets its own format flag.
- **2026-10-17 — Identifier format problems are "check" flags, not errors.** The PDF help text
  says e.g. "11 digit number" for I-94; a flag asks to compare with the document instead of
  rejecting the answer.
- **2026-10-17 — Expired passport: notice, not error.** Owner's request. The notice quotes the
  instructions verbatim so the user sees why it is acceptable; it never blocks filing.
- **2026-10-17 — Per-case keys in a separate key store (`KEYSTORE_URL`), wrapped by
  `MASTER_KEY`.** Production: a managed KMS; key-store backups get their own, shorter
  retention so deleted cases cannot be restored from them.
- **2026-10-17 — Deletion on request removes the case's audit events too**, leaving one
  tombstone event without personal data. The audit log is otherwise append-only; a person's
  deletion request is the one exception.
- **2026-10-17 — Audit log tamper evidence: hash chain + head on the case row.** Not a
  defense against someone with full database write access; exporting the head is a
  production task.
- **2026-10-17 — Every answer stores `translation_method`** ("same" / "user" / "machine") so
  the lawyer sees which English values came from machine translation.
- **2026-10-17 — The filler is literal.** It never prints "N/A" or any other value the user did
  not give; "N/A" is a recorded answer. This keeps "not answered" distinguishable from "does
  not apply".
- **2026-10-17 — A-Number and SSN are written as digits only.** The form prints "A-" and uses
  per-digit boxes; the stored answer is unchanged.
- **2026-10-17 — Filled copy is AcroForm-only: XFA and the Adobe usage-rights signature are
  removed.** Required for the copy to display consistently; acceptance by USCIS is an open
  question for a lawyer.
- **2026-10-17 — Read-back verification after every fill.** A writer failure raises instead of
  producing a form with a missing or wrong field.
- **2026-10-17 — `attorney_decisions_made` flag (default False)** decides whether Part 3 items
  1-2 and Parts 4-5 are filled; lawyer mode will set it after the attorney decides.
- **2026-10-17 — Help text is the verbatim English official text, not a translation.** A
  translation or paraphrase could change the meaning; the RAG step may later explain in the
  user's language, with citations.
- **2026-10-17 — Dates only in the announced format per language** (RU/UK day-first, EN
  US month-first) or ISO; ambiguous dates are rejected rather than guessed.
- **2026-10-17 — Names and U.S. addresses must be typed in Latin letters** as in documents;
  places, countries and statuses may be typed in Cyrillic and wait for a confirmed
  translation before they can reach the form.
- **2026-10-17 — "No A-Number" is stored as "N/A"** (explicit instruction, p.18); other
  "(if any)" fields stay empty until a lawyer says otherwise.
- **2026-10-17 — The interview never asks attorney-decision items** (Part 3 items 1-2,
  Parts 4-5) or the attorney's G-28 box.
- **2026-10-17 — The model never writes user-facing text.** It returns labels or a short
  English rendering that the user confirms. Refusals and all other messages are fixed
  templates. This makes "the bot gave advice" impossible by construction, not by prompt.
- **2026-10-17 — Obvious advice requests are declined by patterns without a model;** subtle
  ones are labeled by the model; with no model available, a possible question is never
  stored as an answer (fail safe).
- **2026-10-17 — Plain answers are not sent to the model** (data minimization).
- **2026-10-17 — Declined advice requests are kept (encrypted) in the audit log** so the
  lawyer sees what the person asked and that the service declined.
- **2026-10-17 — Server-side refusal fallbacks are NOT enabled.** The claude-api reference
  recommends `fallbacks: "default"` for Sonnet 5.5, but it re-runs a refused request on
  another model chosen by the server. That conflicts with the owner's rules (one configured
  model for everyone; no model that requires 30-day data retention). A refusal is handled
  as "no model answer" and falls back to the safe path. Owner may revisit.
- **2026-10-17 — Translation proposals are validated** (Latin only, short, not longer than
  about twice the answer, no advice wording) before the user sees them.
- **2026-10-18 — Reference chat shows only verbatim cited official sentences.** The model picks
  passages through the Citations API; its own wording is discarded. Explanations in the
  user's language were not added: they would be model-written text about the law (possible
  later, with an attorney's approval).
- **2026-10-18 — Corpus = the I-765 instructions of the active edition only, for now.** The
  USCIS Policy Manual needs a manual upload; chapters to be chosen with the lawyer.
- **2026-10-18 — Any doubt ends in "I don't know, ask an attorney"**: no citation, invalid
  citation, NO_ANSWER, or model failure.
- **2026-10-18 — Attorney mode shows data and flags, never analysis or model text.** The
  summary is assembled from stored answers and validator results only.
- **2026-10-18 — The attorney decides the interpreter/preparer question with
  `complete` / `not_required` plus a note, recorded in the audit log;** the latest decision
  wins. The reserved PDF items are filled only after a decision.
- **2026-10-18 — Only the listed paths can be entered by an attorney** (interpreter,
  preparer, Part 3 items 1-2, G-28 box, Part 6); applicant answers are never overwritten
  through attorney mode.
- **2026-10-18 — The filled PDF from attorney mode is a draft** (`filled_i765_draft`), stored
  encrypted; signatures remain to be made in ink.
- **2026-10-18 — Access control for the MVP: one secret token per role (owner's option A).**
  Tokens identify roles, not people; case ids (128 random bits) act as the applicant's
  capability. Real accounts are required before a public launch.
- **2026-10-18 — Only attorneys can download the filled PDF.** Open product/legal question
  for B2C (see STATUS, lawyer questions).
- **2026-10-18 — The API never exposes OpenAPI/docs pages and never echoes user input in
  errors.**
- **2026-10-18 — The web page ships no inline scripts and never inserts server text as HTML**
  (strict CSP); the disclaimer is shown in all three languages at the top and as a sticky
  strip.
- **2026-10-18 — The README states the Legal Principles as a draft for attorney review** and
  lists only what the code does. Principles that were already enforced but unstated (answers
  that always go to an attorney, signatures never filled, the disclaimer) were added as
  principles 7-9, and each principle is mapped to its mechanism and tests. Open legal
  questions and known limitations are listed in the README, not hidden.
- **2026-10-18 — The README does not quote 8 CFR 1.2.** The regulation's text could not be
  re-checked (ecfr.gov and govinfo.gov are not reachable from the sandbox), so the README
  names the question for the attorney without quoting it.
