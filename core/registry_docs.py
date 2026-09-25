"""Write docs/CUSTOMISING.md from the prompt and query registries."""

from core import prompts, queries


def render():
    lines = [
        "# Customising prompts and queries",
        "",
        "Defaults live in the code. The config file holds overrides only.",
        "`pm doctor --prompts` and `pm doctor --queries` show what is in effect.",
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
