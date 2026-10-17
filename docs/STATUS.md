# Project status

*Last updated: 2026-10-17, after step 1 (awaiting owner approval).*

## Where we stopped

- **Step 0 is done and pushed** (skeleton, model config, PII-safe logging).
- **Step 1 is done and awaiting the owner's approval** (30 tests pass): the owner uploaded the
  official PDFs, the edition registry exists, and the full PDF field list is generated.
- The owner works from a phone and may continue in Codex or Claude Code. This file is the
  handoff: read it, then continue with "Next action".

## Next action

1. **Wait for the owner to (a) review `forms/i765/fields/08-21-25.md` and (b) settle the
   edition question** (see Blockers). Do NOT write the field mapping before both.
2. Then step 2: Pydantic schema + mapping to PDF fields (recommended: Opus 5.5, effort high).
   Map by TOOLTIP text, not by field name (see "Traps in the PDF" below).

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
- Several tooltips contain stray spaces ("I - 7 65"); do not match tooltips verbatim, match by
  Part/item number.

## Blockers and open questions

- **uscis.gov is not reachable from the cloud sandbox.** The network allowlist includes the
  host, but the site (Akamai) answers `403 Access Denied` to automated requests from
  datacenter IPs. Do not try to bypass it. Workflow: the owner downloads files in a normal
  browser and uploads them (done for the form and instructions on 2026-10-17).
- **Which I-765 edition is current: owner must confirm.** Registry holds 08/21/25 as the
  active edition PROVISIONALLY (`verified_against_uscis_page: false`).
  - Owner's statement (2026-10-17): since 2026-09-15 only edition **09/15/26** is accepted;
    **08/21/25** is rejected. Owner wants only 09/15/26.
  - The files the owner uploaded (said to come from the USCIS form page) are **08/21/25**.
  - Web search the same day (law-firm and university pages, not the USCIS page itself):
    a court order of 2026-09-14 (D. Mass., duration-of-status rule) paused the new edition;
    USCIS reportedly accepts **08/21/25** and does not accept 09/15/26. Pre-order notices
    say the opposite. This matches the uploaded files, but is secondary evidence.
  - To close it: the owner opens uscis.gov/i-765 in a browser, reads the "Edition Date" and
    any notice, and sends a screenshot/text. If USCIS offers 09/15/26, upload that PDF and
    its instructions; the registry needs only a new entry and `active_edition` change.
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
| 1 | Fetch PDF + instructions, fix edition, list PDF fields (STOP for owner) | Sonnet 5.5 | medium | done, awaiting owner approval |
| 2 | Pydantic schema + mapping to PDF fields | Opus 5.5 | high | todo |
| 3 | Validation + flags | Opus 5.5 | high | todo |
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
