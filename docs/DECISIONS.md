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
- **2026-10-17 — RAG without embeddings (BM25), citations via the Anthropic Citations API.**
  Small corpus (form instructions + Policy Manual chapters); simpler to audit.
- **2026-10-17 — Logging: never log answers/documents/prompts/model output; regex redaction
  is only a safety net.** Phone regexes kept narrow so timestamps are not redacted.
- **2026-10-17 — Handoff files: `AGENTS.md` (read automatically by Codex), `CLAUDE.md`
  importing it, and `docs/` for state.** Source: OpenAI Codex docs, "Custom instructions with
  AGENTS.md".
