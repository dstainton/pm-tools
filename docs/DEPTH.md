# Going further

- Workstreams are Jira Components. `pm setup` proposes one workstream per Component. `pm workstreams check` shows what that membership sees.
- `pm doctor` names the fix. A blank model or a blank field is `pm setup --section model` or `--section jira`. `--section model` probes the servers in `local_models` and, when none answer, can install Ollama or Lemonade after you type `yes`.
- `pm warm` fills the model cache in this order: review, page summaries (including changed register entries), the report, then the inbox. `pm warm --pages` is the right grain for Confluence: one summary per page version, not per report. `--audience pm,leadership` warms both levels.
- `pages.excerpt_chars` is the budget for a Confluence page. Issue details stay short. A decision page is not cut to 180 characters.
- `pm metrics` suppresses a landing date until three items have finished in the window.
- `--plain`, or the environment variable `NO_COLOR`, drops glyphs and terminal links.
- An ended Sprint is printed under `ENDED SPRINT`, not as the current Sprint Goal.
