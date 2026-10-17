# Project status

*Last updated: 2026-10-17, after step 0.*

## Where we stopped

- **Step 0 is done and pushed** (skeleton, model config, PII-safe logging; 22 tests pass).
- **Step 1 is blocked** on getting the official I-765 PDF and instructions (see Blockers).
- The owner works from a phone and may continue in Codex or Claude Code. This file is the
  handoff: read it, then continue with "Next action".

## Next action

Step 1: **fetch the official files, fix the edition, list the PDF fields.**

1. Obtain `Form I-765` PDF and `Instructions for Form I-765` PDF from uscis.gov.
   Put them in `forms/i765/source/` (the owner may upload them manually, see Blockers).
2. Read the edition date from inside the PDF and compare with the USCIS page text.
3. Create the edition registry: edition date, source URL, download date, SHA-256 per file.
   Design it so changing the edition is a config change plus a new field map. Support only
   the ONE current edition (the owner does not want old editions supported).
4. Inspect AcroForm/XFA and print the full field list (name, type, page, max length, options).
5. **Stop and show the owner the field list. Do not write the mapping before approval.**

## Blockers and open questions

- **uscis.gov is not reachable from the cloud sandbox.** The network allowlist now includes
  the host, but the site (Akamai) answers `403 Access Denied` to automated requests from
  datacenter IPs. Do not try to bypass it. Fix: the owner downloads the two PDFs in a normal
  browser and uploads them to `forms/i765/source/`, and pastes the "Edition Date" text and
  any notice from the form page.
- **Which I-765 edition is current is unresolved.**
  - Owner's statement (2026-10-17): since 2026-09-15 only edition **09/15/26** is accepted;
    **08/21/25** is rejected. Owner wants only 09/15/26.
  - Web search the same day (law-firm and university pages, not the USCIS page itself):
    a court order of 2026-09-14 (D. Mass., duration-of-status rule) paused the new edition;
    USCIS reportedly accepts **08/21/25** and does not accept 09/15/26. Several pre-order
    notices still say the opposite.
  - Resolve from the primary source: the edition date printed inside the downloaded PDF and
    the notice on uscis.gov/i-765. Show the owner the quote and decide together.
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
| 1 | Fetch PDF + instructions, fix edition, list PDF fields (STOP for owner) | Sonnet 5.5 | medium | blocked |
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
