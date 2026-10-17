# Project status

*Last updated: 2026-10-17, after step 3 (awaiting owner approval).*

## Where we stopped

- **Step 0 is done and pushed** (skeleton, model config, PII-safe logging).
- **Step 1 is done and approved** (owner confirmed edition 08/21/25 on 2026-10-17: two
  downloads from uscis.gov were byte-identical and the owner found no newer edition).
- **Step 2 is done and approved.** Schema `src/uscis_assistant/forms/i765/schema.py`, field
  map `forms/i765/mappings/08-21-25.json`.
- **Step 3 is done and awaiting the owner's approval** (383 tests pass): validation in
  `src/uscis_assistant/validation/` (`flags.py`, `i765.py`).
- The owner works from a phone and may continue in Codex or Claude Code. This file is the
  handoff: read it, then continue with "Next action".

## Next action

1. Wait for the owner to approve step 3.
2. Then step 4: storage (recommended: Opus 5.5, effort high): SQLAlchemy models, field-level
   encryption with a per-case key (deleting the key = crypto-shredding), append-only audit
   log with timestamps (original answer + English translation), case deletion on request.
   SQLite now, Postgres-ready. No personal data in logs.

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
  requires_attorney_decision), info (overflow_to_part_6).
- Every rule cites the instructions page or the PDF help text it comes from. Rules never
  change data (tested).
- Always raised: requires_attorney_decision for the interpreter/preparer question.
- Attorney review (owner chose "the safest option" on 2026-10-17): no category entered;
  "Yes" to P2.30 or P2.31.B (arrests/convictions); P3.6 ABC settlement selected.
- Not flagged on purpose: an expired passport (instructions: enter it even if expired).
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
| 3 | Validation + flags | Opus 5.5 | high | done, awaiting owner approval |
| 4 | Storage: field encryption, audit log, case deletion | Opus 5.5 | high | todo |
| 5 | PDF filling + round-trip test | Sonnet 5.5 | high | todo |
| 6 | Interview engine (no LLM decides questions), RU/UK/EN texts | Opus 5.5 | high | todo |
| 7 | LLM layer: parse answers, translate, advice-request refusal, adversarial test phrases | Opus 5.5 | xhigh | todo |
| 8 | RAG over official docs + Citations API; reference chat | Opus 5.5 | high | todo |
| 9 | Lawyer mode: English summary, flags, audit log export | Sonnet 5.5 | high | todo |
| 10 | FastAPI + minimal web page with disclaimer | Sonnet 5.5 | medium | todo |
| 11 | Final README for lawyers | Opus 5.5 | high | todo |

Notes on design (details in `docs/DECISIONS.md`):
- Interview order is code/data, not the model. The model only does narrow tasks.
- RAG: keyword search (BM25), no embeddings (Anthropic has no embeddings API); exact
  quotes come from the Citations API.
- Names and dates are entered in Latin as in the passport/I-94 and are not translated.
- Telegram bot, vision-based document extraction, multi-tenant, and a lawyer-only analytic
  chat are out of scope for v1.
