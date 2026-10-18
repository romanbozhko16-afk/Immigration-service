# Project status

*Last updated: 2026-10-18, after step 9 (awaiting owner approval).*

## Where we stopped

- **Step 0 is done and pushed** (skeleton, model config, PII-safe logging).
- **Step 1 is done and approved** (owner confirmed edition 08/21/25 on 2026-10-17: two
  downloads from uscis.gov were byte-identical and the owner found no newer edition).
- **Step 2 is done and approved.** Schema `src/uscis_assistant/forms/i765/schema.py`, field
  map `forms/i765/mappings/08-21-25.json`.
- **Step 3 is done and approved** (validation in `src/uscis_assistant/validation/`).
- **Step 4 is done and approved** (encrypted storage in `src/uscis_assistant/storage/`).
- **Step 5 is done and approved** (PDF filling, `forms/i765/filler.py`).
- **Step 6 is done and approved** (interview, `src/uscis_assistant/interview/`).
- **Step 7 is done and approved** (model layer and advice guard). The live classifier
  eval (`scripts/eval_advice_classifier.py`) has NOT been run yet: no API key in the
  sandbox; it costs money; run it with the owner's key and approval.
- **Step 8 is done and approved** (reference chat, `src/uscis_assistant/reference/`).
- **Step 9 is done and awaiting the owner's approval** (1000 tests pass): attorney mode in
  `src/uscis_assistant/lawyer/` (`review.py`, `render.py`, `session.py`).
- The owner works from a phone and may continue in Codex or Claude Code. This file is the
  handoff: read it, then continue with "Next action".

## Next action

1. Wait for the owner to approve step 9.
2. Then step 10: FastAPI + minimal web page with the disclaimer (recommended: Sonnet 5.5,
   effort medium). Endpoints: create case, interview (prompt/submit), reference chat, lawyer
   summary/audit/decision/fill/download, delete case. Two roles; authentication is needed
   (decide with the owner: simplest for the MVP is one API token per role from `.env`).
   The API layer must set the actor role (the data layer only checks `ActorRole.LAWYER`) and
   must never log request bodies. Serve the PDF only to the lawyer role.
3. Step 11: final README for lawyers.

## Step 9 summary

- `LawyerSession(store, case_id, actor=ActorRole.LAWYER)`: refuses any other role
  (`PermissionError`). Methods: `review(today)`, `summary(today)` (Markdown, English),
  `audit_log(today)`, `enter_attorney_data(path, value)`, `record_decision(decision, note)`,
  `fill_pdf()` (stores the encrypted draft PDF through `CaseStore`).
- The summary: open points first (interpreter/preparer decision, unconfirmed translations,
  unfinished interview, machine translations to verify, declined advice requests), then
  flags grouped by severity with their official source, the declined requests with time and
  the person's words, and the answers table: item, question, applicant's original + language,
  English value, method (same / user / machine), who entered it. It states that it contains
  no legal analysis. It contains NO model-written text.
- Attorney-entered items (the ones the interview never asks): `statement.statement`,
  `statement.interpreter_language`, `statement.prepared_by_preparer`,
  `statement.preparer_name`, `interpreter.*`, `preparer.*`, `attorney.*`, `additional_info[*]`.
  Anything else is rejected. Partial data (for example an interpreter without an address)
  keeps the form from being built and the summary names the gap.
- Decision: `record_decision("complete" | "not_required", note)`, stored in the audit log
  (note encrypted). The latest decision wins. Without a decision `fill_pdf()` leaves the
  reserved items blank (`attorney_decisions_made=False`); with one, they are filled.
- Audit log rendering: sequence, UTC time, role, event, path, details (originals included);
  the summary says if the hash chain shows tampering.
- Mutation check: filling without a decision, missing role check, hidden declined
  requests, hidden tampering, hidden machine translations each fail a test.
- Known gap: identity and authentication of the attorney are not part of this layer (step 10).

## Step 8 summary

