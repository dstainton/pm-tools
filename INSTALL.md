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
and Teams stay off until you want them. `pm setup --section confluence` records
the shared space (its name or key) and your team page, then shows the product
and workstream folders it found under the team page. A space set on a
workstream, with no page, still reads that whole space. `pm update` does not insert those keys.

```text
pm doctor
pm today
```

`pm doctor` checks the login, the project, the field IDs, and the workstream
components. It does not rewrite the file. `pm today` is the first real use.

If `~/.pm-tools/config.yaml` already exists, `pm init` leaves it alone. Later
releases are installed with `pm update`, which upgrades the program and then
migrates the config with that new program. It adds new keys without
replacing the file. One run is enough.

## Local model

Only `pm report`, `pm refine`, and `pm ready --deep` need a model. The default
is Ollama at `http://127.0.0.1:11434/v1/chat/completions` with `qwen3:4b`
(about 2.5 GB, so a low-end laptop can run it). Install Ollama, then
`ollama pull qwen3:4b`. `pm setup --section model` checks the usual local
servers (Ollama, Lemonade, LM Studio, llama.cpp, and the others in
`local_models.endpoints`), lists the models each one is serving, and can
install Ollama or Lemonade Server after you type `yes`. Set `model.api_key`
when that server expects a bearer token. These scripts assume `pm` is
already on PATH. They do not install it. They still publish the alias
`qwen-local` on port 8080.

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
