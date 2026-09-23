# Installing pm-tools

Python 3.9+ is the only prerequisite. You do not clone the repo to use the tool.

## Windows

From PowerShell:

```powershell
irm https://raw.githubusercontent.com/dstainton/pm-tools/main/install.ps1 | iex
```

That installs pipx if it is missing, installs pm-tools from GitHub, and runs
`pm init` when `~/.pm-tools/config.yaml` does not exist. It does not download a model.
If pipx already has pm-tools, the script upgrades it. It runs the `pm.exe`
pipx just installed, and removes an older `pm.exe` left in Python's Scripts
folder by `pm-helper`. `pm -h` should list `doctor` and `today`. If it still
lists `standup`, open a new PowerShell. `pm-tools -h` is the same program.

## macOS or Linux

```bash
pipx install git+https://github.com/dstainton/pm-tools.git
pm init
```

## Fill in the config

`pm init` copies a template to `~/.pm-tools/config.yaml` and stops. Open that file
and replace the placeholders:

- `jira.base_url`, `jira.email`, `jira.api_token`, `jira.project`
- the sample `products:` and `workstreams:` entries

A token can be `${ENV:SOME_VAR}` instead of a literal. Confluence, SharePoint,
and Teams stay off until you want them.

```text
pm doctor
pm today
```

`pm doctor` checks the login, the project, the field IDs, and the workstream
components. It does not rewrite the file. `pm today` is the first real use.

If `~/.pm-tools/config.yaml` already exists, `pm init` leaves it alone. Later
releases are installed with `pm update`, which upgrades the program and adds
new config keys without replacing the file.

## Local model

Only `pm report`, `pm refine`, and `pm ready --deep` need a model. The default
endpoint is `http://127.0.0.1:8080/v1/chat/completions` with the alias
`qwen-local`. These scripts assume `pm` is already on PATH. They do not
install it.

```powershell
.\setup-windows-qwen-small.ps1
.\setup-windows-qwen-small.ps1 -StartServer
```

The larger model the prompts are written for:

```powershell
.\setup-windows-qwen-large.ps1
.\setup-windows-qwen-large.ps1 -StartServer
```

## Development

From a clone, when you are changing pm-tools itself:

```bash
pip install -e .
```

An editable install does not get `pm update`'s code upgrade. Pull the
repository yourself. `pm update` will still migrate `~/.pm-tools/config.yaml`.