- Corpus: the I-765 instructions of the active edition, split into 693 sentences with page
  numbers (page headers removed; "Part 6." / "Item Number 16." do not end a sentence).
  The USCIS Policy Manual is NOT in the corpus yet: uscis.gov blocks downloads from the
  sandbox; the owner can upload chosen chapters (choose them with the lawyer).
- Search: BM25 over 3-sentence windows, hyphenated terms kept ("i-94", "a-number").
- Pipeline: advice patterns (no model) -> model label + English keyword query (structured
  output; personal advice -> decline, off topic -> fixed text) -> BM25 -> Citations API on
  the candidate sentences as a custom-content document -> only cited sentences are shown,
  verbatim, with page and link; the model's prose is discarded. "NO_ANSWER", no citation,
  an out-of-range or mismatching citation -> "I don't know, ask an attorney". Any model
  failure -> "unavailable", never an invented answer.
- Every answer carries the label in the user's language plus the exact English label
  required by AGENTS rule 6.
- Mutation check: showing model prose, trusting cited text, ignoring NO_ANSWER, removing
  the pattern pre-check each fail a test.
- Not measured on the live model yet (same reason as step 7).

## Step 7 summary

- The model NEVER writes text shown to the user. It returns a label (answer /
  advice_request / form_question / unclear) or a short Latin rendering of an answer that the
  user must confirm. All user-facing sentences are fixed RU/UK/EN templates.
- Guard (`interview/guard.py`), before anything is recorded:
  1. Obvious advice requests (RU/UK/EN patterns) -> fixed refusal + offer of a partner
     attorney; no model call; an encrypted `advice_request_declined` audit event keeps the
     text for the lawyer.
  2. "?" in the text, a parse failure, a category that does not look like a code, or long
     free text -> model label first. Without a model (or on any model failure) such
     messages are never stored as answers.
  3. Plain answers are recorded without a model call, so names, numbers and addresses do not
     reach the model (tested on a full interview).
- Patterns were narrowed after the test set caught false refusals: "Chance" and "Advise"
  are real names and must be accepted.
- Translation: Cyrillic answers in place/country/status fields get a model proposal
  (`translation_method="proposed"`), the user confirms ("machine") or types their own
  ("user"). Without a model the user types the English version. Unconfirmed answers block
  the application. Proposals that are not short Latin text, are much longer than the
  answer, or read like advice are discarded (protects against injected instructions).
- Client (`llm/client.py`): model and effort from settings, JSON schema via
  `output_config.format`, stop_reason checked (refusal / max_tokens -> unavailable), no
  logging of content. Server-side refusal fallbacks deliberately NOT enabled (they would
  route to other models; see DECISIONS).
- `evals/advice_phrases.json`: 34 advice requests (obvious and subtle), 5 form questions,
  20 plain answers. Tests: every obvious request is declined by patterns, no advice request
  can be recorded unchecked on any question, no plain answer is ever declined.
- Mutation check: 6 weakenings (proposal checks, "?" routing, audit of declines, skipping
  classification, ignoring stop_reason, adding fallbacks) each fail a test.

## Step 6 summary

- Question bank (81 questions, data) with conditions: `equals`, `not_equals`, `category_in`
  (category compared case/space-insensitively). Repeating groups are expanded in the data:
  up to 6 other names, up to 4 citizenships (more than the form holds go to Part 6).
- Not asked (attorney decision / attorney-only / automatic): Part 3 items 1-2, Parts 4-5,
  the G-28 box, Part 6. A test checks that no attorney-decision path is asked.
- Help ("?") shows the VERBATIM English instruction or tooltip text plus page and link;
  never a paraphrase. A test checks every quote against the PDF, on the stated page.
- Parsing (no model): dates only in the announced format (RU/UK DD.MM.YYYY, EN MM/DD/YYYY)
  or ISO; ambiguous input is rejected, never guessed. Names and U.S. addresses must be in
  Latin letters. Places of birth, citizenship, statuses may be typed in Cyrillic: the answer
  is stored with `translation_method="pending"`, English None, and blocks the application
  until translated (step 7).
- "No A-Number" is recorded as "N/A" (instructions p.18). Other "(if any)" answers are left
  empty when the user has none.
