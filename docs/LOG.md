# Project log

One entry per commit or step, newest last. `git log` is the source of truth for commits;
this file adds the reasoning. An entry lists the commit that introduced the work, so the
commit that adds a log entry is not itself listed (it appears in the next entry).

## 2026-10-17 — Planning (no commits)

- Studied the task, checked sources: I-765 edition status, Claude model IDs, UPL and chatbot
  rules. Proposed architecture and an 11-step plan; the owner answered 8 questions
  (see `DECISIONS.md`).
- Owner's repo was created under a different name than proposed: `Immigration-service`.

## Step 0 — `d24cdd9` Project skeleton, model config, PII-safe logging

- `pyproject.toml` (uv, pytest, ruff), `.env.example`, `.gitignore` (ignores `.env`, DB,
  uploads).
- `config.py`: settings from `.env`; allowed models `claude-sonnet-5-5` (default) and
  `claude-opus-5-5`; no per-tier settings; API key held as `SecretStr`.
- `logging_utils.py`: redacting formatter (A-Numbers, SSNs, receipt and document numbers,
  phones, emails, long digit runs), also redacts tracebacks.
- README: disclaimer, 7 draft Legal Principles, data protection, architecture table, setup.
- 22 tests. A bug found along the way: the first phone regex redacted timestamps; narrowed.

## `54fa8f3` — Merge step 0 into the GitHub repo

- The GitHub repo `romanbozhko16-afk/Immigration-service` already had an auto-generated
  one-line README (`cddc311`). Local history was merged on top; the full README kept.
- Pushed to `origin/main`. Tests re-run after merge: 22 passed.

## Attempted step 1, first try (no commit) — blocked

- Network allowlist opened for `www.uscis.gov`; the sandbox proxy now connects, but uscis.gov
  returns `403 Access Denied` (Akamai bot protection) to automated requests, including the
  direct PDF URLs. Not bypassed. See `STATUS.md` Blockers for the workaround.

## `789a52d` Handoff docs

- Added `AGENTS.md`, `CLAUDE.md`, `docs/STATUS.md`, `docs/DECISIONS.md`, `docs/LOG.md` so a
  new session (Codex or Claude Code) can continue without the chat history.

## Step 1 — `21a903f` Official PDFs, edition registry, field list

- The owner downloaded the form and instructions in a browser and uploaded them; the
  assistant copied them to `forms/i765/source/` and pinned SHA-256 values.
- Edition printed inside both PDFs: **08/21/25** (not 09/15/26 as the owner expected). Recorded
  as the provisional active edition; the owner must confirm on uscis.gov (see `STATUS.md`).
- `scripts/list_pdf_fields.py` lists the AcroForm widgets (161; 154 fillable + 7 barcodes) into
  `forms/i765/fields/08-21-25.{json,md}`.
- `src/uscis_assistant/forms/registry.py` + `forms/i765/editions.json`: one active edition,
  SHA-256 verification, switchable by data. Added `pypdf` and `cryptography` dependencies
  (USCIS PDFs are AES-encrypted with an empty user password).
- Found traps for the mapping step (names vs item numbers, checkbox on-values, interpreter/
  preparer name offset); documented in `STATUS.md`.
- 30 tests pass (8 new).

## Step 2 — `7998124` Pydantic schema and field map

- Owner confirmed edition 08/21/25 (re-uploaded both PDFs; byte-identical, no newer edition
  found). Registry flag `verified_against_uscis_page` set to true with that note.
- `forms/i765/schema.py`: `I765Application` with Parts 1-6 and the attorney box; enums for
  every checkbox group; eligibility category stored exactly as the user states it (None =
  attorney review); interpreter/preparer names have no middle name (the form has none).
- `forms/i765/mappings/08-21-25.json`: 148 entries + 6 deliberately unmapped (signatures and
  signature dates) = all 154 fillable fields. Each entry carries tooltip snippets.
- `forms/field_map.py`: loader, schema path resolver, leaf-path enumeration.
- Tests check the map against the real PDF: field exists and type matches, tooltip contains
  the snippets and the right Part, checkbox on-value exists, the value matches the box's
  meaning, full coverage both ways, Apt/Ste/Flr order by position, attorney-decision flags.
- Mutation check: 7 deliberate corruptions of the map (sex swap, yes/no swap, marital swap,
  naive unit mapping, item 3/4 swap, dropped entry, missing attorney flag) all fail tests.
  The first run missed the sex swap; a "value matches meaning" test was added.
- Verified visually by rendering page crops: Apt/Ste/Flr label order; category boxes print
  their own parentheses.
- 346 tests pass.

## Step 3 — Validation and flags (see `git log` for the hash)

- Owner approved step 2 and chose "the safest option" for the two open questions: attorney
  review for "Yes" to the arrest questions (P2.30, P2.31.B) and for the ABC box (P3.6).
- Read the instructions (How To Complete, pages 17-20) and the PDF help texts; every rule
  cites one of them.
- `validation/flags.py`: flag codes and severities. `validation/i765.py`: 9 rules
  (interpreter/preparer question, eligibility category and items 28-31, legally sensitive
  answers, addresses, history, identifier formats, dates, lists and Part 6, Part 3).
- Tests: 37 validation tests, including a guard that no message sounds like legal advice and
  a test that the category shape accepts all 57 codes in the instructions. Turning off any
  single rule fails at least 2 tests. 383 tests in total.
