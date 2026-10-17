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

## Step 1 — Official PDFs, edition registry, field list (see `git log` for the hash)

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
