# pm-tools

pm-tools is a helper for product managers who work in Jira. You type short
commands such as `pm today` or `pm report`, and it reads your Jira (and,
if you like, Confluence and SharePoint) and tells you what needs your
attention, what changed, and what is ready for the next Sprint.

It runs on your own computer. When it needs to write a summary, it uses an
AI model that also runs on your computer, so your work stays on your
machine.

- New here? Read this page, then [docs/START.md](docs/START.md).
- Already set up? [docs/EVERYDAY.md](docs/EVERYDAY.md) is the short list of
  everyday commands.

---

## What it can do for you

| When | Command | What you get |
|---|---|---|
| Every morning | `pm today` | One screen: the Sprint Goal, what needs you, what moved yesterday, and what has stalled. Each item has a number. |
| Straight after | `pm do 2` | Carries out item 2 from this morning's list. It shows you the change first and asks before it touches Jira. |
| During the day | `pm note "..."` | Jots down an idea in a second. File it as a Jira ticket later with `pm inbox`. |
| Daily Scrum | `pm daily` | What moved since yesterday, and who is working on what now. |
| Before Sprint Planning | `pm ready` | A pass or fail for each ticket against your team's "ready" rules. |
| Tidying the backlog | `pm lint` | Tickets with missing details, such as no estimate, no parent, or dates that do not make sense. |
| Fixing the gaps | `pm refine` | Draft titles, acceptance criteria, and estimates you can edit and then send to Jira. |
| Before a meeting | `pm brief --for "Monthly review"` | What changed since you last met that group, and what you need from them. |
| End of the week | `pm report` | A written weekly update, organised by Epic, with links to every source. |
| Any time | `pm show APS-30` | One ticket on screen: status, owner, dates, and link. |