- The category is the user's text exactly, or "I don't know" -> None -> attorney review.
  The bot offers no list of categories.
- Answers go through `CaseStore` (original, language, English, method), so the audit trail
  has every version. Answers to questions that no longer apply are ignored when building.
- `InterviewSession`: `current()`, `prompt()`, `submit(raw)` ("?" = help), `answer()` to
  change an earlier answer, `build()` -> `BuildResult(application, missing,
  pending_translation)`.
- RU and UK texts were written by the AI assistant: a native speaker should review them
  before real users see them.
- Mutation check: 5 corruptions of the bank (changed quote, wrong page, removed condition,
  advice wording, asking an attorney-decision item) all fail tests; the removed-condition
  case needed a new test (same address -> no physical address questions).

## Step 5 summary

- `fill_i765(app, attorney_decisions_made=False)` returns `FillResult(pdf, report)`. It
  verifies the pinned files and the edition, fills the AcroForm fields from the field map,
  removes `/XFA` and the Adobe usage-rights signature (`/Perms`, invalid after any change),
  sets NeedAppearances, then READS THE PDF BACK and compares every mapped field; a mismatch
  raises `FillVerificationError`.
- Literal filling: never invents answers. "N/A" is printed only when the user's answer is
  "N/A" (the validator accepts it for the A-Number, instructions p.18). The interview
  (step 6) must record "N/A" as an answer where the user has none.
- A-Number and SSN go into the form as digits only (the boxes print "A-" and are comb
  boxes); malformed values are written as given, never repaired, and are flagged by the
  validator.
- Category `(c)(17)(iii)` is split into 3 boxes (parentheses are printed on the form); a
  badly shaped category is left empty and reported.
- Entries that do not fit move to Part 6 (4th+ other name, 3rd+ citizenship), after the
  user's own Part 6 entries; more than 5 Part 6 entries: `report.not_placed` > 0, a
  separate sheet is needed.
- Items with `attorney_decision` (Part 3 items 1-2, Parts 4-5) are skipped unless the caller
  passes `attorney_decisions_made=True`. The report lists them.
- The report contains no personal data (safe to log). The filled PDF DOES contain personal
  data: never write it to a plain file or log it; if it is kept, store it with
  `CaseStore.add_document`.
- Barcodes (7, PDF417) are left untouched. They contain only `I-765|08/21/25|<page>`, not
  the applicant's data (read from the PDF). OPEN QUESTION for a lawyer: whether USCIS
  requires the XFA-generated form or accepts an AcroForm-only filled copy. A web search found
  no USCIS statement either way, so this is unverified.
- Tests: hand-written expected values for ~65 PDF fields, rendered pages checked visually
  (Ste./Apt. boxes in Parts 4-5, category boxes, signatures empty). Corrupting the map in 4
  ways fails tests.

## Step 4 summary

- Envelope encryption, AES-256-GCM: a random key per case, wrapped by `MASTER_KEY` (.env).
  Each ciphertext is bound to case + field (associated data), so swapped or moved
  ciphertext fails to decrypt (tested).
- Per-case keys live in a SEPARATE database (`KEYSTORE_URL`), not with the case data. This is
  what makes deletion by key destruction meaningful for backups: keep the key store's
  backups on a separate, shorter retention. Production: replace `KeyStore` with a KMS.
- Plain columns hold no personal data (ids, timestamps, status, event types, question
  paths). Answers (original + language + English + translation method), document contents
  and file names, and audit details are encrypted. Tests scan the raw database files.
- Audit log: append-only (ORM blocks update/delete), hash-chained, with the chain head kept
  on the case row so removal of the newest events is detected. Limitation: someone with
  full write access to the database can rewrite chain and head together; exporting the
  head elsewhere is a production task.
- Deletion on request: key destroyed first, then answers/documents/audit rows deleted; a
  tombstone event without personal data remains. SQLite `secure_delete` overwrites freed
  pages (tested by scanning files).
- Mutation check: disabling secure_delete, encryption, the chain-head check, key
  destruction, or field binding each fails a test.

## Notes for later steps

