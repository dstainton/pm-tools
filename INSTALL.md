# Installing `pm` and the local Qwen runtime

## Install the CLI

From inside the `pm_helper` folder:

```powershell
pip install -e .
pm init
```

The editable install creates the `pm` command while keeping code changes live.
`pm init` creates `~/.pm/config.yaml` if one does not already exist.

If `pm` is not found afterwards, use `pipx` or add Python's Scripts directory
to PATH. See `README.md` for details.

## Configure Jira workstreams

> **Existing installation:** `pm init` does not overwrite an existing
> `~/.pm/config.yaml`. Updating the package therefore does not automatically
> migrate your live config. Copy the revised `workstreams:` structure below
> into your current config, preserving your existing URLs and credentials.

The bundled config assumes:

- Jira project: `APS`
- workstreams are represented by Component(s) on Epics
- Stories, Tasks, Bugs, and Sub-tasks inherit their workstream from the Epic

For example:

```yaml
- name: "Secure Data Exchange"
  abbrev: "SDX"
  jira_project: "APS"
  epic_components: ["Secure Data Exchange"]
  jira_jql: 'sprint in openSprints()'
  roadmap_jql: 'statusCategory != Done'
  lint_jql: 'statusCategory != Done'
```

**Verify the exact Component names in Jira.** Update `epic_components` if your
site uses names such as `SDX`, `APS Platform`, or another spelling.

In this mode, the JQL values above are filters inside the workstream. `pm`
resolves the Epics first, then uses Jira's `parentEpic` JQL support to retrieve
their children and nested Sub-tasks.

## Local model

The default config expects:

```text
Endpoint: http://127.0.0.1:8080/v1/chat/completions
Model:    qwen-local
```

Only `pm report`, `pm review`, and `pm ready --deep` require a model.

### Small model for testing or tethered connections

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup-windows-qwen-small.ps1
.\setup-windows-qwen-small.ps1 -StartServer
```

This uses Qwen3-4B Q4_K_M, approximately 2.5 GB.

### Larger model

When bandwidth permits:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup-windows-qwen-large.ps1
.\setup-windows-qwen-large.ps1 -StartServer
```

This uses Qwen3.8-27B Q4_K_M. Both scripts expose `qwen-local`, so the Python
CLI does not need to change when you switch models.

The server is intentionally bound to `127.0.0.1` rather than `0.0.0.0`.

## Quick verification

With the model server running:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/v1/models
pm --help
pm lint --workstream SDX
```

If `pm lint` finds the expected SDX children even though those children do not
have the SDX Component themselves, Epic-component inheritance is working.
