"""Write docs/CUSTOMISING.md from the prompt and query registries."""

from core import prompts, queries


def render():
    lines = [
        "# Customising prompts and queries",
        "",
        "Defaults live in the code. The config file holds overrides only.",
        "`pm doctor --prompts` and `pm doctor --queries` show what is in effect.",
        "",
        "## How to override",
        "",
        "Under `prompts:`, an entry takes `text` (the whole prompt), `file` "
        "(a path relative to the config file), `append` (text added at the "
        "entry's insertion point, or at the end), `values` (named values, and "
        "`headings` to rename report sections), and `based_on` (the built-in "
        "version you started from; `pm doctor` warns when the built-in has "
        "moved on). Set `text` or `file`, not both.",
        "",
        "Under `queries:`, an entry is `{text: ...}` or a plain string. A new "
        "`status.*`, `sprint.*`, or `assignee.*` value adds a scope option. "
        "`*.any` means no filter and cannot be overridden.",
        "",
        "An override must keep each name listed under \"Must keep\", and may "
        "use only the listed placeholders.",
        "",
        "## Prompts",
        "",
    ]
    for prompt_id, entry in prompts.PROMPTS.items():
        lines.append(f"### `{prompt_id}`")
        lines.append("")
        lines.append(entry["explain"])
        lines.append("")
        lines.append(f"Used by: {entry['used_by']}.")
        names = sorted(prompts._known(entry))
        if names:
            lines.append(f"Placeholders: {', '.join(names)}.")
        if entry["required"]:
            lines.append("Must keep: " + ", ".join(
                f"{{{name}}}" for name in entry["required"]) + ".")
        if entry["contract"]:
            lines.append("Must still contain: " + ", ".join(entry["contract"]) + ".")
        lines.append("")
        lines.append("```")
        lines.append(entry["text"].rstrip("\n"))
        lines.append("```")
        lines.append("")
    lines.append("## Queries")
    lines.append("")
    for query_id, entry in queries.QUERIES.items():
        lines.append(f"### `{query_id}`")
        lines.append("")
        lines.append(entry["explain"])
        lines.append("")
        lines.append(f"Used by: {entry['used_by']}.")
        names = sorted(set(queries._PLACEHOLDER.findall(entry["text"])))
        if names:
            lines.append(f"Placeholders: {', '.join(names)}.")
        keep = [name for name in entry["required"]
                if queries._KINDS.get(name) != "vocab"]
        if keep:
            lines.append("Must keep: " + ", ".join(
                f"{{{name}}}" for name in keep) + ".")
        lines.append("")
        lines.append("```")
        lines.append(entry["text"])
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main():
    print(render(), end="")


if __name__ == "__main__":
    main()
