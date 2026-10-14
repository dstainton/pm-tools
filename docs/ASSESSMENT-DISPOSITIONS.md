# Configurable assessment dispositions

`pm assess` classifies project-available Jira statuses into **active**, **completed**, and **excluded** populations. Statuses are discovered using Jira's project status endpoint, then queried by exact status ID. This avoids referencing status names that are not installed. Default classification uses Jira's `Done` status category for completed work, plus common excluded status aliases. Anything else in Jira's `To Do` or `In Progress` categories remains active. An unknown Jira category fails explicitly.

Default excluded names (case-insensitive exact matches): Cancelled, Canceled, Rejected, Duplicate, Won't Do, Wont Do, Won't Fix, Wont Fix, Abandoned, Obsolete. These names are not universal claims about status meaning and may be overridden.

## Optional configuration

```yaml
assessment:
  dispositions:
    excluded: [Cancelled, Rejected, Duplicate, "Won't Do"]
    completed: [Completed, Delivered]
    active: [Reopened]
    projects:
      OPS:
        excluded: [Cancelled, Rejected, Duplicate, Decommissioned]
```

Each configured list **replaces** the list of that disposition at its level, including the built-in default exclusions. A project override replaces that disposition's global list, leaving other dispositions unchanged. Explicit statuses must exist in that Jira project; unknown names stop the assessment instead of silently ignoring them. All lists may be empty.

Classification precedence is **excluded → completed → active → Jira category fallback**. Each status ID belongs to one population. Project-scoped JQL is reported separately for all three populations. The active population is fully inventoried, while completed and excluded totals use Jira's approximate-count endpoint and are labelled approximate or unavailable. These counts must not be interpreted as an exact reconciliation to the inventory. If project status discovery is unavailable, the assessment stops rather than reverting to a misleading scope.

The generic `queries.status.open`, `queries.status.done`, and `queries.coverage.open_in_project` configuration interfaces remain available to other commands. `pm assess` now uses its own explicit classification; configuring those legacy query overrides does not change its disposition policy. No Jira writes, model calls, or snapshot retention are introduced.
