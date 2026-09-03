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
> migrate your live config. Copy the `membership:`, `scopes:` and revised
> `workstreams:` sections from the bundled `config.yaml` into your current one,
> preserving your existing URLs and credentials. Older configs keep working, so
> this can wait until convenient.

The bundled config assumes:

- one Jira project, named once in `jira.project` (`APS` by default)
- workstreams are identified by Component(s), normally carried on Epics
- Stories, Tasks, Bugs and Sub-tasks inherit their workstream from their parent
  when they carry no Component of their own

A workstream is three lines, and no JQL:

```yaml
- name: "Secure Data Exchange"
  abbrev: "SDX"
  components: ["Secure Data Exchange"]
```

Add or remove one without editing the file by hand:

```powershell
pm workstreams add --name "Billing Platform" --abbrev BIL --components "Billing Platform"
pm workstreams remove BIL
```

**Verify the exact Component names in Jira** — this is the one thing only you
can confirm, and one command checks it:

```powershell
pm workstreams check --show-jql
```

That reports whether each Component exists in the project (suggesting close
matches when it doesn't), how many Epics and directly tagged issues carry it, and
roughly how much work each command will see.

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
pm workstreams check
pm lint --workstream SDX
```

If `pm lint` finds the expected SDX children even though those children do not
have the SDX Component themselves, inheritance is working.

To check the code itself without touching Jira or the model:

```powershell
python -m unittest discover -s tests
```
