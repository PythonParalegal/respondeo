# Respondeo — Claude Code Memory
<!-- CANONICAL COPY — tracked in git at .claude/memory/MEMORY.md
     To restore on a new machine: copy this file to the Claude Code project-memory folder.
     That folder is at:
       %USERPROFILE%\.claude\projects\<encoded-project-path>\memory\
     The encoded path is the full project path with : and \ replaced by -.
     Example: C:\\Users\\<user>\\Projects\\ediscovery → c--Users-<user>-Projects-ediscovery
     Run `dir "%USERPROFILE%\.claude\projects\"` to find the correct folder name. -->

## Project Identity
- **App:** Self-hosted Python/Streamlit eDiscovery platform for small law firms
- **Branch model:** `main` (stable) → `beta-X.Y` (sprint) → `debug/...` (review/bugfix)
- **Current sprint branch:** `beta-2.11` (documentation architecture reorg + Inbound Production defensibility follow-ups)
- **Last completed sprint:** beta-2.10 (Inbound Production module + defensibility cleanup)
- **Next sprint:** beta-2.12 — thirteen roadmap flags from sprint close (PST container design, production_selection lifecycle/defensibility UX, Review STR metadata silent-loss, backfill LEFT JOIN, aborted-run display hygiene, nav-registry-adjacent cleanups) plus potential deeper-scope doc refactors deferred from 2.11.

## Key Files (pointer table — content lives in docs/)
- `PROJECT_CONTEXT.md` — authoritative architecture reference (upload to Claude.ai Project)
- `ROADMAP_TODO.md` — sprint roadmap (human-authored)
- `CLAUDE.md` — standing orders + iron laws
- `docs/lessons/` — durable pattern library (extracted from sprint retrospectives)
- `docs/templates/` — reusable workflow templates (preflight, defect-triage, scoped-audit)
- `docs/references/` — dependency API references (PyMuPDF, libpff, Outlook COM, Tika, OpenSearch, MIME)
- `docs/audits/` — per-commit preflight documents
- `docs/archive/` — forensic preservation of completed/superseded work
- `config.py` — all machine-specific paths (gitignored); `config.example.py` is the template
- `db_manager.py` — ALL database access; `log_audit()` and `log_audit_batch()` must NEVER raise
- `auth_manager.py` — bcrypt auth, SHA-256 migration on login, 3-tier RBAC

## Architecture Rules (enforced by CLAUDE.md Standing Orders)
- RBAC: admin > manager > reviewer. Every page checks permission at top.
- Closed cases block ALL write operations (reads stay open).
- `log_audit()` / `log_audit_batch()` are "never-raise" contracts.
- All paths come from `config.py` only.
- Direct SQL in page files is a smell — queries live in `db_manager.py` or are annotated `# db_manager: exempt (reason)`.

## Save-Location Discipline
- Hand-written specs/preflights → `docs/specs/` (active) or `docs/archive/{specs,prompts,m4,sprints}/` (shipped).
- Skill-generated artifacts (brainstorming, writing-plans, etc.) → `docs/superpowers/{specs,plans}/YYYY-MM-DD-<topic>.md` (skill-mandated path; do not relocate).
- ROADMAP Active Specs bookmarks `docs/specs/` only, never `docs/superpowers/` (skill outputs aren't sprint deliverables).
- Sprint close: `git mv` shipped specs to `docs/archive/specs/` and delete their ROADMAP bookmarks in the same commit. Partial shippings stay UNSHIPPED with a "Partial shipping note." See CLAUDE.md Standing Order §Spec Lifecycle Discipline.

## Local AI Infrastructure (Confidentiality Airgap)
- **Ollama v0.20.3** on the development workstation, running CPU-only (no GPU/NPU yet).
- Models: `llama3.1:8b`, `mistral:7b`, `phi4`, `gemma4:e4b`, `nomic-embed-text`.
- API endpoint: `http://localhost:11434` when running.
- **Purpose:** Confidential case data (PSTs, client emails) must never hit Anthropic's API. Use local scripts for structural diagnostics; use Ollama for any language-level analysis. Only structural, non-confidential outputs cross to Claude.
- **Ethical basis:** RPC 1.1 (competence), RPC 1.6 (confidentiality).
- **Existing local scripts:** `container_exploder.py` (structural diagnostics).

## User Preferences
- Teaching-oriented explanations appreciated (the maintainer is not a full-time software engineer).
- Ask for clarification if helpful before proceeding.
- Flag any ethical/legal gray areas — the maintainer is not an attorney.
- Concise responses, no emoji unless asked.
- Don't start substantial coding without explicit instruction.
