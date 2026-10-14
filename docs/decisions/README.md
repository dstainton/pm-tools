# Durable decisions

Use short decision records for changes that remain important across multiple PRs: architecture boundaries, data ownership, privacy and write authority, or product conventions with substantial downstream consequences.

Do not write an ADR for routine naming, bug fixes, test additions, or small internal refactors.

Suggested filename: `0001-short-description.md`.

Each record contains:

- **Status:** Proposed, Accepted, Superseded, or Rejected
- **Date:** YYYY-MM-DD
- **Context:** The problem and constraints
- **Decision:** The chosen approach (for Accepted records)
- **Alternatives:** Reasonable approaches considered
- **Consequences:** Trade-offs and implementation impact

Only the owner accepts or supersedes durable decisions. Proposed records are not implementation authority. Accepted decisions constrain subsequent work until explicitly superseded. Use GitHub PR review and the commit history rather than adding a decision-management service.
