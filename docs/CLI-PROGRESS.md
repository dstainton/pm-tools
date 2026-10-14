# CLI progress and feedback standard

**Status:** Required for all pm-tools commands. Applies to new features and to existing commands when they are reviewed or modified.

## User expectation

A user must never be left wondering whether an interactive `pm` command is working, waiting, or stuck. Every command that may take noticeable time must announce its purpose before the slow work begins, show useful feedback throughout, and report a clear outcome when complete or when it fails.

This is a product requirement, not an invitation to print excessive diagnostic output.

## Standard approach

Use the existing `core/progress.py` functionality, including `progress.start`, `progress.note`, `progress.finish`, `progress.numbered`, and the CLI's `progress.running()` lifecycle. Do not create a competing spinner, timer, or progress framework.

- **Start:** Identify the specific operation before network, model, large data processing, or long local file I/O begins. For multiple projects or workstreams, identify the current scope.
- **During:** Update when a meaningful stage changes. Include measured counts when available, such as Jira issues retrieved or workstreams examined. Avoid fabricated percentages or estimated time remaining.
- **Still working:** Retain the existing elapsed-time and periodic heartbeat behaviour for long steps; do not leave a silent gap through nested or paginated operations.
- **Complete:** End active progress cleanly before showing normal results. State success or partial completion and any report path.
- **Failure:** Identify the failed stage and provide an actionable explanation. Clean up progress display and never present incomplete output as complete.
- **Fast commands:** Commands that finish immediately may return a concise result without unnecessary animated progress, provided there is no noticeable silent wait.

## Output environments

Interactive terminals should use the existing one-line progress display and elapsed timer. Redirected or non-interactive output should remain readable as plain lines with bounded reminders rather than terminal escape effects. Scheduled jobs, tests, Windows PowerShell, and Linux must behave consistently.

Do not pollute machine-readable output (such as JSON), interactive prompts, or command pipelines with progress text. Route progress appropriately or suppress it when structured output must stay machine-readable. Never print secrets, personal data, or sensitive source content as progress indicators.

## Verification required

For each new command and when changing an existing slow command, add tests demonstrating:

1. Progress starts **before** a mocked slow network or model operation.
2. A multi-stage operation identifies major stages or scope changes, including count updates when available.
3. Completion and failure both cleanly close progress.
4. Redirected output and machine-readable modes remain valid.
5. Tests do not rely on real sleep delays, real Jira credentials, or network access.

Reviewers must verify progress behaviour, not merely successful final output. Existing inconsistent commands should be audited and corrected in bounded follow-up work rather than through a speculative whole-repository refactor.

## Immediate follow-up

`pm assess` currently begins whole-project Jira retrieval without calling `progress.start`, so the lower-level Jira issue counter cannot surface while it runs. Add stage-level feedback for inventory retrieval, workstream ownership discovery, deterministic analysis, and report generation. Verify it on Windows PowerShell as well as captured output.

The Phase 1D backlog-report improvement remains a separate concern. See `docs/PHASE1-ASSESSMENT.md`.
