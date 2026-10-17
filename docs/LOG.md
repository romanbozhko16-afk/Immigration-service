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

## Step 3 — `06b7a24` Validation and flags

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

## Step 3 addition — `f0bc63b` Expired passport notice

- Owner asked for a user-facing notice when the passport is expired, explaining it is not an
  error. New flag code `notice` (severity info) with a verbatim quote from instructions
  page 19. Tests: notice only for a date before today, quote matches the PDF text. 386 tests.

## Step 4 — `aea627e` Encrypted storage, audit log, deletion

- Owner approved step 3 (with the passport notice).
- Added SQLAlchemy. `storage/crypto.py` (AES-256-GCM, context-bound), `storage/keystore.py`
  (per-case keys in a separate DB, wrapped by MASTER_KEY), `storage/models.py`,
  `storage/store.py` (`CaseStore`), `storage/db.py` (SQLite pragmas: foreign_keys,
  secure_delete). `scripts/generate_master_key.py`; `.env.example` has MASTER_KEY and
  KEYSTORE_URL.
- Corrected an earlier claim: deleting a key protects backups only if keys are stored apart
  from the data. Hence the separate key store.
- Self-review found that a hash chain alone misses removal of the newest events; added the
  chain head on the case row.
- 21 storage tests, including raw-file scans for plaintext and for the destroyed key.
  Mutation check: 6 deliberate weakenings; 5 failed tests at once. The one that did not
  (dropping the case id from the encryption context) is covered by per-case keys; it exposed
  a missing test for swapping ciphertext between fields of one case, which was added and
  catches field-binding removal. 407 tests in total.

## Step 5 — `c1bac9d` PDF filling

- Owner approved step 4. Probed the PDF: comb text boxes (A-Number, SSN print only digits;
  "A-" is printed), no length limits, no signature fields, an Adobe usage-rights signature
  (`/Perms`) that any change invalidates.
- `forms/i765/filler.py`: fill from the field map, drop XFA and `/Perms`, read back and
  compare. Part 6 overflow, category split, attorney-decision skip, source files verified.
- Validator: "N/A" accepted for the A-Number (instructions p.18).
- Tests (hand-written expectations, 65 fields), two test mistakes found and fixed: barcodes
  are not empty (they hold form id, edition, page) and a read-back cannot detect logic
  errors, only writer failures (logic errors are covered by the hand-written expectations).
  Corrupting the map in 4 ways fails tests. Rendered and viewed pages 1, 4, 5. 485 tests.

## Step 6 — Interview engine (see `git log` for the hash)

- Owner approved step 5. Located all 30 help quotes verbatim in the instructions (one page
  each) before writing them into the bank; SSN help uses the PDF tooltip (no instruction
  text for item 13).
- `interview/bank.py` (models, conditions), `interview/parse.py` (deterministic parsing),
  `interview/texts.py` (RU/UK/EN interface texts), `interview/engine.py` (flow, session,
  building `I765Application`). Bank registered in `forms/i765/editions.json`.
- Storage: `translation_method` gained "pending".
- Tests: bank completeness, verbatim quotes on stated pages, no advice wording in 3
  languages, no attorney-decision item asked, parsing, full RU interview -> validation ->
  filled PDF. 845 tests in total.