- Step 5 (PDF filling): the instructions say "If a question does not apply ... type or print
  N/A unless otherwise directed" (page 17) and "If you do not have an A-Number, type or print
  N/A" (page 18). Decide per field with the owner which empty answers print "N/A"; never
  invent answers. Dates print as mm/dd/yyyy (page 19). The A-Number prints digits only; the
  validator accepts an optional leading "A" (the instructions say it begins with an A).
- Step 5: the category is split into 3 boxes, e.g. (c)(17)(iii) -> c | 17 | iii.
- Step 6 (interview): validation messages are English; user-facing texts in RU/UK/EN are
  needed for each flag code.
- Possible future check (not done, needs owner decision): whether the entered category code
  appears in the instructions' list. It is a formal check, but the message must not imply
  a judgment about eligibility.

## Step 3 summary

- `Flag(code, item, path, message, source)`; severity is derived from the code: blocking
  (missing_required), check (inconsistent, format), attorney (requires_attorney_review,
  requires_attorney_decision), info (overflow_to_part_6, notice).
- Every rule cites the instructions page or the PDF help text it comes from. Rules never
  change data (tested).
- Always raised: requires_attorney_decision for the interpreter/preparer question.
- Attorney review (owner chose "the safest option" on 2026-10-17): no category entered;
  "Yes" to P2.30 or P2.31.B (arrests/convictions); P3.6 ABC settlement selected.
- An expired passport is NOT an error. At the owner's request (2026-10-17) it raises a
  `notice` (severity info) that quotes the instructions, page 19: "enter the passport or
  travel document information ... even if the passport or travel document is currently
  expired." A test checks that the quote matches the instructions PDF word for word.
- Category shape is checked against all 57 codes found in the instructions (test).
- Mutation check: switching off any one of the 9 rules makes tests fail.

## Step 1 findings

- Both official files in `forms/i765/source/` carry edition **08/21/25** (printed on every
  page; OMB expires 08/31/2027). The string `09/15/26` appears in neither file. The form PDF
  was created 2025-08-26, the instructions PDF 2026-05-12. SHA-256 values are pinned in
  `forms/i765/editions.json`; a test checks them.
- The form is a hybrid XFA + AcroForm PDF (Adobe Designer 6.5), encrypted with the empty user
  password (needs the `cryptography` package; pypdf reads it fine). 161 widgets: 119 text,
  38 checkbox, 4 choice lists; 7 of them are `PDF417BarCode` fields that must never be
  filled, so 154 are fillable. Full list: `forms/i765/fields/08-21-25.md` (+ `.json`).
- To fill with pypdf, fill the AcroForm fields and remove the `/XFA` entry (otherwise
  XFA-aware viewers show the XFA data instead). Step 5 must verify this by round-trip.

### Traps in the PDF (read before mapping)

- **Field names do not match printed item numbers.** Example: `Line9_Checkbox` is item 10
  (Sex), `Line19_DOB` is item 16, `Line17a/b_CountryOfBirth` are item 14 (citizenship),
  `Line19_Checkbox` is item 12. The tooltip always carries the true Part and item number.
- **Checkbox on-values are not Yes/No.** Sex: `/N` = Female, `/Y` = Male. Each checkbox has
  its own on-value (e.g. `/1 /2 /3`, `/A /B /C`, `/Single /Married`). Never infer from `/Y /N`.