Everything else is in [All commands](#all-commands).

---

## What you need

- A computer running Windows, macOS, or Linux.
- Python 3.9 or newer.
- A Jira Cloud account, and an API token for it. You create the token at
  [id.atlassian.com → Security → API tokens](https://id.atlassian.com/manage-profile/security/api-tokens).
- Optional: a local AI model. Only the commands that write text need it
  (see [The AI model](#the-ai-model)). Everything else works without one.

---

## Install

**Windows.** Open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/dstainton/pm-tools/main/install.ps1 | iex
```

**macOS or Linux.** Open a terminal and run:

```bash
pipx install git+https://github.com/dstainton/pm-tools.git
```

Check it worked:

```text
pm -h
```

You should see a list of commands, including `today` and `doctor`.

---

## Set it up

Run:

```text
pm setup
```

It asks one question at a time: your Jira site, your email, your API
token, and your Jira project. It then looks for an AI model on your
computer and suggests one that suits your machine. Press Enter to skip a
question and come back to it later. It will not change an answer you have
already given.

Your settings are saved in one file, `~/.pm-tools/config.yaml` (a folder
called `.pm-tools` in your home folder). You can open it in any text
editor. Every setting has a comment above it explaining what it does.

Then check everything:

```text
pm doctor
```

`pm doctor` tests your login, your project, your settings, and the AI
model, and tells you how to fix anything that is wrong. It does not change
your file.

To redo one part of setup later:

```text
pm setup --section jira
pm setup --section model
pm setup --section confluence
```

### Keeping your token out of the file

Any setting can read its value from your computer's environment instead of
the file. Write it like this:

```yaml
api_token: "${ENV:JIRA_TOKEN}"
```

pm-tools then reads the token from an environment variable named
`JIRA_TOKEN`.

---

## Products and workstreams

pm-tools groups your work in two levels:

- A **product** is something you are responsible for, for example
  "Integration Platform".
- A **workstream** is a team or an area of work inside a product, for
  example "Secure Data Exchange".

A workstream is found in Jira by its **Component**. That is the Component
field on your Epics. Anything under an Epic with that Component belongs to
that workstream, and so does any ticket that carries the Component itself.
You do not have to add the Component to every Story or Sub-task.

In the settings file it looks like this:

```yaml
products:
  - name: "Integration Platform"
    abbrev: "IP"

workstreams:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    product: "IP"
    components: ["Secure Data Exchange"]
```

The `abbrev` is a short name you can type instead of the full one.

You can add and remove them without editing the file by hand:

```text
pm products add --name "Billing Platform" --abbrev BILL
pm workstreams add --name "Invoicing" --abbrev INV --components "Invoicing" --product BILL
pm workstreams remove INV
```

Then check Jira agrees:

```text
pm workstreams check
```

It tells you if a Component name is misspelt, suggests the closest match,
and shows how many tickets each workstream will see.

### Looking at just one product or workstream

Add `--product` or `--workstream` to any command:

```text
pm today --product IP
pm lint --workstream SDX
pm report -p IP -w SDX,INV
```

You can use the short name or the full name, in any capitals.

---

## Confluence (optional)

pm-tools can include Confluence pages that changed during the week in your
report, and it can follow your decision logs, risk registers, and
architecture decision records (ADRs).

First add your Confluence address, email, and token in the `confluence:`
part of the settings file, or run `pm setup --section confluence`. Then
tell pm-tools where each team keeps its pages. There are two common
layouts.

**Each workstream has its own space.** Give the workstream the space key:

```yaml
workstreams:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    components: ["Secure Data Exchange"]
    confluence_space: "SDX"
```

**Several teams share one space, and each team has its own team page.**
Under your team page are pages or folders for your products, and inside
those, pages or folders for workstreams. Say which space you use and the
title of your team page:

```yaml
confluence:
  space: "POSM Chapter"                          # the space name or its key
  team_page: "API Program Services (APS) Team"
```

That is often all you need. pm-tools looks under your team page for a page
or folder whose title matches each product and workstream, by its name or
its short name. For example, a folder called "Secure Data Exchange (SDX)" is
used for a product named "Secure Data Exchange" or with the short name
`SDX`. Other teams' pages in the same space are left out.

When a folder's title does not match, name it on the product or workstream:

```yaml
products:
  - name: "Secure Data Exchange"
    abbrev: "SDX"
    confluence_page: "SDX Home"
```

In the report:

- Each workstream shows the pages inside its own folder.
- Pages in a product folder that are not inside a workstream folder appear
  once, under the product.
- Pages under the team page that are not in any product or workstream
  folder appear once near the top, as team pages.

To leave out folders or pages that don't belong in a report, such as
personal notes or work in progress, list their titles. Everything inside
them is left out too:

```yaml
confluence:
  skip: ["Life Events", "SM WIP"]
```

If two pages have the same title, use `confluence_page_id` with the page's
number instead. The number is in the page's web address. To stop pm-tools
looking for a folder for one product or workstream, set
`confluence_page: false`. Run `pm doctor` to see which folder was found for
each one.

### Decisions, risks, and ADRs

A register is a page or folder whose sub-pages are the individual
decisions, risks, or ADRs. pm-tools lists the new and changed entries in
your report, with their status.

```yaml
registers:
  - type: risk              # risk, decision, or adr
    name: "SDX risks"
    title: "Risks"          # the title of the register page or folder
    product: SDX
```

- `under` names the folder to look in, when you need to. Without it, pm-tools looks in the
  register's own workstream or product folder first, then directly under
  your team page, so another team's "Risks" page is never used. `under` can
  also name a page elsewhere in the space, for a register shared by several
  teams.
- `product` or `workstream` says where the register appears in the report.
  Leave both off to show it at the top, for the whole portfolio.
- `page_id` can be used instead of `title` and `under`.

If you keep one shared list for every product, label each entry in
Confluence with the product or workstream short name (for example `SDX`),
and add `split: label`:

```yaml
registers:
  - type: decision
    name: "All decisions"
    title: "Decisions"
    split: label
```

Each decision then appears under the workstream or product named by its
label. A workstream label wins over a product label. Entries with no
matching label appear at the top of the report. You can use both layouts at
once. A page that appears in both is only listed once.

`pm doctor` checks that each folder and register can be found.

---

## The AI model

These commands use an AI model to write or judge text: `pm report`,
`pm brief --debrief`, `pm refine`, `pm review`, `pm ready --deep`, the
filing suggestions in `pm inbox`, the written part of
`pm release-notes`, and `pm warm`. Everything else works without one.

A long command tells you what it is doing, such as reading Jira or writing
a section. In a terminal that line counts the seconds, so you can see it is
still working. A scheduled run writes the same steps to its log and, if a
step is still going after 15 seconds, writes a reminder.

The model runs on your own computer. The simplest option is
[Ollama](https://ollama.com):

1. Install Ollama from [ollama.com/download](https://ollama.com/download).
2. Download the default model (about 2.5 GB, fine for most laptops):

   ```text
   ollama pull qwen3:4b
   ```

3. Run `pm doctor` to check pm-tools can reach it.

`pm setup --section model` finds model servers already running on your
computer (Ollama, Lemonade, LM Studio, llama.cpp, and others), lists their
models, and recommends one that fits your computer's memory. If none are
running, it can install Ollama or Lemonade for you. It only does that after
you type `yes`.

A bigger model writes better summaries. On a computer with 32 GB of memory,
a 27-billion-parameter model such as `qwen3.8:27b` works well, though it
uses a lot of memory while it runs.

If your model server needs a password (an API key), put it in
`model.api_key`. Leave it blank if it does not.

On Windows, `setup-windows-qwen-small.ps1` and
`setup-windows-qwen-large.ps1` set up a llama.cpp server instead. They name
the model `qwen-local` on port 8080, so set `model.endpoint` to
`http://127.0.0.1:8080/v1/chat/completions` and `model.name` to
`qwen-local` if you use them.

### Making it faster

The first run of a model command can take a while. Answers are remembered,
so the next run only asks about what changed. `pm warm` prepares those
answers ahead of time:

```text
pm schedule add warm --at 07:00
```

---

## All commands

**Everyday**

| Command | What it does |
|---|---|
| `pm today` | Your morning screen. `--all` also includes mentions and new bugs. |
| `pm do N` | Carries out item N from `pm today`, after showing you the change. |
| `pm show KEY` | One ticket on screen. |
| `pm note "..."` | Saves a quick note for later. |
| `pm inbox` | Lists your notes. `edit`, `create`, and `drop` tidy them, turn them into Jira tickets, or throw them away. |
| `pm triage` | Everything waiting on a decision from you, with the action that clears each one. |
| `pm daily` | What moved since yesterday, and work in progress. |

**Backlog quality**

| Command | What it does |
|---|---|
| `pm lint` | Checks every ticket against simple rules: estimate, parent, dates, acceptance criteria, stalled work. |
| `pm ready` | Pass or fail per ticket against your team's ready rules. `--deep` also asks the AI model. |
| `pm refine` | Drafts missing titles, acceptance criteria, and estimates into a file you edit. `--apply` sends what you kept to Jira. |
| `pm review` | Asks the AI model which titles are unclear and which acceptance criteria are incomplete. |
| `pm coverage` | Open tickets no workstream owns, tickets two workstreams both claim, and Components nobody uses. |

**Reporting**

| Command | What it does |
|---|---|
| `pm report` | The weekly update. `--audience leadership` writes a shorter version, and `--audience partner` writes one safe to share outside the team. |
| `pm brief --for "NAME"` | Meeting preparation for one group. `--debrief notes.md` turns your meeting notes into decisions and actions. |
| `pm metrics` | How much the team finishes each week, how long work takes, and a likely finish date. |
| `pm release-notes` | Finished work since a date (`--since`) or in a release (`--version`). |
| `pm publish FILE` | Sends a report to Confluence or Microsoft Teams, after you confirm. |

**Setup and upkeep**

| Command | What it does |
|---|---|
| `pm setup` | Guided setup, one question at a time. |
| `pm doctor` | Checks everything and says how to fix problems. |
| `pm products` | Lists, adds, removes, or checks products. |
| `pm workstreams` | Lists, adds, removes, or checks workstreams. |
| `pm schedule` | Runs commands at set times, for example `pm today` at 08:30. Only commands that read are allowed. |
| `pm warm` | Prepares AI answers ahead of time. |
| `pm update` | Installs the latest version and adds any new settings to your file. |
| `pm init` | Creates a blank settings file, if you would rather fill it in by hand. |

Add `-h` to any command to see its options, for example `pm report -h`.

### Options that work everywhere

| Option | What it does |
|---|---|
| `--product IP`, `--workstream SDX` | Only look at these. |
| `--cached` | Reuse earlier results, even old ones. Handy when you are offline. |
| `--refresh` | Ignore earlier results and fetch everything again. |
| `--out FOLDER` | Save this run's files in a different folder. |
| `--plain` | No colours or symbols. |
| `--config FILE` | Use a different settings file. |

---

## Safety: what pm-tools changes

- It only changes Jira when you ask it to (`pm do`, `pm refine --apply`,
  `pm inbox create`, and a few similar commands). Each one shows you the
  exact change and asks before it writes. `--dry-run` shows the change and
  stops.
- Every change it makes is recorded in `~/.pm-tools/write-log.jsonl`.
- Scheduled commands never change Jira.
- Reports are sent to Confluence or Teams only when you confirm.
- It does not send your data to an online AI service. The one exception is
  `pm mcp`, which is off unless you turn it on
  (see [docs/AUTOMATION.md](docs/AUTOMATION.md)).

---

## Where your files are

| What | Where |
|---|---|
| Your settings | `~/.pm-tools/config.yaml` |
| Reports and other output | `~/.pm-tools/out` (change it with `output.directory`) |
| Remembered results | `~/.pm-tools/cache` |
| Record of Jira changes | `~/.pm-tools/write-log.jsonl` |

To share decisions such as "snooze this finding" with a colleague, set
`state.shared_path` to a synced OneDrive or SharePoint folder.

pm-tools looks for settings in this order and uses the first it finds:
`--config FILE`, the `PM_CONFIG` environment variable, `config.yaml` in the
folder you are in, then `~/.pm-tools/config.yaml`.

---

## Updating

```text
pm update
```

This installs the latest version, then adds any new settings to your file.
Your existing settings and comments are kept. `pm update --dry-run` shows
what would change without changing anything.

---

## When something is not right

- **Start with `pm doctor`.** It checks each part and names the fix.
- **A workstream shows too few or too many tickets.** Run
  `pm workstreams check`. The Component name must match Jira exactly.
- **Story points or start dates are ignored.** Your Jira may store them in
  a different field. Run `pm doctor --discover-fields` to find the right
  one, or `pm doctor --discover-fields --yes` to fill in blank fields.
- **A model command is slow or gives empty answers.** Run `pm doctor` to
  check the model is reachable, then try `pm warm` or a smaller model.
- **`pm -h` shows an older program called "Product Manager Helper".** An
  earlier tool is installed with the same command name. On Windows, run
  `python -m pip uninstall -y pm-helper` and open a new PowerShell window.
  `pm-tools -h` always runs this program.

Keep in mind:

- `pm lint` and `pm ready` follow fixed rules, so their results are exact.
  Anything written by the AI model is a suggestion. Read it before you act
  on it.
- A ticket can appear in two workstreams if its Component differs from its
  Epic's. That is on purpose, so nothing goes missing. `pm coverage` lists
  these tickets, and `membership.child_component_wins: true` makes each
  ticket count only once.

---

## More reading

- [docs/START.md](docs/START.md): the five commands to begin with.
- [docs/EVERYDAY.md](docs/EVERYDAY.md): everyday commands and report windows.
- [docs/DEPTH.md](docs/DEPTH.md): going further.
- [docs/AUTOMATION.md](docs/AUTOMATION.md): scheduling, scripts, and Power Automate.
- [docs/CUSTOMISING.md](docs/CUSTOMISING.md): changing the wording sent to
  the AI model, and the searches sent to Jira and Confluence.
- [INSTALL.md](INSTALL.md): installation in more detail.
- [CHANGELOG.md](CHANGELOG.md): what changed in each release.

---

## For developers

To work on pm-tools itself, clone the repository and install it in editable
mode:

```bash
pip install -e .
```

Run the tests (no Jira, model, or network needed):

```bash
python -m unittest discover -s tests
```

`pm update` does not upgrade an editable install. Pull the repository
yourself.
