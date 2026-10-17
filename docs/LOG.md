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

## Attempted step 1 (no commit) — blocked

- Network allowlist opened for `www.uscis.gov`; the sandbox proxy now connects, but uscis.gov
  returns `403 Access Denied` (Akamai bot protection) to automated requests, including the
  direct PDF URLs. Not bypassed. See `STATUS.md` Blockers for the workaround.

## Handoff docs — added `AGENTS.md`, `CLAUDE.md`, `docs/`

- Created so a new session (Codex or Claude Code) can continue without this conversation.