- **Interpreter vs Preparer are offset by one Part in the names.** `Pt5Line3*` are the
  INTERPRETER address fields (tooltip: Part 4); `Pt6Line3*` are the PREPARER address fields
  (tooltip: Part 5). Both parts are "requires attorney decision" flags (owner's decision), so
  a wrong mapping here would mislabel who prepared the form.
- Eligibility category (item 27) is split over three boxes of 4 + 3 + 3 characters
  (`section_1/2/3`). Items 28-31 depend on the category the USER entered. The bot never picks
  the category.
- Part 6 (page 7) repeats name and A-Number as "pre-populated" fields; the XFA fills them
  automatically, plain AcroForm filling will not, so we must fill them ourselves.
- Several tooltips contain stray spaces ("I - 7 65"); tests normalize tooltips to lowercase
  alphanumerics before matching.
- Found in step 2: in Parts 4-5 the Apt/Ste/Flr on-values do not match the printed labels
  (the box printed "Apt." has on-value `/ FLR `). Tooltips match the printed labels. The map
  follows the printed label; a test checks it by widget x-position.
- Found in step 2: other names item 3 is `Line3*[1]` and item 4 is `Line3*[0]`; Part 6
  item 3.D is `Pt6Line4d_AdditionalInfo[1]`; `Pt5Line5_PreparerFaxNumber` is the preparer's
  MOBILE number; `Pt4Line6_Checkbox` is Part 3 item 6 (ABC settlement).
- Signatures (and their dates) are never filled: the form says it cannot be signed
  electronically. The applicant signs and dates in ink.

## Blockers and open questions

- **uscis.gov is not reachable from the cloud sandbox.** The network allowlist includes the
  host, but the site (Akamai) answers `403 Access Denied` to automated requests from
  datacenter IPs. Do not try to bypass it. Workflow: the owner downloads files in a normal
  browser and uploads them (done for the form and instructions on 2026-10-17).
- **Edition: resolved for now.** Active edition 08/21/25, confirmed by the owner on
  2026-10-17 (see `DECISIONS.md`). If USCIS publishes or starts accepting another edition,
  add it to `forms/i765/editions.json`, generate its field list, and write a new map.
- **Lawyer questions (owner will ask their attorney):**
  - Whether "(if any)" questions the person has no answer for should print "N/A" (the
    instructions' general rule, p.17) or stay empty (current behavior, except the A-Number,
    where the instructions say "N/A" explicitly).
  - Whether USCIS accepts a copy filled as plain AcroForm (XFA removed, usage-rights signature
    removed, barcodes unchanged) or requires a form filled in Adobe's XFA layer.
  - Whether/how to complete Interpreter and Preparer sections when the interview is done by
    software in another language (we flag them; we do not decide).
  - Review of the README "Legal Principles" section by a U.S.-licensed immigration attorney
    before external use.
  - Whether the paid B2C service fits the "clerical assistance" exception of 8 CFR 1.2.
- **Repo is public.** No secrets in it, but code and legal principles are visible. Owner may
  switch it to private (Settings → General → Danger Zone).

## Plan (11 steps)

Recommended model / effort per step is the owner's request; it is an engineering estimate,
not a rule from any documentation.

| # | Step | Model | Effort | State |
|---|---|---|---|---|
| 0 | Skeleton, config, PII-safe logging | — | — | done |
| 1 | Fetch PDF + instructions, fix edition, list PDF fields (STOP for owner) | Sonnet 5.5 | medium | done |
| 2 | Pydantic schema + mapping to PDF fields | Opus 5.5 | high | done |
| 3 | Validation + flags | Opus 5.5 | high | done |
| 4 | Storage: field encryption, audit log, case deletion | Opus 5.5 | high | done |
| 5 | PDF filling + round-trip test | Sonnet 5.5 | high | done |
| 6 | Interview engine (no LLM decides questions), RU/UK/EN texts | Opus 5.5 | high | done |
| 7 | LLM layer: parse answers, translate, advice-request refusal, adversarial test phrases | Opus 5.5 | xhigh | done |
| 8 | RAG over official docs + Citations API; reference chat | Opus 5.5 | high | done |
| 9 | Lawyer mode: English summary, flags, audit log export | Sonnet 5.5 | high | done, awaiting owner approval |
| 10 | FastAPI + minimal web page with disclaimer | Sonnet 5.5 | medium | todo |
| 11 | Final README for lawyers | Opus 5.5 | high | todo |

Notes on design (details in `docs/DECISIONS.md`):
- Interview order is code/data, not the model. The model only does narrow tasks.
- RAG: keyword search (BM25), no embeddings (Anthropic has no embeddings API); exact
  quotes come from the Citations API.
- Names and dates are entered in Latin as in the passport/I-94 and are not translated.
- Telegram bot, vision-based document extraction, multi-tenant, and a lawyer-only analytic
  chat are out of scope for v1.
